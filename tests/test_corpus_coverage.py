"""Mapping-collection coverage check (Req 11.9, 11.10, 11.15).

NIST publishes no mapping-collection example and the AWS corpus holds only
component definitions, so the remote corpora cover 7 of the 8 OSCAL document
types. The eighth is covered only by the opt-in local corpus named by
``OSCAL_BINDINGS_LOCAL_CORPUS``. This module is a coverage assertion, not a
property: it makes that gap visible.

When the variable is unset this test skips (the suite's one sanctioned skip),
with a reason naming the variable so the 7-type limitation shows up in pytest's
short summary. When set, it asserts the corpus pool contains at least one
mapping-collection document.
"""

from __future__ import annotations

import os

import pytest
from support.corpus import LOCAL_CORPUS_ENV, CorpusDoc

MAPPING_COLLECTION_KEY = "mapping-collection"


def test_mapping_collection_covered(request: pytest.FixtureRequest) -> None:
    # Check the variable before requesting ``all_corpus_docs`` so the unset
    # case skips without loading (or fetching) the remote corpora.
    if not os.environ.get(LOCAL_CORPUS_ENV):
        pytest.skip(
            f"{LOCAL_CORPUS_ENV} is unset: no mapping-collection example is "
            "published by NIST, so this type is only covered locally"
        )

    all_corpus_docs: list[CorpusDoc] = request.getfixturevalue("all_corpus_docs")
    assert any(d.root_key == MAPPING_COLLECTION_KEY for d in all_corpus_docs), (
        f"{LOCAL_CORPUS_ENV} is set but supplied no mapping-collection document"
    )
