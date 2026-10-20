"""Corpus_Fetcher — pin, fetch, cache, and expose remote OSCAL corpora.

This module provides the core data structures and pinned specifications for the
two remote OSCAL corpora that seed the corpus-driven property tests:

- **NIST** ``usnistgov/oscal-content`` — example documents for all 8 OSCAL types.
- **AWS** ``awslabs/oscal-content-for-aws-services`` — component definitions.

Both corpora are pinned to a specific commit SHA so the test input set is
reproducible over time. Documents are fetched once as a codeload tarball per
pinned SHA, extracted into a git-ignored cache under ``tests/.corpus_cache``,
and reused across runs and across parallel workers.

Fetch/cache logic (``ensure_corpus``) provides atomic, concurrency-safe
extraction; ``load_corpus_docs`` walks the cached tree and filters it down to
OSCAL documents. ``load_local_corpus_docs`` reads an optional local corpus in
place from the path in ``OSCAL_BINDINGS_LOCAL_CORPUS`` (Req 11).

The lock, download, safe extraction, and atomic publish live in
``scripts/pinned_archive.py``, which code generation shares. This module
re-exports ``CorpusError``, ``PinnedArchive``, and ``ensure_pinned_archive``
from there. Every fetch made through this module goes through the module
attribute ``_http_get``, so a test can replace it with ``monkeypatch``.
"""

from __future__ import annotations

import json
import os
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from support.scripts import load_script

if TYPE_CHECKING:
    from collections.abc import Mapping

_pinned = load_script("pinned_archive")

CorpusError = _pinned.CorpusError
PinnedArchive = _pinned.PinnedArchive

_http_get = _pinned.http_get
_FileLock = _pinned.FileLock
_thread_lock_for = _pinned.thread_lock_for
_extract_tar_gz = _pinned.extract_tar_gz
_tarball_root = _pinned.tarball_root
_is_complete = _pinned.is_complete
_COMPLETE_MARKER: str = _pinned.COMPLETE_MARKER
_FETCH_ERRORS: tuple[type[BaseException], ...] = _pinned.FETCH_ERRORS
_EXTRACT_ERRORS: tuple[type[BaseException], ...] = _pinned.EXTRACT_ERRORS

# The 8 recognized OSCAL document root keys. A parseable OSCAL document is a
# JSON object with exactly one of these as its single top-level key. The NIST
# corpus is loaded with a broad ``**/*.json`` glob and narrowed by filtering to
# files whose single top-level key is one of these, which drops non-document
# JSON (metaschema, config, etc.) that would otherwise be swept in (Req 2.4).
OSCAL_ROOT_KEYS: frozenset[str] = frozenset(
    {
        "catalog",
        "profile",
        "component-definition",
        "system-security-plan",
        "assessment-plan",
        "assessment-results",
        "plan-of-action-and-milestones",
        "mapping-collection",
    }
)

# tests/.corpus_cache — git-ignored cache directory (Req 3.3). ``corpus.py``
# lives at tests/support/corpus.py, so two parents up is ``tests/``.
CACHE_ROOT: Path = Path(__file__).parent.parent / ".corpus_cache"


@dataclass(frozen=True)
class CorpusSpec:
    """A commit-pinned specification for a remote OSCAL corpus."""

    name: str
    owner: str
    repo: str
    sha: str
    include_globs: tuple[str, ...]
    require_oscal_root: bool = True
    """Drop JSON files whose single top-level key is not an OSCAL root (Req 2.4)."""

    @property
    def tarball_url(self) -> str:
        """The codeload tarball URL for the whole repo tree at the pinned SHA."""
        return f"https://codeload.github.com/{self.owner}/{self.repo}/tar.gz/{self.sha}"


@dataclass(frozen=True)
class CorpusDoc:
    """A single fetched corpus document."""

    corpus_name: str
    rel_path: str
    """Path within the repo tree — used as the document identifier (Req 6.4)."""
    raw_bytes: bytes = field(repr=False)
    """The document as bytes — drives str/bytes equivalence (Req 6.3).

    Excluded from ``repr`` so a failing Hypothesis example never prints document
    content, in particular a local, unpublishable document (Req 11.13).
    """
    root_key: str
    """The single top-level OSCAL key (in ``OSCAL_ROOT_KEYS``).

    Drives AP/AR partitioning.
    """

    def _repr_pretty_(self, p: Any, _cycle: bool) -> None:
        # Hypothesis's pretty-printer (used for "Failing test case" and
        # "Draw N" output) walks ``dataclasses.fields()`` and ignores
        # ``repr=False``. Route it through ``repr`` so ``raw_bytes`` stays
        # hidden there too (Req 11.13).
        p.text(repr(self))


