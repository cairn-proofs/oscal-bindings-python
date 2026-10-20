"""Tests for ``scripts/spec_artifact.py`` and ``scripts/pinned_archive.py``.

The synthetic tests pass a fake ``fetch`` and a ``tmp_path`` cache, so they
never touch the network or the real cache.
"""

from __future__ import annotations

import subprocess
import sys
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


def test_http_get_refuses_non_https() -> None:
    with pytest.raises(ValueError, match="non-HTTPS"):
        pinned.http_get("http://example.com/a.tar.gz")


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
