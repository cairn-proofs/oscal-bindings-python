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

Fix-checking unit tests (task 4.1) follow: opt-outs (``by_alias=False``,
``exclude_none=False``, ``include``/``exclude``/``exclude_unset``), construction
smoke cases, the serialization JSON schema, the generated-model structure, and
framework-shaped calls that must re-parse to the same document.

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 2.3, 2.4, 2.8, 2.9,
2.12, 2.13, 3.12**
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pydantic_core
import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import BaseModel, RootModel, TypeAdapter, ValidationError
from support.oscal_shape import DEFAULT_PATHS, assert_valid_oscal_shape

from oscal_bindings import (
    make_resource,
    parse_catalog,
    parse_oscal,
    serialize_oscal,
)
from oscal_bindings.models import (
    Capability,
    DocumentId,
    Hash,
    Resource,
    Rlink,
)
from oscal_bindings.v1 import models as v1_models
from oscal_bindings.v1._base import OscalBaseModel

if TYPE_CHECKING:
    from collections.abc import Callable

    from support.corpus import CorpusDoc

CATALOG_800_53 = "nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_catalog.json"
UUID = "3b2a5a8e-6f8e-4c1e-9a0b-0c7d2e1f4a55"
HREF = "https://example.com/a.pdf"


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


# --- Default serialization paths (shared table in support.oscal_shape) -------

PATHS = DEFAULT_PATHS

BY_ALIAS = {"by_alias-omitted": {}, "by_alias=True": {"by_alias": True}}


@pytest.mark.parametrize("by_alias", list(BY_ALIAS))
@pytest.mark.parametrize("path", list(PATHS))
@pytest.mark.parametrize("model", list(MODEL_FACTORIES))
def test_default_path_emits_oscal_keys_and_no_nulls(
    model: str, path: str, by_alias: str, catalog_bytes: bytes
) -> None:
    """Default paths emit alias keys only and no null (1.1-1.4, 2.1-2.4, 2.6)."""
    instance = MODEL_FACTORIES[model](catalog_bytes)
    assert_valid_oscal_shape(PATHS[path](instance, BY_ALIAS[by_alias]))


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


# --- Opt-outs (2.8) ----------------------------------------------------------


def _model_field_names() -> frozenset[str]:
    names: set[str] = set()
    for obj in vars(v1_models).values():
        if isinstance(obj, type) and issubclass(obj, BaseModel):
            names.update(obj.model_fields)
    return frozenset(names)


MODEL_FIELD_NAMES = _model_field_names()