# Pinning (Req 2.1, 2.2) — pinned to full 40-hex commit SHAs. Both `sha` values
# are pinned to each corpus repo's HEAD commit as of the pin date, so the input
# set is stable and reproducible over time.
NIST_CORPUS = CorpusSpec(
    name="NIST oscal-content",
    owner="usnistgov",
    repo="oscal-content",
    sha="78650f02ad9321bb7b817846f8fbd4f2bcd620de",
    include_globs=("**/*.json",),  # broad glob; narrowed by root-key filter (Req 2.4)
    require_oscal_root=True,
)

AWS_CORPUS = CorpusSpec(
    name="AWS oscal-content-for-aws-services",
    owner="awslabs",
    repo="oscal-content-for-aws-services",
    sha="4a1779ffb556c4ab8fb3dad94a19d4d198116803",
    include_globs=("component-definitions/**/*.json",),  # scope (Req 2.3)
    require_oscal_root=True,
)


def ensure_corpus(spec: CorpusSpec, *, cache_root: Path = CACHE_ROOT) -> Path:
    """Ensure the corpus tree for ``spec.sha`` is extracted under the cache.

    Cache-hit (Req 3.2): if the extracted ``{repo}-{sha}`` dir exists and carries
    its ``.complete`` marker, return it with no network access. Cache-miss
    (Req 3.1): download the tarball at the pinned SHA, extract it atomically,
    and return the dir.

    Concurrency-safe (Req 4): a per-corpus lock (``threading.Lock`` for threads
    in this process, ``_FileLock`` across processes) serializes concurrent
    callers so the download happens at most once (Req 4.1); extraction goes to a
    per-PID/thread temp dir published with an atomic ``os.replace`` so no caller
    ever observes a partial tree (Req 4.2) and every caller reads identical
    content (Req 4.3).

    Raises ``CorpusError`` (with the corpus name and pinned SHA) if the fetch
    or extraction fails and no cached copy exists (Req 5.1-5.3). It never skips:
    an unreachable corpus is a hard failure (Req 5.4).
    """
    target = cache_root / f"{spec.repo}-{spec.sha}"
    if _is_complete(target):  # Req 3.2 — cache hit, no network
        return target

    cache_root.mkdir(parents=True, exist_ok=True)
    lock_path = cache_root / f"{spec.repo}-{spec.sha}.lock"
    with _thread_lock_for(lock_path.resolve()):
        try:
            with _FileLock(lock_path):
                # Re-check under the lock: a caller that lost the race finds
                # the tree already published and returns it without
                # downloading (Req 4.1).
                if not _is_complete(target):
                    _fetch_and_publish(spec, target=target, cache_root=cache_root)
        except TimeoutError as exc:
            # ``_fetch_and_publish`` wraps its own timeouts in ``CorpusError``,
            # so a bare ``TimeoutError`` here can only be lock acquisition.
            msg = _corpus_failure(spec, "timed out waiting for the cache lock", exc)
            raise CorpusError(msg) from exc
    return target


def _fetch_and_publish(spec: CorpusSpec, *, target: Path, cache_root: Path) -> None:
    """Download ``spec``'s tarball and atomically publish it at ``target``.

    Must be called with the corpus lock held. On any failure the temp dir is
    removed and nothing is published.
    """
    try:
        data = _http_get(spec.tarball_url)  # Req 3.1 — download at pinned SHA
    except _FETCH_ERRORS as exc:
        raise CorpusError(_corpus_failure(spec, "fetch failed", exc)) from exc

    tmp = (
        cache_root
        / f".tmp-{spec.repo}-{spec.sha}-{os.getpid()}-{threading.get_ident()}"
    )
    try:
        if tmp.exists():  # leftover from a prior interrupted run
            shutil.rmtree(tmp)
        _extract_tar_gz(data, into=tmp)
        # codeload tarballs wrap the whole repo tree in a single top-level
        # directory named ``{repo}-{sha}``. Strip it so the published cache dir
        # exposes the repo root directly and ``include_globs`` such as
        # ``component-definitions/**/*.json`` match as written (Req 2.3).
        root = _tarball_root(tmp)
        (root / _COMPLETE_MARKER).touch()  # mark complete before publishing
        if _is_complete(target):
            # Only reachable if a stale lock was broken while its holder was in
            # fact still publishing: that tree is complete and identical (same
            # pinned SHA), so keep it and discard ours (Req 4.3).
            return
        # A dir at ``target`` without the marker can only be debris (a manual
        # edit, or a crash on a filesystem without atomic rename). We hold the
        # lock, so clearing it cannot race a reader of a complete tree.
        if target.exists() and not _is_complete(target):
            shutil.rmtree(target)
        # Atomic publish via ``os.replace`` (what ``Path.replace`` calls) — no
        # caller ever reads a half-extracted tree (Req 4.2).
        root.replace(target)
    except _EXTRACT_ERRORS as exc:
        # A ``CorpusError`` here is an unsafe tar member; re-raise with name + SHA.
        raise CorpusError(_corpus_failure(spec, "extraction failed", exc)) from exc
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _corpus_failure(spec: CorpusSpec, what: str, exc: BaseException) -> str:
    """Build a ``CorpusError`` message naming the corpus and pinned SHA (5.1-5.3)."""
    return f"Corpus {spec.name!r} at commit {spec.sha}: {what}: {exc}"


