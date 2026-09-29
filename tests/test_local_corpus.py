"""Example tests for the local opt-in corpus loader (Req 11).

Every case builds tiny synthetic OSCAL / non-OSCAL JSON under ``tmp_path``; no
test touches a real local document.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from hypothesis.vendor.pretty import pretty
from support import corpus
from support.corpus import (
    LOCAL_CORPUS_ENV,
    CorpusDoc,
    CorpusError,
    load_local_corpus_docs,
)

_CONTENT_MARKER = "confidential-marker-7f3a"


def _write_json(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _oscal(root_key: str) -> dict[str, object]:
    return {root_key: {"uuid": "00000000-0000-4000-8000-000000000000"}}


def test_unset_yields_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Req 11.8."""
    monkeypatch.delenv(LOCAL_CORPUS_ENV, raising=False)
    assert load_local_corpus_docs() == []
    assert load_local_corpus_docs(environ={LOCAL_CORPUS_ENV: ""}) == []


def test_single_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Req 11.1, 11.3, 11.5."""
    path = _write_json(tmp_path / "mc.json", _oscal("mapping-collection"))
    monkeypatch.setenv(LOCAL_CORPUS_ENV, str(path))

    (doc,) = load_local_corpus_docs()

    assert doc.corpus_name == "local"
    assert doc.root_key == "mapping-collection"
    assert doc.rel_path == "mc.json"
    assert doc.raw_bytes == path.read_bytes()


def test_directory_filters_and_relativizes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Req 11.2, 11.3, 11.4."""
    root = tmp_path / "local"
    _write_json(root / "top.json", _oscal("catalog"))
    _write_json(root / "nested" / "deep" / "mc.json", _oscal("mapping-collection"))
    _write_json(root / "nested" / "config.json", {"not-oscal": 1})
    _write_json(root / "two-keys.json", {"catalog": {}, "profile": {}})
    (root / "broken.json").write_text("{not json", encoding="utf-8")
    _write_json(root / "ignored.txt", _oscal("profile"))  # not *.json
    monkeypatch.setenv(LOCAL_CORPUS_ENV, str(root))

    docs = load_local_corpus_docs()

    assert [(d.rel_path, d.root_key) for d in docs] == [
        ("nested/deep/mc.json", "mapping-collection"),
        ("top.json", "catalog"),
    ]
    assert all(d.corpus_name == "local" for d in docs)


def test_rel_paths_never_leak_configured_root(tmp_path: Path) -> None:
    """Req 11.4, 11.5."""
    root = tmp_path / "local"
    single = _write_json(root / "a" / "one.json", _oscal("profile"))
    _write_json(root / "b.json", _oscal("catalog"))

    docs = [
        *load_local_corpus_docs(environ={LOCAL_CORPUS_ENV: str(root)}),
        *load_local_corpus_docs(environ={LOCAL_CORPUS_ENV: str(single)}),
    ]

    assert len(docs) == 3
    for doc in docs:
        assert not Path(doc.rel_path).is_absolute()
        assert str(root) not in doc.rel_path
        assert str(tmp_path) not in doc.rel_path


def test_missing_path_raises(tmp_path: Path) -> None:
    """Req 11.11."""
    missing = tmp_path / "does-not-exist.json"
    with pytest.raises(CorpusError, match=LOCAL_CORPUS_ENV):
        load_local_corpus_docs(environ={LOCAL_CORPUS_ENV: str(missing)})


@pytest.mark.parametrize("as_dir", [False, True], ids=["file", "directory"])
def test_no_oscal_docs_raises_without_content(tmp_path: Path, *, as_dir: bool) -> None:
    """Req 11.12, 11.13."""
    content = {_CONTENT_MARKER: _CONTENT_MARKER}
    path = _write_json(tmp_path / "src" / "data.json", content)
    target = path.parent if as_dir else path

    with pytest.raises(CorpusError, match=LOCAL_CORPUS_ENV) as excinfo:
        load_local_corpus_docs(environ={LOCAL_CORPUS_ENV: str(target)})

    assert _CONTENT_MARKER not in str(excinfo.value)


def test_no_network_and_no_cache_writes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Req 11.6, 11.7."""

    def _no_network(*_args: object, **_kwargs: object) -> bytes:
        msg = "network access attempted"
        raise AssertionError(msg)

    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    monkeypatch.setattr(corpus, "_http_get", _no_network)
    monkeypatch.setattr(corpus, "CACHE_ROOT", cache_root)
    root = tmp_path / "local"
    _write_json(root / "x.json", _oscal("catalog"))
    before = sorted(p.relative_to(root) for p in root.rglob("*"))

    docs = load_local_corpus_docs(environ={LOCAL_CORPUS_ENV: str(root)})

    assert len(docs) == 1
    assert list(cache_root.iterdir()) == []
    assert sorted(p.relative_to(root) for p in root.rglob("*")) == before


def test_repr_excludes_raw_bytes() -> None:
    """``raw_bytes`` is ``repr=False`` so failing examples never print content."""
    doc = CorpusDoc(
        corpus_name="local",
        rel_path="mc.json",
        raw_bytes=_CONTENT_MARKER.encode(),
        root_key="mapping-collection",
    )
    # Hypothesis prints failing examples with its own pretty-printer, which
    # ignores ``repr=False`` on dataclass fields; check both paths.
    for text in (repr(doc), pretty([doc])):
        assert _CONTENT_MARKER not in text
        assert "raw_bytes" not in text
        assert "mc.json" in text
        assert "mapping-collection" in text
