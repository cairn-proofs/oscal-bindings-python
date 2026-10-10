"""Default serialization paths emit valid OSCAL; keyword construction by name.

Bug condition exploration for GitHub issue #5 (Property 1 / Property 4 of the
``oscal-default-serialization-fix`` spec). These tests encode the *expected*
behavior, so they fail on the unfixed library and pass once the fix lands:

- Every default serialization path (``model_dump*`` with no kwargs,
  ``pydantic_core.to_json``, ``TypeAdapter.dump_python``) emits OSCAL (alias)
  keys only and no ``None``/``null``, at every depth, for models alone and
  inside plain containers.
- For a whole document, ``json.loads(doc.model_dump_json())`` equals
  ``json.loads(serialize_oscal(doc))``.
- Keyword construction by Python field name equals construction by alias.
- ``make_resource`` validates ``document_ids`` and raises ``ValidationError``.

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 2.12, 2.13**
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pydantic_core
import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import BaseModel, TypeAdapter, ValidationError

from oscal_bindings import (
    make_resource,
    parse_catalog,
    parse_oscal,
    serialize_oscal,
)
from oscal_bindings.models import (
    Capability,
    DocumentId,
    Resource,
    Rlink,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from support.corpus import CorpusDoc

SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent
    / "schemas"
    / "1.2.3"
    / "oscal_complete_schema.json"
)
CATALOG_800_53 = "nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_catalog.json"
UUID = "3b2a5a8e-6f8e-4c1e-9a0b-0c7d2e1f4a55"
HREF = "https://example.com/a.pdf"
CONTAINER_KEY = "k"


# --- Schema property names ---------------------------------------------------


def _collect_property_names(node: object, out: set[str]) -> None:
    if isinstance(node, dict):
        props = node.get("properties")
        if isinstance(props, dict):
            out.update(props)
        for value in node.values():
            _collect_property_names(value, out)
    elif isinstance(node, list):
        for value in node:
            _collect_property_names(value, out)


def _schema_property_names() -> frozenset[str]:
    names: set[str] = set()
    _collect_property_names(json.loads(SCHEMA_PATH.read_text()), names)
    assert names, "no properties found in the vendored schema"
    return frozenset(names)


SCHEMA_PROPERTY_NAMES = _schema_property_names()


def _violations(value: object, path: str = "$") -> list[str]:
    """Return every ``null`` and every non-OSCAL key in a dumped model tree."""
    found: list[str] = []
    if value is None:
        found.append(f"{path}: null")
    elif isinstance(value, dict):
        for key, child in value.items():
            if key not in SCHEMA_PROPERTY_NAMES:
                found.append(f"{path}: non-OSCAL key {key!r}")
            found.extend(_violations(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for i, child in enumerate(value):
            found.extend(_violations(child, f"{path}[{i}]"))
    return found


def _assert_valid_oscal_shape(value: object) -> None:
    problems = _violations(value)
    first = "; ".join(problems[:10])
    assert not problems, f"{len(problems)} violation(s), first 10: {first}"


# --- Fixtures: models under test ---------------------------------------------


@pytest.fixture(scope="module")
def catalog_bytes(nist_docs: list[CorpusDoc]) -> bytes:
    for doc in nist_docs:
        if doc.rel_path == CATALOG_800_53:
            return doc.raw_bytes
    pytest.fail(f"{CATALOG_800_53} missing from the NIST corpus")


def _capability() -> BaseModel:
    return Capability(uuid=UUID, name="n", description="d")


def _rlink_plain() -> BaseModel:
    return Rlink(href=HREF)


def _rlink_media_type() -> BaseModel:
    return Rlink(**{"href": HREF, "media-type": "text/plain"})


def _resource_document_ids() -> BaseModel:
    return Resource(
        **{"uuid": UUID, "document-ids": [DocumentId(identifier="x")]},
    )


MODEL_FACTORIES: dict[str, Callable[[bytes], BaseModel]] = {
    "capability-required-only": lambda _: _capability(),
    "rlink-no-media-type": lambda _: _rlink_plain(),
    "rlink-media-type": lambda _: _rlink_media_type(),
    "resource-document-ids": lambda _: _resource_document_ids(),
    "corpus-metadata": lambda raw: parse_catalog(raw).catalog.metadata,
    "catalog-document": parse_catalog,
    "oscal-document": parse_oscal,
}


# --- Default serialization paths ---------------------------------------------
# Each returns the dumped value with any container wrapper removed, so the
# result is the model's own serialized tree.


def _unwrap_list(value: Any) -> Any:
    assert list(value) == [CONTAINER_KEY]
    (item,) = value[CONTAINER_KEY]
    return item


def _path_model_dump(m: BaseModel, kw: dict[str, Any]) -> Any:
    return m.model_dump(**kw)


def _path_model_dump_json_mode(m: BaseModel, kw: dict[str, Any]) -> Any:
    return m.model_dump(mode="json", **kw)


def _path_model_dump_json(m: BaseModel, kw: dict[str, Any]) -> Any:
    return json.loads(m.model_dump_json(**kw))


def _path_to_json(m: BaseModel, kw: dict[str, Any]) -> Any:
    return json.loads(pydantic_core.to_json(m, **kw))


def _path_to_json_container(m: BaseModel, kw: dict[str, Any]) -> Any:
    return _unwrap_list(json.loads(pydantic_core.to_json({CONTAINER_KEY: [m]}, **kw)))


def _path_type_adapter(m: BaseModel, kw: dict[str, Any]) -> Any:
    dumped = TypeAdapter(dict[str, Any]).dump_python(
        {CONTAINER_KEY: m}, mode="json", **kw
    )
    assert list(dumped) == [CONTAINER_KEY]
    return dumped[CONTAINER_KEY]


PATHS: dict[str, Callable[[BaseModel, dict[str, Any]], Any]] = {
    "model_dump()": _path_model_dump,
    "model_dump(mode=json)": _path_model_dump_json_mode,
    "model_dump_json()": _path_model_dump_json,
    "to_json(m)": _path_to_json,
    "to_json({k: [m]})": _path_to_json_container,
    "TypeAdapter.dump_python({k: m})": _path_type_adapter,
}

BY_ALIAS = {"by_alias-omitted": {}, "by_alias=True": {"by_alias": True}}


@pytest.mark.parametrize("by_alias", list(BY_ALIAS))
@pytest.mark.parametrize("path", list(PATHS))
@pytest.mark.parametrize("model", list(MODEL_FACTORIES))
def test_default_path_emits_oscal_keys_and_no_nulls(
    model: str, path: str, by_alias: str, catalog_bytes: bytes
) -> None:
    """Default paths emit alias keys only and no null (1.1-1.4, 2.1-2.4, 2.6)."""
    instance = MODEL_FACTORIES[model](catalog_bytes)
    _assert_valid_oscal_shape(PATHS[path](instance, BY_ALIAS[by_alias]))


# --- Whole-document equivalence ----------------------------------------------


def test_catalog_model_dump_json_equals_serialize_oscal(catalog_bytes: bytes) -> None:
    """SP 800-53: bare ``model_dump_json`` matches ``serialize_oscal`` (1.5)."""
    doc = parse_oscal(catalog_bytes)
    assert json.loads(doc.model_dump_json()) == json.loads(serialize_oscal(doc))


@given(data=st.data())
def test_corpus_model_dump_json_equals_serialize_oscal(
    all_corpus_docs: list[CorpusDoc], data: st.DataObject
) -> None:
    """Any corpus doc: default ``model_dump_json`` matches ``serialize_oscal`` (1.5)."""
    corpus_doc = data.draw(st.sampled_from(all_corpus_docs), label="doc")
    doc = parse_oscal(corpus_doc.raw_bytes)
    assert json.loads(doc.model_dump_json()) == json.loads(serialize_oscal(doc)), (
        f"{corpus_doc.corpus_name}:{corpus_doc.rel_path}"
    )


# --- Keyword construction by Python field name (1.6, 2.9) --------------------


def test_resource_document_ids_by_name_equals_alias() -> None:
    ids = [DocumentId(identifier="x")]
    by_name = Resource(uuid=UUID, document_ids=ids)
    by_alias = Resource(**{"uuid": UUID, "document-ids": ids})
    assert by_name == by_alias


def test_rlink_media_type_by_name_equals_alias() -> None:
    by_name = Rlink(href=HREF, media_type="text/plain")
    by_alias = Rlink(**{"href": HREF, "media-type": "text/plain"})
    assert by_name == by_alias


# --- make_resource validates document_ids (Property 4; 1.7, 2.13) ------------


@pytest.mark.parametrize(
    "document_ids",
    [pytest.param([], id="empty"), pytest.param(["x"], id="non-DocumentId")],
)
def test_make_resource_rejects_invalid_document_ids(document_ids: list[Any]) -> None:
    with pytest.raises(ValidationError):
        make_resource(document_ids=document_ids)