def _fetch(url: str) -> bytes:
    """Fetch ``url`` through the module attribute ``_http_get``.

    The attribute is read at call time, so a test that replaces
    ``support.corpus._http_get`` also controls ``ensure_pinned_archive``.
    """
    return _http_get(url)


def ensure_pinned_archive(archive: Any, *, cache_root: Path = CACHE_ROOT) -> Path:
    """Ensure ``archive`` is downloaded, hash-checked, and extracted in the cache.

    ``archive`` is a ``PinnedArchive``. Delegates to
    ``scripts/pinned_archive.py``: same cache, lock, safe extraction, and atomic
    publish as ``ensure_corpus``, with the sha256 checked before extraction. A
    fetch failure or a hash mismatch raises ``CorpusError`` and publishes
    nothing. It never skips.
    """
    root: Path = _pinned.ensure_pinned_archive(
        archive, cache_root=cache_root, fetch=_fetch
    )
    return root


def _single_top_level_key(raw_bytes: bytes) -> str | None:
    """Return the sole top-level key of a JSON object document, else ``None``.

    ``None`` means the bytes are not UTF-8, not valid JSON, not a JSON object,
    or an object with zero or several top-level keys — none of which can be an
    OSCAL document. The stdlib ``json`` module has no incremental API, so the
    whole file is decoded; only the top-level keys are inspected.
    """
    try:
        value = json.loads(raw_bytes)  # accepts UTF-8 bytes directly
    except (UnicodeDecodeError, ValueError):  # JSONDecodeError is a ValueError
        return None
    if isinstance(value, dict) and len(value) == 1:
        (key,) = value
        return str(key)
    return None


def _oscal_root_key(raw_bytes: bytes) -> str | None:
    """Return the OSCAL document root key of ``raw_bytes``, else ``None``.

    The shared root-key filter (Req 2.4, 11.3): a document is kept only if it
    is a JSON object whose single top-level key is in ``OSCAL_ROOT_KEYS``.
    Invalid UTF-8/JSON, non-objects, objects with zero or several keys, and
    non-OSCAL keys (metaschema, config, ...) all yield ``None``. Used by both
    ``load_corpus_docs`` and ``load_local_corpus_docs`` so they cannot drift.
    """
    key = _single_top_level_key(raw_bytes)
    return key if key in OSCAL_ROOT_KEYS else None


def _matching_files(root: Path, globs: tuple[str, ...]) -> dict[str, Path]:
    """Map POSIX ``rel_path`` → file for every regular file matching ``globs``.

    Keyed by ``rel_path`` so a file matched by several globs appears once.
    ``Path.glob`` treats ``**`` as zero or more directories on every tested
    Python (3.11 through 3.14), so ``**/*.json`` also matches top-level files.
    Unlike a shell glob it also matches dotfiles; that is harmless here since
    non-documents are filtered by root key.
    """
    matches: dict[str, Path] = {}
    for pattern in globs:
        for path in root.glob(pattern):
            if path.is_file():
                matches.setdefault(path.relative_to(root).as_posix(), path)
    return matches


