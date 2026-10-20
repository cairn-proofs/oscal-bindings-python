"""Fetch, hash-check, and cache a pinned ``.tar.gz`` archive.

A ``PinnedArchive`` names a ``.tar.gz`` at a fixed HTTPS URL and the sha256 of
its bytes. ``ensure_pinned_archive`` downloads it once, checks the hash before
it extracts anything, extracts it with tar-slip checks, and publishes the tree
under a cache root with an atomic rename. A cross-process file lock plus a
per-path thread lock make concurrent callers (``pytest-xdist`` workers, threads,
a codegen run next to a test run) download at most once.

The module uses the standard library only and imports nothing from ``tests/``,
so a script in ``scripts/`` can import it as a sibling module, and the test
support code can load it from its file path.
"""

from __future__ import annotations

import hashlib
import http.client
import io
import os
import shutil
import tarfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import IO


class CorpusError(RuntimeError):
    """Raised when a pinned archive or a corpus cannot be fetched or loaded.

    The message names the archive or corpus and its pin (URL, commit SHA, or
    environment variable) so a failure is reported with enough context to
    diagnose. The message never includes document content.
    """


# Marker file written into a fully-extracted cache dir. Its presence is the
# signal that the dir is complete and safe to treat as a cache hit. A partial
# or interrupted extraction never has it.
COMPLETE_MARKER = ".complete"

# HTTP fetch timeout (seconds) for a tarball request.
HTTP_TIMEOUT = 60
# The largest response body (bytes) that ``http_get`` accepts.
MAX_BYTES = 64 * 1024 * 1024

# FileLock spin-with-backoff tuning.
_LOCK_POLL_INITIAL = 0.01  # first back-off sleep (seconds)
_LOCK_POLL_MAX = 0.5  # back-off ceiling (seconds)
_LOCK_TIMEOUT = 300  # max seconds to wait for the lock before giving up
# A lock file older than this was left by a holder that died without releasing
# it (e.g. a killed worker). Far longer than any real fetch, so a live holder is
# never mistaken for a dead one.
_LOCK_STALE_AFTER = 900

# Network-layer failures that mean "the archive could not be fetched".
# ``OSError`` covers ``URLError``/``HTTPError`` (both subclass it), socket
# errors, and ``TimeoutError``; ``HTTPException`` covers protocol-level faults
# such as ``IncompleteRead`` that are not ``OSError`` subclasses.
FETCH_ERRORS: tuple[type[BaseException], ...] = (
    OSError,
    http.client.HTTPException,
)

# Failures while unpacking a downloaded tarball (corrupt/truncated archive,
# unsafe member, disk error).
EXTRACT_ERRORS: tuple[type[BaseException], ...] = (
    CorpusError,  # raised by ``check_member_safe`` for an unsafe member
    tarfile.TarError,
    EOFError,
    zlib.error,
    OSError,
)


