"""Tests for the pinned spec artifact fetch (``tests/support/spec_artifact.py``).

The synthetic tests serve an in-memory tarball through a monkeypatched
``_http_get`` and a ``tmp_path`` cache, so they never touch the network or the
real cache. The last test fetches the real artifact through the real cache
(network on the first run only).
"""

from __future__ import annotations

import hashlib
import io
import tarfile

import pytest
from support import corpus
from support.corpus import CorpusError, PinnedArchive, ensure_pinned_archive
from support.spec_artifact import (
    OSCAL_RELEASE,
    SPEC_ARTIFACT,
    SPEC_ARTIFACT_VERSION,
    corpus_root,
    ensure_spec_artifact,
)


def _tarball(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for rel, data in files.items():
            info = tarfile.TarInfo(rel)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


PAYLOAD = _tarball({"pkg-1.0/VERSION": b"1.0\n", "pkg-1.0/data/a.json": b"{}"})
ARCHIVE = PinnedArchive(
    name="synthetic archive",
    url="https://example.com/pkg-1.0.tar.gz",
    sha256=hashlib.sha256(PAYLOAD).hexdigest(),
    cache_dir="pkg-1.0-test",
)


class _CountingGet:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.urls: list[str] = []

    def __call__(self, url: str, **_kwargs: object) -> bytes:
        self.urls.append(url)
        return self.payload


def test_cache_miss_fetches_checks_and_strips_wrapper(tmp_path, monkeypatch):
    fake_get = _CountingGet(PAYLOAD)
    monkeypatch.setattr(corpus, "_http_get", fake_get)
    root = ensure_pinned_archive(ARCHIVE, cache_root=tmp_path)
    assert fake_get.urls == [ARCHIVE.url]
    assert root == tmp_path / ARCHIVE.cache_dir
    assert (root / "VERSION").read_bytes() == b"1.0\n"
    assert (root / "data" / "a.json").exists()


def test_cache_hit_makes_no_network_call(tmp_path, monkeypatch):
    fake_get = _CountingGet(PAYLOAD)
    monkeypatch.setattr(corpus, "_http_get", fake_get)
    first = ensure_pinned_archive(ARCHIVE, cache_root=tmp_path)
    assert ensure_pinned_archive(ARCHIVE, cache_root=tmp_path) == first
    assert len(fake_get.urls) == 1


def test_hash_mismatch_raises_and_publishes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(corpus, "_http_get", _CountingGet(PAYLOAD + b"tampered"))
    with pytest.raises(CorpusError, match="sha256 mismatch") as info:
        ensure_pinned_archive(ARCHIVE, cache_root=tmp_path)
    assert ARCHIVE.sha256 in str(info.value)
    assert not (tmp_path / ARCHIVE.cache_dir).exists()
    assert [p.name for p in tmp_path.iterdir() if p.name.startswith(".tmp-")] == []


def test_fetch_failure_raises_with_the_url(tmp_path, monkeypatch):
    def failing_get(_url: str, **_kwargs: object) -> bytes:
        msg = "connection refused"
        raise OSError(msg)

    monkeypatch.setattr(corpus, "_http_get", failing_get)
    with pytest.raises(CorpusError, match="fetch failed") as info:
        ensure_pinned_archive(ARCHIVE, cache_root=tmp_path)
    assert ARCHIVE.url in str(info.value)
    assert not issubclass(CorpusError, pytest.skip.Exception)


def test_unsafe_member_raises(tmp_path, monkeypatch):
    payload = _tarball({"../escape.json": b"{}"})
    archive = PinnedArchive(
        name="unsafe",
        url="https://example.com/unsafe.tar.gz",
        sha256=hashlib.sha256(payload).hexdigest(),
        cache_dir="unsafe",
    )
    monkeypatch.setattr(corpus, "_http_get", _CountingGet(payload))
    with pytest.raises(CorpusError, match="extraction failed"):
        ensure_pinned_archive(archive, cache_root=tmp_path)
    assert not (tmp_path.parent / "escape.json").exists()


def test_pin_is_consistent():
    assert SPEC_ARTIFACT.url.startswith("https://")
    assert "%2B" in SPEC_ARTIFACT.url
    assert "+" not in SPEC_ARTIFACT.url
    assert SPEC_ARTIFACT_VERSION in SPEC_ARTIFACT.cache_dir
    assert SPEC_ARTIFACT.sha256[:12] in SPEC_ARTIFACT.cache_dir
    assert OSCAL_RELEASE == "1.2.3"


def test_real_artifact_is_fetched_and_complete():
    """Task 1.2: the pinned artifact holds the corpus index and its version."""
    root = ensure_spec_artifact()
    assert (root / "VERSION").read_text().strip() == SPEC_ARTIFACT_VERSION
    assert (corpus_root() / "cases.json").is_file()
