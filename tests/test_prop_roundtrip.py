"""Round-trip property tests over the corpus pool (Requirement 6).

Every property draws a document from the session-scoped ``all_corpus_docs``
fixture with the ``st.data()`` pattern (``@given`` cannot close over a
fixture value). Example counts come from the ``ci`` Hypothesis profile
registered in ``conftest.py`` (``max_examples=100``).
"""

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from hypothesis import given
from hypothesis import strategies as st
from support.corpus import CorpusDoc

from oscal_bindings import OscalDoc, OscalDocument, parse_oscal, serialize_oscal


def _doc_id(doc: CorpusDoc) -> str:
    """Identifier used in every failure diagnostic (Req 6.4)."""
    return f"{doc.corpus_name}:{doc.rel_path}"


@contextmanager
def _identify(doc: CorpusDoc, stage: str) -> Iterator[None]:
    """Re-raise any exception from *stage* as a test failure naming *doc*."""
    try:
        yield
    except Exception as e:
        pytest.fail(f"{stage} raised on {_doc_id(doc)}: {type(e).__name__}: {e}")


def _round_trip(doc: CorpusDoc, model: OscalDocument) -> OscalDocument:
    """Serialize *model* and parse the result, naming *doc* on failure."""
    with _identify(doc, "serialize_oscal"):
        text = serialize_oscal(model)
    with _identify(doc, "parse_oscal (re-parse)"):
        return parse_oscal(text)


def set_metadata_remarks(model: OscalDocument, text: str) -> OscalDocument:
    """Return a copy of *model* whose ``metadata.remarks`` is *text*.

    Rebuilds metadata -> body -> wrapper -> ``OscalDocument`` with
    ``model_copy(update=...)``; the input model is left untouched. The
    wrapper's body attribute is located by identity with ``OscalDoc.body``
    so no per-document-type dispatch is needed here.
    """
    wrapper = model.root
    body = OscalDoc(model).body
    body_attr = next(
        name for name in type(wrapper).model_fields if getattr(wrapper, name) is body
    )
    metadata = body.metadata.model_copy(update={"remarks": text})
    new_body = body.model_copy(update={"metadata": metadata})
    return OscalDocument(root=wrapper.model_copy(update={body_attr: new_body}))


@given(data=st.data())
def test_round_trip_preserves_model(
    all_corpus_docs: list[CorpusDoc], data: st.DataObject
) -> None:
    """Feature: property-based-tests, Property 1: Round-trip preserves the model.

    For any corpus document, parsing it, serializing the result, and parsing
    that serialization again yields a model equal to the first parse.

    **Validates: Requirements 6.1, 6.4**
    """
    doc = data.draw(st.sampled_from(all_corpus_docs), label="doc")
    with _identify(doc, "parse_oscal"):
        first = parse_oscal(doc.raw_bytes)
    second = _round_trip(doc, first)
    assert second == first, f"round-trip changed the model for {_doc_id(doc)}"


@given(data=st.data())
def test_mutated_documents_still_round_trip(
    all_corpus_docs: list[CorpusDoc], data: st.DataObject
) -> None:
    """Feature: property-based-tests, Property 2: Mutated documents still round-trip.

    For any corpus document and any non-empty string assigned to the
    optional ``metadata.remarks`` scalar (by nested reconstruction), the
    mutated document serializes and re-parses to an equal model.

    **Validates: Requirements 6.2**
    """
    doc = data.draw(st.sampled_from(all_corpus_docs), label="doc")
    # Metadata.remarks is an unconstrained optional str, so any non-empty
    # text is schema-valid (including characters that need JSON escaping).
    remarks = data.draw(st.text(min_size=1), label="remarks")
    with _identify(doc, "parse_oscal"):
        original = parse_oscal(doc.raw_bytes)
    mutated = set_metadata_remarks(original, remarks)
    reparsed = _round_trip(doc, mutated)
    assert reparsed == mutated, (
        f"mutated round-trip changed the model for {_doc_id(doc)}"
    )
    survived = OscalDoc(reparsed).metadata.remarks
    assert survived == remarks, f"remarks lost for {_doc_id(doc)}"


@given(data=st.data())
def test_bytes_and_str_parse_identically(
    all_corpus_docs: list[CorpusDoc], data: st.DataObject
) -> None:
    """Feature: property-based-tests, Property 3: bytes and str inputs parse identically

    For any corpus document, parsing its UTF-8 ``bytes`` form and its
    decoded ``str`` form produce equal models.

    **Validates: Requirements 6.3**
    """
    doc = data.draw(st.sampled_from(all_corpus_docs), label="doc")
    with _identify(doc, "parse_oscal (bytes)"):
        from_bytes = parse_oscal(doc.raw_bytes)
    with _identify(doc, "parse_oscal (str)"):
        from_str = parse_oscal(doc.raw_bytes.decode("utf-8"))
    assert from_bytes == from_str, f"bytes and str parses differ for {_doc_id(doc)}"
