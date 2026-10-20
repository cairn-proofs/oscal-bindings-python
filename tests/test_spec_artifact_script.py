"""Tests for ``scripts/spec_artifact.py`` and ``scripts/pinned_archive.py``.

The synthetic tests pass a fake ``fetch`` and a ``tmp_path`` cache, so they
never touch the network or the real cache.
"""

from __future__ import annotations

import http.client
import io
import subprocess
import sys
import tarfile
import urllib.error
import urllib.request
import urllib.response
from pathlib import Path

import pytest
from support import corpus, spec_artifact
from support.scripts import load_script

REPO_ROOT = Path(__file__).parent.parent

pin = load_script("spec_artifact")
pinned = load_script("pinned_archive")


def test_script_and_test_support_share_one_pin_and_one_cache() -> None:
    assert spec_artifact.SPEC_ARTIFACT is pin.SPEC_ARTIFACT
    assert pin.SPEC_ARTIFACT_VERSION == "0.2.0+oscal.1.2.3"
    assert pin.SPEC_ARTIFACT_SHA256 == (
        "3bc746e8a6182a612c2a8f397e0ee7a47b2d777108f93df81dcd139ee59b271e"
    )
    assert pin.CACHE_ROOT.resolve() == corpus.CACHE_ROOT.resolve()
    assert REPO_ROOT.resolve() / "tests" / ".corpus_cache" == pin.CACHE_ROOT


def test_support_reexports_the_script_classes() -> None:
    assert corpus.CorpusError is pinned.CorpusError
    assert corpus.PinnedArchive is pinned.PinnedArchive


def test_artifact_paths_are_inside_the_root(tmp_path: Path) -> None:
    paths = pin.artifact_paths(tmp_path)
    assert paths.root == tmp_path
    assert paths.schema == tmp_path / "schemas/1.2.3/oscal_complete_schema.json"
    assert paths.names == tmp_path / "manifest/1.2.3/names.json"
    assert paths.names_schema == tmp_path / "manifest/names.schema.json"
    assert paths.corpus == tmp_path / "corpus/1.2.3"


def test_ensure_spec_artifact_fetch_failure_raises(tmp_path: Path) -> None:
    def failing_fetch(_url: str) -> bytes:
        msg = "connection refused"
        raise OSError(msg)

    with pytest.raises(pinned.CorpusError, match="fetch failed") as info:
        pin.ensure_spec_artifact(cache_root=tmp_path, fetch=failing_fetch)
    assert pin.SPEC_ARTIFACT.url in str(info.value)
    assert not (tmp_path / pin.SPEC_ARTIFACT.cache_dir).exists()


def test_ensure_spec_artifact_hash_mismatch_raises(tmp_path: Path) -> None:
    with pytest.raises(pinned.CorpusError, match="sha256 mismatch"):
        pin.ensure_spec_artifact(cache_root=tmp_path, fetch=lambda _url: b"x")
    assert not (tmp_path / pin.SPEC_ARTIFACT.cache_dir).exists()


def test_ensure_spec_artifact_protocol_failure_raises(tmp_path: Path) -> None:
    """A protocol fault that is not an ``OSError`` is a fetch failure too."""

    def truncated_fetch(_url: str) -> bytes:
        partial = b"partial"
        raise http.client.IncompleteRead(partial)

    with pytest.raises(pinned.CorpusError, match="fetch failed"):
        pin.ensure_spec_artifact(cache_root=tmp_path, fetch=truncated_fetch)
    assert not (tmp_path / pin.SPEC_ARTIFACT.cache_dir).exists()


def test_ensure_spec_artifact_warm_cache_never_fetches() -> None:
    """A complete cache dir is returned without a call to ``fetch``."""
    warm = spec_artifact.ensure_spec_artifact()
    calls: list[str] = []

    def failing_fetch(url: str) -> bytes:
        calls.append(url)
        msg = "network down"
        raise OSError(msg)

    assert pin.ensure_spec_artifact(fetch=failing_fetch) == warm
    assert calls == []


def test_ensure_spec_artifact_incomplete_cache_dir_is_refetched(
    tmp_path: Path,
) -> None:
    """A cache dir without its marker (a killed run) is not trusted."""
    partial = tmp_path / pin.SPEC_ARTIFACT.cache_dir
    (partial / "manifest").mkdir(parents=True)
    calls: list[str] = []

    def failing_fetch(url: str) -> bytes:
        calls.append(url)
        msg = "network down"
        raise OSError(msg)

    with pytest.raises(pinned.CorpusError, match="fetch failed"):
        pin.ensure_spec_artifact(cache_root=tmp_path, fetch=failing_fetch)
    assert calls == [pin.SPEC_ARTIFACT.url]
    assert not pinned.is_complete(partial)


def test_http_get_refuses_non_https() -> None:
    with pytest.raises(ValueError, match="non-HTTPS"):
        pinned.http_get("http://example.com/a.tar.gz")