def _name_keyed_violations(value: object, path: str = "$") -> list[str]:
    """Return every ``null`` and every key that isn't a Python field name."""
    found: list[str] = []
    if value is None:
        found.append(f"{path}: null")
    elif isinstance(value, dict):
        for key, child in value.items():
            if key not in MODEL_FIELD_NAMES or "-" in key:
                found.append(f"{path}: non-field-name key {key!r}")
            found.extend(_name_keyed_violations(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for i, child in enumerate(value):
            found.extend(_name_keyed_violations(child, f"{path}[{i}]"))
    return found


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        keys = set(value)
        for child in value.values():
            keys |= _all_keys(child)
        return keys
    if isinstance(value, list):
        return set().union(*(_all_keys(c) for c in value)) if value else set()
    return set()


@pytest.mark.parametrize(
    "dump",
    [
        pytest.param(lambda m: m.model_dump(by_alias=False), id="model_dump"),
        pytest.param(
            lambda m: m.model_dump(mode="json", by_alias=False), id="model_dump-json"
        ),
        pytest.param(
            lambda m: json.loads(m.model_dump_json(by_alias=False)),
            id="model_dump_json",
        ),
        pytest.param(
            lambda m: json.loads(pydantic_core.to_json(m, by_alias=False)),
            id="to_json",
        ),
    ],
)
def test_by_alias_false_emits_names_at_depth_without_nulls(
    dump: Callable[[BaseModel], Any], catalog_bytes: bytes
) -> None:
    """``by_alias=False`` gives Python names at every depth, still no null."""
    dumped = dump(parse_catalog(catalog_bytes))
    problems = _name_keyed_violations(dumped)
    assert not problems, f"{len(problems)} violation(s): {'; '.join(problems[:10])}"
    # Alias-differing fields at depth come out under their Python names.
    keys = _all_keys(dumped)
    assert {"back_matter", "media_type", "last_modified", "oscal_version"} <= keys
    assert not {"back-matter", "media-type", "last-modified"} & keys


@pytest.mark.parametrize("model", list(MODEL_FACTORIES))
def test_exclude_none_false_is_a_no_op(model: str, catalog_bytes: bytes) -> None:
    """``exclude_none=False`` output equals default output (OSCAL forbids null)."""
    m = MODEL_FACTORIES[model](catalog_bytes)
    assert m.model_dump(exclude_none=False) == m.model_dump()
    assert m.model_dump(mode="json", exclude_none=False) == m.model_dump(mode="json")
    assert m.model_dump_json(exclude_none=False) == m.model_dump_json()
    assert pydantic_core.to_json(m, exclude_none=False) == pydantic_core.to_json(m)


def _full_rlink() -> Rlink:
    return Rlink(
        href=HREF,
        media_type="text/plain",
        hashes=[Hash(algorithm="SHA-256", value="ab")],
    )


def test_include_is_honored() -> None:
    assert _full_rlink().model_dump(include={"href"}) == {"href": HREF}
    assert json.loads(_full_rlink().model_dump_json(include={"media_type"})) == {
        "media-type": "text/plain"
    }


def test_exclude_is_honored() -> None:
    assert _full_rlink().model_dump(exclude={"hashes"}) == {
        "href": HREF,
        "media-type": "text/plain",
    }
    nested = _full_rlink().model_dump(mode="json", exclude={"hashes": {0: {"value"}}})
    assert nested["hashes"] == [{"algorithm": "SHA-256"}]


def test_exclude_unset_is_honored() -> None:
    # No generated field has a non-None default, so build an instance whose
    # unset field carries a value to observe exclude_unset dropping it.
    m = Rlink.model_construct(href=HREF, media_type="text/plain", _fields_set={"href"})
    assert m.model_dump() == {"href": HREF, "media-type": "text/plain"}
    assert m.model_dump(exclude_unset=True) == {"href": HREF}
    assert json.loads(m.model_dump_json(exclude_unset=True)) == {"href": HREF}


# --- Construction smoke (2.9; exhaustive cases in test_base_model.py) --------


def test_rlink_construction_by_name_alias_and_mixed() -> None:
    hashes = [Hash(algorithm="SHA-256", value="ab")]
    by_name = Rlink(href=HREF, media_type="text/plain", hashes=hashes)
    by_alias = Rlink(**{"href": HREF, "media-type": "text/plain", "hashes": hashes})
    assert by_name == by_alias
    assert by_name.media_type == "text/plain"
    assert by_name.model_dump() == {
        "href": HREF,
        "media-type": "text/plain",
        "hashes": [{"algorithm": "SHA-256", "value": "ab"}],
    }


def test_resource_construction_by_name_alias_and_mixed() -> None:
    ids = [DocumentId(identifier="x")]
    rlinks = [Rlink(href=HREF, media_type="text/plain")]
    by_name = Resource(uuid=UUID, title="t", document_ids=ids, rlinks=rlinks)
    by_alias = Resource(
        **{"uuid": UUID, "title": "t", "document-ids": ids, "rlinks": rlinks}
    )
    mixed = Resource(uuid=UUID, title="t", rlinks=rlinks, **{"document-ids": ids})
    assert by_name == by_alias == mixed
    assert by_name.document_ids == ids


@pytest.mark.parametrize(
    ("cls", "kwargs"),
    [
        pytest.param(Rlink, {"href": HREF, "bogus": 1}, id="rlink"),
        pytest.param(Resource, {"uuid": UUID, "bogus": 1}, id="resource"),
    ],
)
def test_unknown_kwarg_is_rejected(
    cls: type[BaseModel], kwargs: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError) as excinfo:
        cls(**kwargs)
    found = {(e["type"], e["loc"]) for e in excinfo.value.errors()}
    assert ("extra_forbidden", ("bogus",)) in found


# --- Serialization JSON schema (2.8) -----------------------------------------


def test_rlink_serialization_schema_lists_alias_properties() -> None:
    schema = Rlink.model_json_schema(mode="serialization")
    assert {"href", "media-type", "hashes"} <= set(schema["properties"])


# --- Structure: every object model uses the base (3.12) ----------------------

PRESERVED_ROOT_MODELS = {"OscalDocument", "Mappings"}
IMPORTED_BASES = {BaseModel, RootModel, OscalBaseModel}


def test_every_generated_object_model_subclasses_oscal_base_model() -> None:
    offenders = [
        name
        for name, obj in vars(v1_models).items()
        if isinstance(obj, type)
        and issubclass(obj, BaseModel)
        and obj not in IMPORTED_BASES
        and name not in PRESERVED_ROOT_MODELS
        and not issubclass(obj, OscalBaseModel)
    ]
    assert not offenders, f"not OscalBaseModel subclasses: {offenders}"
    for name in PRESERVED_ROOT_MODELS:
        assert issubclass(getattr(v1_models, name), RootModel)


def test_models_source_has_no_plain_base_model_header() -> None:
    source = Path(v1_models.__file__).read_text(encoding="utf-8")
    headers = re.findall(r"^class \w+\(\s*BaseModel\s*\)", source, re.MULTILINE)
    assert not headers, f"class headers still on BaseModel: {headers[:10]}"


# --- Framework-shaped calls round-trip (2.3, 2.4) ----------------------------


def _framework_to_json_list(doc: BaseModel) -> Any:
    (item,) = json.loads(pydantic_core.to_json([doc]))
    return item


def _framework_type_adapter(doc: BaseModel) -> Any:
    dumped = TypeAdapter(dict[str, Any]).dump_python(
        {"result": doc}, mode="json", by_alias=True
    )
    assert list(dumped) == ["result"]
    return dumped["result"]


def _framework_model_dump_json(doc: BaseModel) -> Any:
    return json.loads(doc.model_dump_json())


@pytest.mark.parametrize(
    "dump",
    [
        pytest.param(_framework_to_json_list, id="to_json([doc])"),
        pytest.param(_framework_type_adapter, id="TypeAdapter({'result': doc})"),
        pytest.param(_framework_model_dump_json, id="model_dump_json()"),
    ],
)
def test_framework_shaped_output_reparses_to_same_document(
    dump: Callable[[BaseModel], Any], catalog_bytes: bytes
) -> None:
    doc = parse_oscal(catalog_bytes)
    expected = serialize_oscal(doc)
    dumped = dump(doc)
    assert dumped == json.loads(expected)
    assert serialize_oscal(parse_oscal(json.dumps(dumped))) == expected