def load_corpus_docs(
    spec: CorpusSpec, *, cache_root: Path = CACHE_ROOT
) -> list[CorpusDoc]:
    """Return all documents in ``spec`` matching its include_globs, from cache.

    Calls ``ensure_corpus`` first, so a cache miss triggers the (locked, atomic)
    download and an unreachable corpus raises ``CorpusError`` (Req 5). Each
    returned ``CorpusDoc`` carries its POSIX path relative to the repo root as
    ``rel_path`` — the identifier reported in property-test failures (Req 6.4)
    — and the file's exact bytes as ``raw_bytes``. Results are de-duplicated
    across globs and sorted by ``rel_path`` so the list is deterministic.

    When ``spec.require_oscal_root`` is set, each candidate JSON file is parsed
    just far enough to inspect its top-level keys, and any file whose single
    top-level key is not in ``OSCAL_ROOT_KEYS`` is dropped — as is any file
    that is not UTF-8, not valid JSON, or not a JSON object — so only OSCAL
    documents are yielded (Req 2.4). ``root_key`` is the matched key.

    When ``require_oscal_root`` is false, every matching file is yielded
    unfiltered; ``root_key`` is its single top-level key if it has exactly one,
    and ``""`` otherwise (including for undecodable or non-object JSON).
    """
    root = ensure_corpus(spec, cache_root=cache_root)
    docs: list[CorpusDoc] = []
    for rel_path, path in sorted(_matching_files(root, spec.include_globs).items()):
        raw_bytes = path.read_bytes()
        if spec.require_oscal_root:
            root_key = _oscal_root_key(raw_bytes)
            if root_key is None:
                continue  # non-document JSON (metaschema, config, ...) — Req 2.4
        else:
            root_key = _single_top_level_key(raw_bytes)
        docs.append(
            CorpusDoc(
                corpus_name=spec.name,
                rel_path=rel_path,
                raw_bytes=raw_bytes,
                root_key=root_key or "",
            )
        )
    return docs


# Local opt-in corpus (Req 11). Holds an absolute path to one OSCAL JSON file
# or a directory of them. Unset in CI. Its documents are read in place and are
# never copied, cached, or placed anywhere under the repository (Req 11.6, 11.7).
LOCAL_CORPUS_ENV = "OSCAL_BINDINGS_LOCAL_CORPUS"

_LOCAL_CORPUS_NAME = "local"
_LOCAL_CORPUS_GLOBS: tuple[str, ...] = ("**/*.json",)


def load_local_corpus_docs(
    *, environ: Mapping[str, str] = os.environ
) -> list[CorpusDoc]:
    """Return documents from the local opt-in corpus, read in place.

    - Unset (or empty) ``LOCAL_CORPUS_ENV`` → ``[]`` (Req 11.8).
    - File → that one file; ``rel_path`` = its basename (Req 11.1, 11.5).
    - Directory → every ``**/*.json`` under it; ``rel_path`` = path relative to
      the directory, POSIX-style (Req 11.2, 11.4). Absolute user paths never
      reach test IDs or diagnostics.
    - Each candidate goes through the same OSCAL root-key filter as the remote
      corpora (``_oscal_root_key``); retained docs get ``corpus_name="local"``
      and ``root_key`` set (Req 11.3). Sorted by ``rel_path``.
    - No network, no Corpus_Cache writes, no copies (Req 11.6, 11.7).
    - Set but missing/unreadable, or zero docs after the filter → ``CorpusError``
      whose message names ``LOCAL_CORPUS_ENV`` and never includes document
      content (Req 11.11-11.13).
    """
    value = environ.get(LOCAL_CORPUS_ENV, "")
    if not value:
        return []

    source = Path(value)
    if source.is_file():
        candidates = {source.name: source}
    elif source.is_dir():
        candidates = _matching_files(source, _LOCAL_CORPUS_GLOBS)
    else:
        msg = (
            f"{LOCAL_CORPUS_ENV} is set to {value!r}, which is not an existing "
            "file or directory"
        )
        raise CorpusError(msg)

    docs: list[CorpusDoc] = []
    for rel_path, path in sorted(candidates.items()):
        try:
            raw_bytes = path.read_bytes()
        except OSError as exc:
            # ``exc`` carries only the OS error and path, never file content.
            msg = f"{LOCAL_CORPUS_ENV}: cannot read {rel_path!r}: {exc.strerror}"
            raise CorpusError(msg) from exc
        root_key = _oscal_root_key(raw_bytes)
        if root_key is None:
            continue  # not an OSCAL document — same filter as remote (Req 11.3)
        docs.append(
            CorpusDoc(
                corpus_name=_LOCAL_CORPUS_NAME,
                rel_path=rel_path,
                raw_bytes=raw_bytes,
                root_key=root_key,
            )
        )

    if not docs:
        msg = (
            f"{LOCAL_CORPUS_ENV} is set to {value!r}, but it yielded no OSCAL "
            f"documents ({len(candidates)} JSON candidate(s) checked; each must "
            "be a JSON object whose single top-level key is an OSCAL root)"
        )
        raise CorpusError(msg)
    return docs
