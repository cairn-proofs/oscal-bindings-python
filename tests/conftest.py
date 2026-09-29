"""Shared pytest configuration for the test suite.

Registers Hypothesis profiles at import time so every property module picks
them up without per-test ``@settings`` boilerplate. Select a profile with the
``HYPOTHESIS_PROFILE`` environment variable (default ``ci``).

Also provides the session-scoped corpus fixtures the property modules sample
from. Each corpus is fetched/parsed once per session (and shared across xdist
workers through the on-disk cache). Every fixture that feeds
``st.sampled_from`` asserts non-emptiness: an empty corpus or partition is a
hard failure, never a skip (Req 5.4).
"""

import os

import pytest
from hypothesis import HealthCheck, settings
from support.corpus import (
    AWS_CORPUS,
    NIST_CORPUS,
    CorpusDoc,
    load_corpus_docs,
    load_local_corpus_docs,
)

# --- Hypothesis profiles -----------------------------------------------------

settings.register_profile(
    "ci",
    max_examples=100,  # >= 100 iterations per property
    deadline=None,  # corpus parsing can be slow; no per-example deadline
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    print_blob=True,  # surface reproducible counterexamples
)
settings.register_profile("dev", max_examples=50)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "ci"))

# --- Corpus fixtures ---------------------------------------------------------

AP_AR_KEYS = frozenset({"assessment-plan", "assessment-results"})
"""Root keys of the document types that define ``assessment_period()``."""


@pytest.fixture(scope="session")
def nist_docs() -> list[CorpusDoc]:
    """NIST oscal-content documents at the pinned SHA."""
    return load_corpus_docs(NIST_CORPUS)


@pytest.fixture(scope="session")
def aws_docs() -> list[CorpusDoc]:
    """AWS component-definition documents at the pinned SHA."""
    return load_corpus_docs(AWS_CORPUS)


@pytest.fixture(scope="session")
def local_corpus_docs() -> list[CorpusDoc]:
    """Opt-in local documents named by ``OSCAL_BINDINGS_LOCAL_CORPUS``.

    ``[]`` when the variable is unset. When set but invalid or empty,
    ``CorpusError`` propagates and errors every dependent test (Req 11.11, 11.12).
    """
    return load_local_corpus_docs()


@pytest.fixture(scope="session")
def all_corpus_docs(
    nist_docs: list[CorpusDoc],
    aws_docs: list[CorpusDoc],
    local_corpus_docs: list[CorpusDoc],
) -> list[CorpusDoc]:
    """Every corpus document: remote corpora plus any local ones (Req 11.14)."""
    docs = [*nist_docs, *aws_docs, *local_corpus_docs]
    assert docs, "corpus is empty — cannot sample (fail-loud, Req 5.4)"
    return docs


@pytest.fixture(scope="session")
def ap_ar_docs(all_corpus_docs: list[CorpusDoc]) -> list[CorpusDoc]:
    """Assessment Plan and Assessment Results documents only (Req 7.2)."""
    docs = [d for d in all_corpus_docs if d.root_key in AP_AR_KEYS]
    assert docs, "no Assessment Plan / Assessment Results documents in corpus"
    return docs


@pytest.fixture(scope="session")
def non_ap_ar_docs(all_corpus_docs: list[CorpusDoc]) -> list[CorpusDoc]:
    """The other six document types, incl. any local mapping-collection (Req 7.3)."""
    docs = [d for d in all_corpus_docs if d.root_key not in AP_AR_KEYS]
    assert docs, "no non-AP/AR documents in corpus"
    return docs
