"""Example/edge tests for the Corpus_Fetcher in ``tests/support/corpus.py``.

Synthetic tests drive ``ensure_corpus``/``load_corpus_docs`` against an
in-memory tarball under ``tmp_path`` with ``_http_get`` monkeypatched, so they
never touch the network or the real cache. The pinned-corpus tests at the end
use the real NIST/AWS corpora through the real cache (network on first run).
"""

from __future__ import annotations

import io
import json
import re
import subprocess
import tarfile
import threading
import time
from pathlib import Path

import pytest
from support import corpus
from support.corpus import (
    AWS_CORPUS,
    CACHE_ROOT,
    NIST_CORPUS,
    CorpusError,
    CorpusSpec,
    ensure_corpus,
    load_corpus_docs,
)

REPO_ROOT = Path(__file__).parent.parent

SYNTH_SPEC = CorpusSpec(
    name="synthetic corpus",
    owner="example",
    repo="synthetic",
    sha="0123456789abcdef0123456789abcdef01234567",
    include_globs=("docs/**/*.json",),
)

CATALOG_JSON = json.dumps({"catalog": {"uuid": "x"}}).encode()
PROFILE_JSON = json.dumps({"profile": {"uuid": "y"}}).encode()
NON_OSCAL_JSON = json.dumps({"metaschema": {}}).encode()

# The 7 OSCAL document types the pinned NIST corpus publishes (Req 2.4).
NIST_PUBLISHED_ROOT_KEYS = frozenset(
    {
        "catalog",
        "profile",
        "component-definition",
        "system-security-plan",
        "assessment-plan",
        "assessment-results",
        "plan-of-action-and-milestones",
    }
)

SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _make_tarball(spec: CorpusSpec) -> bytes:
    """Build a codeload-style tar.gz: one ``{repo}-{sha}/`` wrapper directory."""
    files = {
        "docs/catalog.json": CATALOG_JSON,
        "docs/nested/profile.json": PROFILE_JSON,
        "docs/metaschema.json": NON_OSCAL_JSON,
        "outside/catalog.json": CATALOG_JSON,  # excluded by include_globs
    }
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for rel, data in files.items():
            info = tarfile.TarInfo(f"{spec.repo}-{spec.sha}/{rel}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class _CountingGet:
    """``_http_get`` stand-in that serves a tarball and counts calls."""

    def __init__(self, payload: bytes, *, delay: float = 0.0) -> None:
        self.payload = payload
        self.delay = delay
        self.urls: list[str] = []
        self._lock = threading.Lock()

    def __call__(self, url: str, **_kwargs: object) -> bytes:
        with self._lock:
            self.urls.append(url)
        if self.delay:
            time.sleep(self.delay)  # widen the race window for concurrency tests
        return self.payload


# --- Req 3.1, 3.2: cache miss downloads and stores; cache hit skips network ---


def test_cache_miss_downloads_and_stores(tmp_path, monkeypatch):
    fake_get = _CountingGet(_make_tarball(SYNTH_SPEC))
    monkeypatch.setattr(corpus, "_http_get", fake_get)

    target = ensure_corpus(SYNTH_SPEC, cache_root=tmp_path)

    assert fake_get.urls == [SYNTH_SPEC.tarball_url]
    assert target == tmp_path / f"{SYNTH_SPEC.repo}-{SYNTH_SPEC.sha}"
    assert (target / ".complete").is_file()
    # Wrapper dir stripped: the repo root is published directly.
    assert (target / "docs" / "catalog.json").read_bytes() == CATALOG_JSON
    # No temp dirs or lock files left behind.
    assert sorted(p.name for p in tmp_path.iterdir()) == [target.name]


def test_cache_hit_returns_without_network(tmp_path, monkeypatch):
    monkeypatch.setattr(corpus, "_http_get", _CountingGet(_make_tarball(SYNTH_SPEC)))
    first = ensure_corpus(SYNTH_SPEC, cache_root=tmp_path)

    calls: list[str] = []

    def raising_get(url: str, **_kwargs: object) -> bytes:
        calls.append(url)
        msg = "network must not be used on a cache hit"
        raise OSError(msg)

    monkeypatch.setattr(corpus, "_http_get", raising_get)

    assert ensure_corpus(SYNTH_SPEC, cache_root=tmp_path) == first
    docs = load_corpus_docs(SYNTH_SPEC, cache_root=tmp_path)
    assert calls == []
    assert [d.rel_path for d in docs] == [
        "docs/catalog.json",
        "docs/nested/profile.json",
    ]


def test_load_corpus_docs_filters_by_glob_and_root_key(tmp_path, monkeypatch):
    monkeypatch.setattr(corpus, "_http_get", _CountingGet(_make_tarball(SYNTH_SPEC)))

    docs = load_corpus_docs(SYNTH_SPEC, cache_root=tmp_path)

    by_path = {d.rel_path: d for d in docs}
    assert set(by_path) == {"docs/catalog.json", "docs/nested/profile.json"}
    assert by_path["docs/catalog.json"].root_key == "catalog"
    assert by_path["docs/catalog.json"].raw_bytes == CATALOG_JSON
    assert by_path["docs/nested/profile.json"].root_key == "profile"
    assert all(d.corpus_name == SYNTH_SPEC.name for d in docs)


# --- Req 3.3: cache dir is git-ignored ---


def test_cache_dir_is_gitignored():
    assert CACHE_ROOT.resolve() == (REPO_ROOT / "tests" / ".corpus_cache").resolve()
    probe = "tests/.corpus_cache/some-repo-sha/doc.json"
    # --no-index: judge by .gitignore patterns alone, independent of the index.
    result = subprocess.run(  # noqa: S603 — fixed argv, no untrusted input
        ["git", "check-ignore", "--no-index", "-q", probe],  # noqa: S607
        cwd=REPO_ROOT,
        check=False,
    )
    assert result.returncode == 0, f"{probe} is not covered by .gitignore"


# --- Req 4.1-4.3: concurrent callers download at most once, identical content ---


def test_concurrent_requests_download_once(tmp_path, monkeypatch):
    fake_get = _CountingGet(_make_tarball(SYNTH_SPEC), delay=0.2)
    monkeypatch.setattr(corpus, "_http_get", fake_get)

    n_threads = 8
    barrier = threading.Barrier(n_threads)
    results: list[dict[str, bytes]] = []
    errors: list[BaseException] = []
    results_lock = threading.Lock()

    def worker() -> None:
        try:
            barrier.wait()
            docs = load_corpus_docs(SYNTH_SPEC, cache_root=tmp_path)
            snapshot = {d.rel_path: d.raw_bytes for d in docs}
            with results_lock:
                results.append(snapshot)
        except BaseException as exc:  # surfaced via the errors assertion below
            with results_lock:
                errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    assert errors == []
    assert len(fake_get.urls) == 1  # Req 4.1
    assert len(results) == n_threads
    assert all(r == results[0] for r in results)  # Req 4.3
    assert results[0] == {
        "docs/catalog.json": CATALOG_JSON,
        "docs/nested/profile.json": PROFILE_JSON,
    }  # complete, not partial (Req 4.2)
    target = tmp_path / f"{SYNTH_SPEC.repo}-{SYNTH_SPEC.sha}"
    assert sorted(p.name for p in tmp_path.iterdir()) == [target.name]


# --- Req 5.1-5.4: unreachable corpus with empty cache is a hard failure ---


@pytest.mark.parametrize("spec", [NIST_CORPUS, AWS_CORPUS], ids=["nist", "aws"])
def test_fetch_failure_raises_corpus_error(spec, tmp_path, monkeypatch):
    def failing_get(_url: str, **_kwargs: object) -> bytes:
        msg = "simulated network outage"
        raise OSError(msg)

    monkeypatch.setattr(corpus, "_http_get", failing_get)
    cache_root = tmp_path / "empty-cache"

    with pytest.raises(CorpusError) as excinfo:
        load_corpus_docs(spec, cache_root=cache_root)

    message = str(excinfo.value)
    assert spec.name in message
    assert spec.sha in message
    # Nothing was published to the cache.
    assert not (cache_root / f"{spec.repo}-{spec.sha}").exists()


def test_corpus_error_is_failure_not_skip():
    # A skip is signalled by pytest's Skipped (a BaseException); CorpusError
    # must be an ordinary Exception so pytest reports it as an error/failure.
    assert issubclass(CorpusError, Exception)
    assert not issubclass(CorpusError, pytest.skip.Exception)


def test_corrupt_tarball_raises_corpus_error(tmp_path, monkeypatch):
    monkeypatch.setattr(corpus, "_http_get", _CountingGet(b"not a tarball"))

    with pytest.raises(CorpusError) as excinfo:
        ensure_corpus(SYNTH_SPEC, cache_root=tmp_path)

    assert SYNTH_SPEC.name in str(excinfo.value)
    assert SYNTH_SPEC.sha in str(excinfo.value)
    assert not (tmp_path / f"{SYNTH_SPEC.repo}-{SYNTH_SPEC.sha}").exists()


# --- Req 2.1-2.4: pinning and scope (real pinned corpora via the real cache) ---


@pytest.mark.parametrize("spec", [NIST_CORPUS, AWS_CORPUS], ids=["nist", "aws"])
def test_pinned_sha_is_full_commit(spec):
    assert SHA_RE.fullmatch(spec.sha), spec.sha
    assert spec.tarball_url.endswith(f"/tar.gz/{spec.sha}")


def test_aws_docs_are_component_definitions_only():
    docs = load_corpus_docs(AWS_CORPUS)
    assert docs
    assert all(d.rel_path.startswith("component-definitions/") for d in docs)
    assert {d.root_key for d in docs} == {"component-definition"}


def test_nist_root_keys_are_exactly_the_published_types():
    docs = load_corpus_docs(NIST_CORPUS)
    root_keys = {d.root_key for d in docs}
    assert root_keys == NIST_PUBLISHED_ROOT_KEYS
    assert "mapping-collection" not in root_keys


def test_nist_root_key_filter_drops_non_document_json():
    docs = load_corpus_docs(NIST_CORPUS)
    root = ensure_corpus(NIST_CORPUS)
    all_json = {p.relative_to(root).as_posix(): p for p in root.glob("**/*.json")}

    kept = {d.rel_path for d in docs}
    expected = {
        rel
        for rel, path in all_json.items()
        if corpus._oscal_root_key(path.read_bytes()) is not None  # noqa: SLF001
    }
    assert kept == expected
    for doc in docs:
        value = json.loads(doc.raw_bytes)
        assert list(value) == [doc.root_key]


def test_corpus_fixture_partitions(all_corpus_docs, ap_ar_docs, non_ap_ar_docs):
    """AP/AR partitions are disjoint, cover ``all_corpus_docs``, split on root_key."""
    ap_ar_keys = {"assessment-plan", "assessment-results"}

    def ids(docs):
        return {(d.corpus_name, d.rel_path) for d in docs}

    assert len(ap_ar_docs) + len(non_ap_ar_docs) == len(all_corpus_docs)
    assert ids(ap_ar_docs).isdisjoint(ids(non_ap_ar_docs))
    assert ids(ap_ar_docs) | ids(non_ap_ar_docs) == ids(all_corpus_docs)
    assert {d.root_key for d in ap_ar_docs} == ap_ar_keys
    assert not ap_ar_keys & {d.root_key for d in non_ap_ar_docs}
