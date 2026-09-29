"""Corpus_Fetcher — pin, fetch, cache, and expose remote OSCAL corpora.

This module provides the core data structures and pinned specifications for the
two remote OSCAL corpora that seed the corpus-driven property tests:

- **NIST** ``usnistgov/oscal-content`` — example documents for all 8 OSCAL types.
- **AWS** ``awslabs/oscal-content-for-aws-services`` — component definitions.

Both corpora are pinned to a specific commit SHA so the test input set is
reproducible over time. Documents are fetched once as a codeload tarball per
pinned SHA, extracted into a git-ignored cache under ``tests/.corpus_cache``,
and reused across runs and across parallel workers.

Fetch/cache logic (``ensure_corpus``) is implemented here with atomic,
concurrency-safe extraction. Load/filter logic (``load_corpus_docs``) is
implemented in a later task.
"""

from __future__ import annotations

import io
import os
import shutil
import tarfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Self

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
    """Raised when a corpus cannot be fetched.

    The message always includes the corpus name and the pinned commit SHA so an
    unreachable corpus is reported with enough context to diagnose (Req 5.1-5.3).
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
    raw_bytes: bytes
    """The document as bytes — drives str/bytes equivalence (Req 6.3)."""
    root_key: str
    """The single top-level OSCAL key (in ``OSCAL_ROOT_KEYS``).

    Drives AP/AR partitioning.
    """


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
_LOCK_POLL_INTERVAL = 0.05  # seconds between acquisition attempts
_LOCK_TIMEOUT = 300  # max seconds to wait for the lock before giving up


class _FileLock:
    """A cross-process advisory lock backed by an exclusively-created file.

    Uses ``os.open(..., O_CREAT | O_EXCL)`` with spin-with-backoff so it works
    across ``pytest-xdist`` worker processes (separate interpreters, shared
    filesystem). The first worker to create the lock file holds the lock;
    others spin until it is released, then re-check the cache (Req 4.1).
    """

    def __init__(self, path: Path, *, timeout: float = _LOCK_TIMEOUT) -> None:
        self._path = path
        self._timeout = timeout
        self._fd: int | None = None

    def __enter__(self) -> Self:
        deadline = time.monotonic() + self._timeout
        while True:
            try:
                self._fd = os.open(self._path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                if time.monotonic() >= deadline:
                    msg = (
                        f"Timed out after {self._timeout}s waiting for lock "
                        f"{self._path}"
                    )
                    raise TimeoutError(msg) from None
                time.sleep(_LOCK_POLL_INTERVAL)
            else:
                return self

    def __exit__(self, *_exc: object) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        # Best-effort cleanup — a leftover lock file is harmless (the next
        # acquirer will still be able to O_EXCL-create it once it is gone).
        self._path.unlink(missing_ok=True)


def _http_get(url: str, *, timeout: int = _HTTP_TIMEOUT) -> bytes:
    """Fetch ``url`` and return the response body as bytes (stdlib ``urllib``).

    No third-party HTTP client is used — only ``pydantic`` is a runtime
    dependency, and stdlib ``urllib.request`` covers an HTTPS GET of a tarball.
    """
    request = urllib.request.Request(url, method="GET")  # noqa: S310 — https codeload URL
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return response.read()


def _is_within_directory(directory: Path, target: Path) -> bool:
    """Return True if ``target`` resolves to a path inside ``directory``."""
    directory = directory.resolve()
    target = target.resolve()
    return directory == target or directory in target.parents


def _extract_tar_gz(data: bytes, *, into: Path) -> None:
    """Extract a gzipped tarball from ``data`` into the ``into`` directory.

    Guards against path-traversal ("tar slip") entries so a malicious or
    corrupt archive cannot write outside ``into``.
    """
    into.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for member in tar.getmembers():
            member_path = into / member.name
            if not _is_within_directory(into, member_path):
                msg = (
                    "Refusing to extract unsafe tar member outside target dir: "
                    f"{member.name!r}"
                )
                raise CorpusError(msg)
        # ``filter="data"`` (available on 3.11.4+/3.12) strips unsafe metadata
        # and blocks traversal; the explicit check above is a belt-and-braces
        # guard for older patch releases where the filter is unavailable.
        try:
            tar.extractall(into, filter="data")  # type: ignore[call-arg]
        except TypeError:
            tar.extractall(into)  # noqa: S202 — members validated above


def ensure_corpus(spec: CorpusSpec, *, cache_root: Path = CACHE_ROOT) -> Path:
    """Ensure the corpus tree for ``spec.sha`` is extracted under the cache.

    Cache-hit (Req 3.2): if the extracted ``{repo}-{sha}`` dir exists and carries
    its ``.complete`` marker, return it with no network access. Cache-miss
    (Req 3.1): download the tarball at the pinned SHA, extract it atomically,
    and return the dir.

    Concurrency-safe (Req 4): a per-corpus file lock serializes concurrent
    workers so the download happens at most once (Req 4.1); extraction goes to a
    per-PID temp dir published with an atomic ``os.replace`` so no worker ever
    observes a partial tree (Req 4.2) and every worker reads identical content
    (Req 4.3).

    Raises ``CorpusError`` (with the corpus name and pinned SHA) if the fetch
    fails and no cached copy exists (Req 5.1-5.3).
    """
    target = cache_root / f"{spec.repo}-{spec.sha}"
    if _is_complete(target):  # Req 3.2 — cache hit, no network
        return target

    cache_root.mkdir(parents=True, exist_ok=True)
    lock_path = cache_root / f"{spec.repo}-{spec.sha}.lock"
    with _FileLock(lock_path):
        # Re-check under the lock: a worker that lost the race finds the tree
        # already published and returns it without downloading (Req 4.1).
        if _is_complete(target):
            return target

        try:
            data = _http_get(spec.tarball_url)  # Req 3.1 — download at pinned SHA
        except (
            urllib.error.URLError,
            urllib.error.HTTPError,
            TimeoutError,
            OSError,
        ) as exc:
            # Req 5.1/5.2/5.3 — name + pinned SHA in the message
            msg = f"Failed to fetch corpus {spec.name!r} at commit {spec.sha}: {exc}"
            raise CorpusError(msg) from exc

        tmp = cache_root / f".tmp-{spec.repo}-{spec.sha}-{os.getpid()}"
        if tmp.exists():  # leftover from a prior interrupted run
            shutil.rmtree(tmp)
        try:
            _extract_tar_gz(data, into=tmp)
            # codeload tarballs wrap the whole repo tree in a single top-level
            # directory named ``{repo}-{sha}``. Strip it so the published cache
            # dir exposes the repo root directly and ``include_globs`` such as
            # ``component-definitions/**/*.json`` match as written (Req 2.3).
            root = _tarball_root(tmp)
            (root / _COMPLETE_MARKER).touch()  # mark complete before publishing
            # Atomic publish — no worker ever reads a half-extracted tree
            # (Req 4.2). If another worker won the race between the re-check and
            # here, the tree is already published, so reuse it instead of
            # replacing over the existing dir.
            if _is_complete(target):
                return target
            root.replace(target)
        finally:
            if tmp.exists():
                shutil.rmtree(tmp, ignore_errors=True)
    return target


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


def load_corpus_docs(
    spec: CorpusSpec, *, cache_root: Path = CACHE_ROOT
) -> list[CorpusDoc]:
    """Return all documents in ``spec`` matching its include_globs, from cache.

    When ``spec.require_oscal_root`` is set, each candidate JSON file is parsed
    just far enough to inspect its top-level keys, and any file whose single
    top-level key is not in ``OSCAL_ROOT_KEYS`` is dropped, so only parseable
    OSCAL documents are yielded (Req 2.4).

    Implemented in task 2.3.
    """
    msg = "load_corpus_docs is implemented in task 2.3"
    raise NotImplementedError(msg)
