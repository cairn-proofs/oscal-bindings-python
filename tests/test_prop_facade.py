"""Property-based tests for the ``OscalDoc`` facade (Req 7).

Each property samples real corpus documents via ``st.sampled_from`` and relies
on the ``ci`` Hypothesis profile (``max_examples=100``) registered in
``conftest.py``. Parsing is deterministic, so parsed models are cached per
document identity to keep repeated draws of large documents cheap; the facade
only reads from the model, so sharing it across examples is safe.
"""

from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st
from support.corpus import CorpusDoc

from oscal_bindings import OscalAccessError, OscalDoc, parse_oscal
from oscal_bindings.models import Metadata, OscalDocument

_PARSED: dict[tuple[str, str], OscalDocument] = {}


def _facade(doc: CorpusDoc) -> OscalDoc:
    """Wrap the (cached) parse of ``doc`` in ``OscalDoc``."""
    key = (doc.corpus_name, doc.rel_path)
    if key not in _PARSED:
        _PARSED[key] = parse_oscal(doc.raw_bytes)
    return OscalDoc(_PARSED[key])


def _ident(doc: CorpusDoc) -> str:
    return f"{doc.corpus_name}:{doc.rel_path}"


@given(data=st.data())
def test_facade_accessors_never_raise(
    all_corpus_docs: list[CorpusDoc], data: st.DataObject
) -> None:
    """Feature: property-based-tests, Property 4: Facade accessors never raise
    on valid documents.

    For any corpus document wrapped in ``OscalDoc``, accessing ``metadata``,
    ``uuid``, ``oscal_version``, and ``body`` completes without raising.

    **Validates: Requirements 7.1, 11.14**
    """
    doc = data.draw(st.sampled_from(all_corpus_docs))
    facade = _facade(doc)

    body = facade.body
    metadata = facade.metadata
    uuid = facade.uuid
    oscal_version = facade.oscal_version

    assert body is not None, _ident(doc)
    assert isinstance(metadata, Metadata), _ident(doc)
    assert isinstance(uuid, str), _ident(doc)
    assert uuid, _ident(doc)
    assert isinstance(oscal_version, str), _ident(doc)
    assert oscal_version, _ident(doc)


@given(data=st.data())
def test_assessment_period_succeeds_for_ap_ar(
    ap_ar_docs: list[CorpusDoc], data: st.DataObject
) -> None:
    """Feature: property-based-tests, Property 5: assessment_period() succeeds
    for Assessment Plan / Assessment Results.

    For any Assessment Plan or Assessment Results corpus document,
    ``assessment_period()`` returns a ``(start, end)`` value without raising.

    **Validates: Requirements 7.2**
    """
    doc = data.draw(st.sampled_from(ap_ar_docs))
    period = _facade(doc).assessment_period()

    assert isinstance(period, tuple), _ident(doc)
    assert len(period) == 2, _ident(doc)
    start, end = period
    assert start is None or isinstance(start, date), _ident(doc)
    assert end is None or isinstance(end, date), _ident(doc)


@given(data=st.data())
def test_assessment_period_rejects_non_ap_ar(
    non_ap_ar_docs: list[CorpusDoc], data: st.DataObject
) -> None:
    """Feature: property-based-tests, Property 6: assessment_period() rejects
    non-AP/AR documents.

    For any corpus document that is neither an Assessment Plan nor Assessment
    Results, invoking ``assessment_period()`` raises ``OscalAccessError``.

    **Validates: Requirements 7.3, 11.14**
    """
    doc = data.draw(st.sampled_from(non_ap_ar_docs))
    facade = _facade(doc)

    with pytest.raises(OscalAccessError):
        facade.assessment_period()