class _FakeHttps(urllib.request.HTTPSHandler):
    """Serve fake HTTPS responses: a redirect, or a body, per URL."""

    def __init__(self, routes: dict[str, tuple[int, str | bytes]]) -> None:
        super().__init__()
        self.routes = routes
        self.opened: list[str] = []

    def https_open(self, req: urllib.request.Request) -> urllib.response.addinfourl:
        url = req.full_url
        self.opened.append(url)
        code, value = self.routes[url]
        headers = http.client.HTTPMessage()
        body = b""
        if isinstance(value, str):
            headers["Location"] = value
        else:
            body = value
        response = urllib.response.addinfourl(io.BytesIO(body), headers, url, code)
        response.msg = "Found" if code == 302 else "OK"  # type: ignore[attr-defined]
        return response


def test_http_get_follows_an_https_redirect() -> None:
    fake = _FakeHttps(
        {
            "https://a.example/x.tar.gz": (302, "https://b.example/x.tar.gz"),
            "https://b.example/x.tar.gz": (200, b"payload"),
        }
    )
    opener = pinned.build_https_opener(fake)
    assert pinned.http_get("https://a.example/x.tar.gz", opener=opener) == b"payload"
    assert fake.opened == ["https://a.example/x.tar.gz", "https://b.example/x.tar.gz"]


def test_http_get_refuses_a_redirect_to_http() -> None:
    fake = _FakeHttps(
        {
            "https://a.example/x.tar.gz": (302, "http://b.example/x.tar.gz"),
        }
    )
    opener = pinned.build_https_opener(fake)
    with pytest.raises(urllib.error.URLError, match="non-HTTPS"):
        pinned.http_get("https://a.example/x.tar.gz", opener=opener)
    assert fake.opened == ["https://a.example/x.tar.gz"]


def test_refused_redirect_is_a_fetch_failure(tmp_path: Path) -> None:
    fake = _FakeHttps({pin.SPEC_ARTIFACT.url: (302, "http://evil.example/x.tar.gz")})
    opener = pinned.build_https_opener(fake)

    def fetch(url: str) -> bytes:
        return pinned.http_get(url, opener=opener)

    with pytest.raises(pinned.CorpusError, match=r"fetch failed.*non-HTTPS"):
        pin.ensure_spec_artifact(cache_root=tmp_path, fetch=fetch)
    assert not (tmp_path / pin.SPEC_ARTIFACT.cache_dir).exists()


def test_http_get_accepts_a_body_at_the_limit() -> None:
    fake = _FakeHttps({"https://a.example/x": (200, b"0123456789")})
    opener = pinned.build_https_opener(fake)
    assert pinned.http_get("https://a.example/x", max_bytes=10, opener=opener) == (
        b"0123456789"
    )


def test_http_get_refuses_a_body_over_the_limit(tmp_path: Path) -> None:
    fake = _FakeHttps({pin.SPEC_ARTIFACT.url: (200, b"0123456789!")})
    opener = pinned.build_https_opener(fake)
    with pytest.raises(pinned.ResponseTooLargeError, match="larger than 10 bytes"):
        pinned.http_get(pin.SPEC_ARTIFACT.url, max_bytes=10, opener=opener)

    def fetch(url: str) -> bytes:
        return pinned.http_get(url, max_bytes=10, opener=opener)

    with pytest.raises(pinned.CorpusError, match="fetch failed"):
        pin.ensure_spec_artifact(cache_root=tmp_path, fetch=fetch)


def test_default_body_limit_is_64_mib() -> None:
    assert pinned.MAX_BYTES == 64 * 1024 * 1024


def test_extract_refuses_a_python_without_data_filters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delattr(tarfile, "data_filter")
    with pytest.raises(pinned.CorpusError, match=r"3\.11\.4 or later"):
        pinned.extract_tar_gz(b"", into=tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_extract_keeps_a_safe_symlink(tmp_path: Path) -> None:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        data = b"{}"
        info = tarfile.TarInfo("root/a.json")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
        link = tarfile.TarInfo("root/b.json")
        link.type = tarfile.SYMTYPE
        link.linkname = "a.json"
        tar.addfile(link)
    pinned.extract_tar_gz(buffer.getvalue(), into=tmp_path)
    assert (tmp_path / "root" / "b.json").is_symlink()
    assert (tmp_path / "root" / "b.json").read_bytes() == b"{}"


def test_real_artifact_holds_every_path() -> None:
    paths = pin.artifact_paths(spec_artifact.ensure_spec_artifact())
    assert paths.schema.is_file()
    assert paths.names.is_file()
    assert paths.names_schema.is_file()
    assert (paths.corpus / "cases.json").is_file()


def test_runs_as_a_script_with_scripts_dir_on_sys_path() -> None:
    """``python scripts/spec_artifact.py`` resolves its sibling import."""
    spec_artifact.ensure_spec_artifact()  # warm the cache: no network below
    result = subprocess.run(  # noqa: S603 — fixed argv, no untrusted input
        [sys.executable, str(REPO_ROOT / "scripts" / "spec_artifact.py")],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT / "src",
    )
    assert result.returncode == 0, result.stderr
    corpus_dir = pin.artifact_paths(spec_artifact.ensure_spec_artifact()).corpus
    assert f"corpus: {corpus_dir}" in result.stdout
