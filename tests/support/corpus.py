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
"""

from __future__ import annotations

import http.client
import io
import json
import os
import shutil
import tarfile
import threading
import time
import urllib.request
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    from collections.abc import Mapping

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


class CorpusError(RuntimeError):
    """Raised when a corpus cannot be fetched or loaded.

    For a remote corpus the message always includes the corpus name and the
    pinned commit SHA so an unreachable corpus is reported with enough context
    to diagnose (Req 5.1-5.3). For the local corpus it names
    ``LOCAL_CORPUS_ENV`` and never includes document content (Req 11.11-11.13).
    """


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


# Marker file written into a fully-extracted cache dir. Its presence is the
# signal that the dir is complete and safe to treat as a cache hit (Req 3.2,
# 4.2) — a partial/interrupted extraction never has it.
_COMPLETE_MARKER = ".complete"

# HTTP fetch timeout (seconds) for the codeload tarball request.
_HTTP_TIMEOUT = 60

# FileLock spin-with-backoff tuning.
_LOCK_POLL_INITIAL = 0.01  # first back-off sleep (seconds)
_LOCK_POLL_MAX = 0.5  # back-off ceiling (seconds)
_LOCK_TIMEOUT = 300  # max seconds to wait for the lock before giving up
# A lock file older than this was left by a holder that died without releasing
# it (e.g. a killed worker). Far longer than any real fetch, so a live holder is
# never mistaken for a dead one.
_LOCK_STALE_AFTER = 900

# Network-layer failures that mean "the corpus could not be fetched" (Req 5).
# ``OSError`` covers ``URLError``/``HTTPError`` (both subclass it), socket
# errors, and ``TimeoutError``; ``HTTPException`` covers protocol-level faults
# such as ``IncompleteRead`` that are not ``OSError`` subclasses.
_FETCH_ERRORS: tuple[type[BaseException], ...] = (
    OSError,
    http.client.HTTPException,
)

# Failures while unpacking a downloaded tarball (corrupt/truncated archive,
# unsafe member, disk error). Surfaced as ``CorpusError`` with name + SHA too.
_EXTRACT_ERRORS: tuple[type[BaseException], ...] = (
    CorpusError,  # raised by ``_check_member_safe`` for an unsafe member
    tarfile.TarError,
    EOFError,
    zlib.error,
    OSError,
)


class _FileLock:
    """A cross-process, cross-thread lock backed by an exclusively-created file.

    Uses ``os.open(..., O_CREAT | O_EXCL)`` with exponential spin-with-backoff.
    Exclusive creation is atomic at the filesystem level, so it serializes
    ``pytest-xdist`` worker processes (separate interpreters, shared filesystem)
    and threads within one process alike. The first caller to create the lock
    file holds the lock; others spin until it is released, then re-check the
    cache (Req 4.1). Unlike ``fcntl.flock`` this is portable to Windows.

    A lock file older than ``stale_after`` is treated as abandoned by a dead
    holder and removed, so a crashed run cannot wedge every later run.
    """

    def __init__(
        self,
        path: Path,
        *,
        timeout: float = _LOCK_TIMEOUT,
        stale_after: float = _LOCK_STALE_AFTER,
    ) -> None:
        self._path = path
        self._timeout = timeout
        self._stale_after = stale_after
        self._fd: int | None = None

    def __enter__(self) -> Self:
        deadline = time.monotonic() + self._timeout
        delay = _LOCK_POLL_INITIAL
        while True:
            try:
                self._fd = os.open(self._path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                if self._break_if_stale():
                    continue  # retry immediately — the stale lock is gone
                if time.monotonic() >= deadline:
                    msg = (
                        f"Timed out after {self._timeout}s waiting for lock "
                        f"{self._path}"
                    )
                    raise TimeoutError(msg) from None
                time.sleep(delay)
                delay = min(delay * 2, _LOCK_POLL_MAX)
            else:
                # Record the holder for anyone debugging a leftover lock file.
                os.write(self._fd, f"{os.getpid()}:{threading.get_ident()}\n".encode())
                return self

    def __exit__(self, *_exc: object) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        self._path.unlink(missing_ok=True)

    def _break_if_stale(self) -> bool:
        """Remove the lock file if its holder has evidently died.

        Returns True if a stale lock was removed (or vanished meanwhile).
        """
        try:
            age = time.time() - self._path.stat().st_mtime
        except FileNotFoundError:
            return True  # released between our O_EXCL attempt and the stat
        if age < self._stale_after:
            return False
        self._path.unlink(missing_ok=True)
        return True


# In-process companion to ``_FileLock``: threads of one process queue on a
# ``threading.Lock`` per lock path instead of all spinning on the filesystem.
# ``_FileLock`` alone is already thread-safe; this just makes waiting cheap.
_THREAD_LOCKS: dict[Path, threading.Lock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()


def _thread_lock_for(path: Path) -> threading.Lock:
    """Return the process-wide ``threading.Lock`` for ``path`` (created once)."""
    with _THREAD_LOCKS_GUARD:
        return _THREAD_LOCKS.setdefault(path, threading.Lock())


def _http_get(url: str, *, timeout: int = _HTTP_TIMEOUT) -> bytes:
    """Fetch ``url`` and return the response body as bytes (stdlib ``urllib``).

    No third-party HTTP client is used — only ``pydantic`` is a runtime
    dependency, and stdlib ``urllib.request`` covers an HTTPS GET of a tarball.
    Non-2xx responses raise ``urllib.error.HTTPError`` from ``urlopen``.
    """
    if not url.startswith("https://"):
        msg = f"Refusing non-HTTPS corpus URL: {url!r}"
        raise ValueError(msg)
    request = urllib.request.Request(url, method="GET")  # noqa: S310 — https checked
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return bytes(response.read())


def _is_within_directory(directory: Path, target: Path) -> bool:
    """Return True if ``target`` resolves to a path inside ``directory``."""
    directory = directory.resolve()
    target = target.resolve()
    return directory == target or directory in target.parents


def _check_member_safe(member: tarfile.TarInfo, *, into: Path) -> None:
    """Reject tar members that could write outside ``into`` ("tar slip").

    Used as the fallback on Python builds whose ``tarfile`` lacks extraction
    filters (3.11 before 3.11.4). Rejects absolute names, ``..`` traversal,
    links whose target escapes ``into``, and device/FIFO nodes.
    """
    name = member.name
    unsafe = (
        Path(name).is_absolute()
        or ".." in Path(name).parts
        or not _is_within_directory(into, into / name)
        or member.isdev()
    )
    if not unsafe and member.issym():
        link_target = (into / name).parent / member.linkname
        unsafe = Path(member.linkname).is_absolute() or not _is_within_directory(
            into, link_target
        )
    if not unsafe and member.islnk():
        unsafe = Path(member.linkname).is_absolute() or not _is_within_directory(
            into, into / member.linkname
        )
    if unsafe:
        msg = f"Refusing to extract unsafe tar member: {name!r}"
        raise CorpusError(msg)


def _extract_tar_gz(data: bytes, *, into: Path) -> None:
    """Extract a gzipped tarball from ``data`` into the ``into`` directory.

    Every member is validated with ``_check_member_safe`` before anything is
    written, so an unsafe archive is rejected outright (the ``"data"`` filter
    alone would silently strip a leading ``/`` rather than refuse). Extraction
    then also applies ``tarfile``'s ``"data"`` filter where available (3.12 and
    3.11.4+), which additionally drops unsafe permission bits and ownership.
    """
    into.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        members = tar.getmembers()
        for member in members:
            _check_member_safe(member, into=into)
        if hasattr(tarfile, "data_filter"):
            tar.extractall(into, members=members, filter="data")
        else:  # pragma: no cover — only on Python 3.11.0-3.11.3
            tar.extractall(into, members=members)  # noqa: S202 — validated above


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


def _tarball_root(extracted: Path) -> Path:
    """Return the effective repo root within a freshly extracted tarball.

    GitHub codeload archives wrap the entire tree in a single top-level
    directory named ``{repo}-{sha}``. When the extraction contains exactly one
    entry and it is a directory, that directory is the repo root and is returned
    so callers publish it directly (stripping the wrapper). Otherwise the
    extraction directory itself is returned unchanged.
    """
    entries = list(extracted.iterdir())
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return extracted


def _is_complete(target: Path) -> bool:
    """Return True if ``target`` is an extracted cache dir with its marker."""
    return target.is_dir() and (target / _COMPLETE_MARKER).exists()


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
    ``Path.glob`` treats ``**`` as zero or more directories on 3.11 and 3.12
    alike, so ``**/*.json`` also matches top-level files. Unlike a shell glob
    it also matches dotfiles; that is harmless here since non-documents are
    filtered by root key.
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