class FileLock:
    """A cross-process, cross-thread lock backed by an exclusively-created file.

    Uses ``os.open(..., O_CREAT | O_EXCL)`` with exponential spin-with-backoff.
    Exclusive creation is atomic at the filesystem level, so it serializes
    separate interpreters on a shared filesystem and threads within one process
    alike. The first caller to create the lock file holds the lock; others spin
    until it is released, then re-check the cache. Unlike ``fcntl.flock`` this
    is portable to Windows.

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


# In-process companion to ``FileLock``: threads of one process queue on a
# ``threading.Lock`` per lock path instead of all spinning on the filesystem.
# ``FileLock`` alone is already thread-safe; this just makes waiting cheap.
_THREAD_LOCKS: dict[Path, threading.Lock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()


def thread_lock_for(path: Path) -> threading.Lock:
    """Return the process-wide ``threading.Lock`` for ``path`` (created once)."""
    with _THREAD_LOCKS_GUARD:
        return _THREAD_LOCKS.setdefault(path, threading.Lock())


class ResponseTooLargeError(OSError):
    """Raised when a response body is larger than the limit of ``http_get``.

    It is an ``OSError``, so ``FETCH_ERRORS`` reports it as a fetch failure.
    """


class HttpsOnlyRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follow a redirect only when its target URL is HTTPS.

    A redirect to any other scheme raises ``urllib.error.URLError``, an
    ``OSError``, so ``FETCH_ERRORS`` reports it as a fetch failure.
    """

    def redirect_request(  # noqa: PLR0913, PLR0917 — the base method's signature
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: http.client.HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        """Return the request for ``newurl``, or raise if it is not HTTPS."""
        if urllib.parse.urlsplit(newurl).scheme.lower() != "https":
            reason = f"refusing redirect to non-HTTPS URL {newurl!r}"
            raise urllib.error.URLError(reason)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def build_https_opener(
    *handlers: urllib.request.BaseHandler,
) -> urllib.request.OpenerDirector:
    """Return an opener that follows HTTPS redirects only.

    ``handlers`` are added to the opener, as ``urllib.request.build_opener``
    adds them. A test can pass a handler that serves fake responses.
    """
    return urllib.request.build_opener(HttpsOnlyRedirectHandler(), *handlers)


def http_get(
    url: str,
    *,
    timeout: int = HTTP_TIMEOUT,
    max_bytes: int = MAX_BYTES,
    opener: urllib.request.OpenerDirector | None = None,
) -> bytes:
    """Fetch ``url`` and return the response body as bytes (stdlib ``urllib``).

    Only an HTTPS URL is accepted, and a redirect is followed only to an HTTPS
    URL. A body of more than ``max_bytes`` bytes raises
    ``ResponseTooLargeError``. A non-2xx response raises
    ``urllib.error.HTTPError``. ``opener`` defaults to
    ``build_https_opener()``.
    """
    if not url.startswith("https://"):
        msg = f"Refusing non-HTTPS archive URL: {url!r}"
        raise ValueError(msg)
    # The scheme is https, and the opener follows https redirects only.
    request = urllib.request.Request(url, method="GET")  # noqa: S310  # nosec B310
    opener = opener or build_https_opener()
    with opener.open(request, timeout=timeout) as response:
        data = bytes(response.read(max_bytes + 1))
    if len(data) > max_bytes:
        msg = f"the response from {url!r} is larger than {max_bytes} bytes"
        raise ResponseTooLargeError(msg)
    return data


def _is_within_directory(directory: Path, target: Path) -> bool:
    """Return True if ``target`` resolves to a path inside ``directory``."""
    directory = directory.resolve()
    target = target.resolve()
    return directory == target or directory in target.parents


def check_member_safe(member: tarfile.TarInfo, *, into: Path) -> None:
    """Reject tar members that could write outside ``into`` ("tar slip").

    Rejects absolute names, ``..`` traversal, links whose target escapes
    ``into``, and device/FIFO nodes.
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


def extract_tar_gz(data: bytes, *, into: Path) -> None:
    """Extract a gzipped tarball from ``data`` into the ``into`` directory.

    Every member is validated with ``check_member_safe`` before anything is
    written, so an unsafe archive is rejected outright (the ``"data"`` filter
    alone would silently strip a leading ``/`` rather than refuse). Extraction
    then also applies ``tarfile``'s ``"data"`` filter, which additionally drops
    unsafe permission bits and ownership. A Python without the filter (3.11.0
    to 3.11.3) raises ``CorpusError`` before anything is extracted.
    """
    if not hasattr(tarfile, "data_filter"):
        msg = "this Python lacks tarfile data filters; use 3.11.4 or later"
        raise CorpusError(msg)
    into.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        members = tar.getmembers()
        for member in members:
            check_member_safe(member, into=into)
        tar.extractall(into, members=members, filter="data")


def tarball_root(extracted: Path) -> Path:
    """Return the effective content root within a freshly extracted tarball.

    When the extraction contains exactly one entry and it is a directory (the
    wrapper directory of a GitHub codeload or release archive), that directory
    is returned so callers publish it directly. Otherwise the extraction
    directory itself is returned unchanged.
    """
    entries = list(extracted.iterdir())
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return extracted


def is_complete(target: Path) -> bool:
    """Return True if ``target`` is an extracted cache dir with its marker."""
    return target.is_dir() and (target / COMPLETE_MARKER).exists()


@dataclass(frozen=True)
class PinnedArchive:
    """A .tar.gz at a fixed HTTPS URL, pinned by the sha256 of its bytes."""

    name: str
    url: str
    sha256: str
    cache_dir: str
    """Directory name under the cache root. Include the version and the hash."""


def ensure_pinned_archive(
    archive: PinnedArchive,
    *,
    cache_root: Path,
    fetch: Callable[[str], bytes] = http_get,
) -> Path:
    """Ensure ``archive`` is downloaded, hash-checked, and extracted in the cache.

    A complete cache dir is returned with no network access. Otherwise the
    archive is fetched with ``fetch`` under the archive lock, and the sha256 of
    the downloaded bytes is checked before anything is extracted. A fetch
    failure, a hash mismatch, an unsafe member, or a lock timeout raises
    ``CorpusError`` and publishes nothing. It never skips. A single top-level
    directory in the archive is stripped, so the returned path is the archive's
    content root.
    """
    target = cache_root / archive.cache_dir
    if is_complete(target):
        return target
    cache_root.mkdir(parents=True, exist_ok=True)
    lock_path = cache_root / f"{archive.cache_dir}.lock"
    with thread_lock_for(lock_path.resolve()):
        try:
            with FileLock(lock_path):
                if not is_complete(target):
                    _fetch_verify_publish(
                        archive, target=target, cache_root=cache_root, fetch=fetch
                    )
        except TimeoutError as exc:
            msg = (
                f"Archive {archive.name!r}: timed out waiting for the cache lock: {exc}"
            )
            raise CorpusError(msg) from exc
    return target


def _fetch_verify_publish(
    archive: PinnedArchive,
    *,
    target: Path,
    cache_root: Path,
    fetch: Callable[[str], bytes],
) -> None:
    """Download, hash-check, and atomically publish ``archive`` at ``target``.

    Must be called with the archive lock held.
    """
    try:
        data = fetch(archive.url)
    except FETCH_ERRORS as exc:
        msg = f"Archive {archive.name!r} at {archive.url}: fetch failed: {exc}"
        raise CorpusError(msg) from exc
    actual = hashlib.sha256(data).hexdigest()
    if actual != archive.sha256:
        msg = (
            f"Archive {archive.name!r} at {archive.url}: sha256 mismatch: "
            f"expected {archive.sha256}, got {actual}"
        )
        raise CorpusError(msg)
    tmp = cache_root / f".tmp-{archive.cache_dir}-{os.getpid()}-{threading.get_ident()}"
    try:
        if tmp.exists():
            shutil.rmtree(tmp)
        extract_tar_gz(data, into=tmp)
        root = tarball_root(tmp)
        (root / COMPLETE_MARKER).touch()
        if is_complete(target):
            return
        if target.exists():
            shutil.rmtree(target)
        root.replace(target)
    except EXTRACT_ERRORS as exc:
        msg = f"Archive {archive.name!r}: extraction failed: {exc}"
        raise CorpusError(msg) from exc
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
