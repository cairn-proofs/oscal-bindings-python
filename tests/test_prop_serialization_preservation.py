"""Preservation properties for the default-serialization fix (GitHub issue #5).

Property 2 of the ``oscal-default-serialization-fix`` spec: for every input
outside the bug condition, the fixed library behaves exactly as the unfixed
one. These tests were written and run green on the UNFIXED tree first, so they
pin today's behavior:

- Name-keyed OSCAL *dict* input is rejected at every depth as
  ``extra_forbidden`` at the renamed key (``model_validate`` on the document,
  wrapper, and owning model; ``validate_element``) (3.3, 3.4). This is the
  behavioral tripwire for the ``__pydantic_base_init__`` marker on
  ``OscalBaseModel.__init__`` (design Hypothesized Root Cause 5): if pydantic
  ever routes ``model_validate*`` through the name-mapping ``__init__``, these
  tests fail.
- Name-keyed OSCAL *JSON* input never round-trips its value (3.2, 3.3 as
  observed). pydantic-core's JSON mode (2.46.5) does not report a key equal to
  a field's Python name as ``extra_forbidden``; it drops it. So an optional
  field's value is silently lost (the document is accepted with the field
  ``None``), and a required one fails as ``missing`` at its alias. The JSON
  tests pin exactly that, and also accept ``extra_forbidden`` so a stricter
  pydantic doesn't break them. Silent dropping is a pre-existing defect,
  tracked separately from issue #5.
- Unknown keys stay rejected (3.5).
- ``serialize_oscal`` output is what it always was (3.1).
- ``get_supported_element_types()`` equals the committed pre-fix snapshot (3.7).
- Builders with valid arguments equal the pre-fix alias-dict construction (3.8).
- ``OscalDoc`` accessors and attribute access by Python name are unchanged
  (3.9, 3.11).

Example counts come from the active Hypothesis profile (``ci``:
``max_examples=100``) registered in ``tests/conftest.py``.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11**
"""

from __future__ import annotations

import functools
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st
from pydantic import BaseModel, RootModel, ValidationError
from strategies import (
    hash_strategy,
    leaf_instance_strategy,
    resource_strategy,
    rlink_models,
    rlink_strategy,
    uuids,
)

from oscal_bindings import (
    OscalAccessError,
    OscalDoc,
    OscalParseError,
    get_supported_element_types,
    make_hash,
    make_resource,
    make_rlink,
    parse_assessment_plan,
    parse_assessment_results,
    parse_catalog,
    parse_component_definition,
    parse_mapping_collection,
    parse_oscal,
    parse_oscal_file,
    parse_plan_of_action_and_milestones,
    parse_profile,
    parse_system_security_plan,
    serialize_oscal,
    validate_element,
    validate_oscal,
)
from oscal_bindings.models import (
    Algorithm,
    Hash,
    Link,
    OscalDocument,
    Property,
    Resource,
    Rlink,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence

    from support.corpus import CorpusDoc

SNAPSHOT_PATH = Path(__file__).parent / "support" / "element_types_snapshot.txt"

ROOT_CAUSE_5 = (
    "If this fails after the OscalBaseModel fix, pydantic may no longer honor "
    "`__pydantic_base_init__`: model_validate* would route through "
    "OscalBaseModel.__init__ and accept name-keyed OSCAL input. See design.md, "
    "Hypothesized Root Cause 5 (`__pydantic_custom_init__`)."
)

# pydantic's message for an ``extra_forbidden`` error. `validate_element`
# reports only ``path`` and ``message`` (no error type), so its assertions
# match on this message instead of the type code.
EXTRA_FORBIDDEN_MSG = "Extra inputs are not permitted"

UNKNOWN_KEY = "zz-unknown-preservation-key"

TYPED_PARSERS: dict[str, Callable[[str | bytes], BaseModel]] = {
    "catalog": parse_catalog,
    "profile": parse_profile,
    "component-definition": parse_component_definition,
    "system-security-plan": parse_system_security_plan,
    "assessment-plan": parse_assessment_plan,
    "assessment-results": parse_assessment_results,
    "plan-of-action-and-milestones": parse_plan_of_action_and_milestones,
    "mapping-collection": parse_mapping_collection,
}

# Two tests below draw only from documents up to this size; the 2-10 MB
# catalogs cost ~0.5 s per example to parse and walk. 279 of 306 docs and all
# 7 document types remain.
# - Parse entry points are thin wrappers over OscalDocument.model_validate_json,
#   which test_model_validate_rejects_name_keyed_input_at_depth exercises over
#   the whole corpus, large catalogs included; this test only shows they agree.
# - Unknown keys are rejected by extra='forbid' on every model, which the corpus
#   and mutation suites already cover; site variety, not document size, matters.
SMALL_DOC_MAX_BYTES = 100_000


def _small_docs(corpus: list[CorpusDoc]) -> list[CorpusDoc]:
    """Corpus docs up to SMALL_DOC_MAX_BYTES; every document type must remain."""
    small = [d for d in corpus if len(d.raw_bytes) <= SMALL_DOC_MAX_BYTES]
    assert {d.root_key for d in small} == {d.root_key for d in corpus}, (
        f"a document type lost coverage under {SMALL_DOC_MAX_BYTES} bytes"
    )
    return small


JsonPath = tuple[str | int, ...]


# --- Walking a parsed document alongside its JSON ----------------------------


@dataclass(frozen=True)
class ObjectSite:
    """A JSON object in a corpus doc that a generated model validated."""

    path: JsonPath
    owner: BaseModel


@dataclass(frozen=True)
class AliasSite:
    """A present key whose OSCAL alias differs from its Python field name."""

    path: JsonPath  # path to the owning JSON object
    owner: BaseModel
    name: str
    alias: str


@dataclass(frozen=True)
class DocSites:
    doc: OscalDocument
    objects: tuple[ObjectSite, ...]
    alias_by_depth: dict[int, tuple[AliasSite, ...]]


def _walk(
    value: object, node: object, path: JsonPath
) -> Iterator[ObjectSite | AliasSite]:
    if isinstance(value, RootModel):
        yield from _walk(value.root, node, path)
    elif isinstance(value, BaseModel):
        if not isinstance(node, dict):
            return
        yield ObjectSite(path, value)
        for name, info in type(value).model_fields.items():
            key = info.alias or name
            if key not in node:
                continue
            if info.alias is not None and info.alias != name:
                yield AliasSite(path, value, name, info.alias)
            yield from _walk(getattr(value, name), node[key], (*path, key))
    elif isinstance(value, list) and isinstance(node, list):
        for i, (child, child_node) in enumerate(zip(value, node, strict=True)):
            yield from _walk(child, child_node, (*path, i))
    elif isinstance(value, dict) and isinstance(node, dict):
        for k, child in value.items():
            if k in node:
                yield from _walk(child, node[k], (*path, k))


@functools.cache
def _sites(raw_bytes: bytes) -> DocSites:
    doc = parse_oscal(raw_bytes)
    objects: list[ObjectSite] = []
    by_depth: dict[int, list[AliasSite]] = {}
    for site in _walk(doc, json.loads(raw_bytes), ()):
        if isinstance(site, ObjectSite):
            objects.append(site)
        else:
            by_depth.setdefault(len(site.path), []).append(site)
    return DocSites(
        doc=doc,
        objects=tuple(objects),
        alias_by_depth={d: tuple(s) for d, s in by_depth.items()},
    )


def _node_at(tree: Any, path: JsonPath) -> Any:
    for part in path:
        tree = tree[part]
    return tree


def _rename_key(tree: dict[str, Any], path: JsonPath, old: str, new: str) -> None:
    node = _node_at(tree, path)
    node[new] = node.pop(old)


def _is_subsequence(needle: Sequence[object], haystack: Sequence[object]) -> bool:
    it = iter(haystack)
    return all(any(part == h for h in it) for part in needle)


def _has_error(
    errors: Sequence[Any], error_type: str, path: JsonPath, key: str
) -> bool:
    """True if some error has ``error_type`` for ``key`` under ``path``.

    Union validation inserts member tags (e.g. ``"CatalogDocument"``) into
    ``loc``, so the JSON path must be a subsequence of ``loc``, not a prefix,
    and ``loc`` must end with ``key``.
    """
    for err in errors:
        loc = tuple(err.get("loc", ()))
        if (
            err.get("type") == error_type
            and loc
            and loc[-1] == key
            and _is_subsequence((*path, key), loc)
        ):
            return True
    return False


def _has_extra_forbidden(errors: Sequence[Any], path: JsonPath, key: str) -> bool:
    return _has_error(errors, "extra_forbidden", path, key)


def _model_at(model: object, path: JsonPath) -> object:
    """Follow a JSON (alias) path through a parsed model; ``None`` if absent."""
    for part in path:
        while isinstance(model, RootModel):
            model = model.root
        if isinstance(part, int):
            if not isinstance(model, list) or part >= len(model):
                return None
            model = model[part]
            continue
        if not isinstance(model, BaseModel):
            return None
        fields = type(model).model_fields
        name = next((n for n, f in fields.items() if (f.alias or n) == part), None)
        if name is None:
            return None
        model = getattr(model, name)
    while isinstance(model, RootModel):
        model = model.root
    return model


Outcome = BaseModel | list[Any]
"""A validated model (accepted) or its error dicts (rejected)."""


def _outcome(call: Callable[[], BaseModel]) -> Outcome:
    try:
        return call()
    except OscalParseError as e:
        return list(e.errors)
    except ValidationError as e:
        return list(e.errors())


def _check_json_name_keyed_outcome(
    label: str, outcome: Outcome, site: AliasSite, rel_path: JsonPath, where: str
) -> None:
    """Assert JSON-mode name-keyed input never keeps the value (observed F).

    - Rejected: ``extra_forbidden`` at the Python name, or (required field
      only) ``missing`` at the alias. pydantic-core's JSON mode drops the
      name-keyed key, so a required field reports ``missing``.
    - Accepted (optional field only): the field is ``None`` in the result.
    """
    required = type(site.owner).model_fields[site.name].is_required()
    if isinstance(outcome, list):
        ok = _has_extra_forbidden(outcome, rel_path, site.name) or (
            required and _has_error(outcome, "missing", rel_path, site.alias)
        )
        assert ok, (
            f"{label}: rejected {where}, but not as extra_forbidden at the name "
            f"or missing at the alias (required={required}); "
            f"errors[:5]={outcome[:5]}"
        )
        return
    assert not required, f"{label}: accepted {where} with a required field renamed"
    owner = _model_at(outcome, rel_path)
    assert getattr(owner, site.name, None) is None, (
        f"{label}: accepted {where} AND kept the value: name-keyed JSON now "
        f"populates by name. {ROOT_CAUSE_5}"
    )


def _describe(doc: CorpusDoc, path: JsonPath, key: str, alias: str = "") -> str:
    where = "$" + "".join(f"[{p!r}]" for p in path)
    renamed = f" (renamed from {alias!r})" if alias else ""
    return f"{doc.corpus_name}:{doc.rel_path} at {where} key {key!r}{renamed}"


def _draw_alias_site(
    data: st.DataObject, corpus: list[CorpusDoc]
) -> tuple[CorpusDoc, DocSites, AliasSite]:
    corpus_doc = data.draw(st.sampled_from(corpus), label="doc")
    sites = _sites(corpus_doc.raw_bytes)
    assume(sites.alias_by_depth)
    # Draw the depth first so shallow and deep keys are both exercised, not
    # just whatever depth dominates a large document.
    depth = data.draw(st.sampled_from(sorted(sites.alias_by_depth)), label="depth")
    site = data.draw(st.sampled_from(sites.alias_by_depth[depth]), label="site")
    return corpus_doc, sites, site


def _name_keyed(corpus_doc: CorpusDoc, site: AliasSite) -> dict[str, Any]:
    tree = json.loads(corpus_doc.raw_bytes)
    _rename_key(tree, site.path, site.alias, site.name)
    return tree


# --- Name-keyed rejection at depth (3.2, 3.3) --------------------------------


@given(data=st.data())
def test_parse_entry_points_never_keep_name_keyed_json_value(
    all_corpus_docs: list[CorpusDoc],
    tmp_path_factory: pytest.TempPathFactory,
    data: st.DataObject,
) -> None:
    """Feature: oscal-default-serialization-fix, Property 2: name-keyed JSON
    never keeps its value through any parse entry point, and every entry
    point agrees on accept/reject.

    The parse functions are JSON-mode, so they see pydantic-core's
    drop-the-name-key behavior (module docstring), not ``extra_forbidden``.

    **Validates: Requirements 3.2, 3.3**
    """
    corpus_doc, _, site = _draw_alias_site(data, _small_docs(all_corpus_docs))
    text = json.dumps(_name_keyed(corpus_doc, site))
    where = _describe(corpus_doc, site.path, site.name, site.alias)
    tmp_file = tmp_path_factory.mktemp("name_keyed") / "doc.json"
    tmp_file.write_text(text, encoding="utf-8")
    typed = TYPED_PARSERS[corpus_doc.root_key]

    parsers: dict[str, tuple[Callable[[], BaseModel], JsonPath]] = {
        "parse_oscal(str)": (lambda: parse_oscal(text), site.path),
        "parse_oscal(bytes)": (lambda: parse_oscal(text.encode()), site.path),
        "parse_oscal_file": (lambda: parse_oscal_file(tmp_file), site.path),
        f"typed parser for {corpus_doc.root_key}": (lambda: typed(text), site.path),
    }
    accepted: dict[str, bool] = {}
    for label, (parse, rel_path) in parsers.items():
        outcome = _outcome(parse)
        accepted[label] = not isinstance(outcome, list)
        _check_json_name_keyed_outcome(label, outcome, site, rel_path, where)

    accepted["validate_oscal(str)"] = validate_oscal(text)
    accepted["validate_oscal(bytes)"] = validate_oscal(text.encode())
    assert len(set(accepted.values())) == 1, (
        f"entry points disagree on {where}: {accepted}"
    )


@given(data=st.data())
def test_model_validate_rejects_name_keyed_input_at_depth(
    all_corpus_docs: list[CorpusDoc], data: st.DataObject
) -> None:
    """Feature: oscal-default-serialization-fix, Property 2: direct
    ``model_validate`` stays alias-only (``extra_forbidden`` at the renamed
    key) at the document, wrapper, and owning model levels; direct
    ``model_validate_json`` never keeps the value.

    Direct calls matter: ``model_validate*`` is exactly the path the
    ``__pydantic_base_init__`` marker protects. The dict-mode assertions are
    the strict tripwire.

    **Validates: Requirements 3.2, 3.3**
    """
    corpus_doc, sites, site = _draw_alias_site(data, all_corpus_docs)
    tree = _name_keyed(corpus_doc, site)
    text = json.dumps(tree)
    where = _describe(corpus_doc, site.path, site.name, site.alias)
    wrapper_cls = type(sites.doc.root)
    owner_cls = type(site.owner)
    subtree = _node_at(tree, site.path)

    dict_calls: dict[str, tuple[Callable[[], object], JsonPath]] = {
        "OscalDocument.model_validate": (
            lambda: OscalDocument.model_validate(tree),
            site.path,
        ),
        f"{wrapper_cls.__name__}.model_validate": (
            lambda: wrapper_cls.model_validate(tree),
            site.path,
        ),
        f"{owner_cls.__name__}.model_validate": (
            lambda: owner_cls.model_validate(subtree),
            (),
        ),
    }
    for label, (call, rel_path) in dict_calls.items():
        with pytest.raises(ValidationError) as excinfo:
            call()
        assert _has_extra_forbidden(excinfo.value.errors(), rel_path, site.name), (
            f"{label}: no extra_forbidden for {where}. {ROOT_CAUSE_5}"
        )

    json_calls: dict[str, tuple[Callable[[], BaseModel], JsonPath]] = {
        "OscalDocument.model_validate_json": (
            lambda: OscalDocument.model_validate_json(text.encode()),
            site.path,
        ),
        f"{owner_cls.__name__}.model_validate_json": (
            lambda: owner_cls.model_validate_json(json.dumps(subtree)),
            (),
        ),
    }
    for label, (call, rel_path) in json_calls.items():
        _check_json_name_keyed_outcome(label, _outcome(call), site, rel_path, where)


# --- validate_element: leaf types and nested resource.rlinks[i] (3.4) --------

# Allow-listed leaf types that carry at least one alias-differing field.
_LEAF_MODELS_WITH_ALIASES: dict[str, type[BaseModel]] = {
    "rlink": Rlink,
    "link": Link,
    "property": Property,
}


def _alias_to_name(model_cls: type[BaseModel]) -> dict[str, str]:
    return {
        info.alias: name
        for name, info in model_cls.model_fields.items()
        if info.alias is not None and info.alias != name
    }


def _element_has_extra_forbidden(result: Any, path: str) -> bool:
    return any(
        e.path == path and e.message == EXTRA_FORBIDDEN_MSG for e in result.errors or []
    )


@pytest.mark.parametrize("element_type", list(_LEAF_MODELS_WITH_ALIASES))
@given(data=st.data())
def test_validate_element_rejects_name_keyed_leaf(
    element_type: str, data: st.DataObject
) -> None:
    """Feature: oscal-default-serialization-fix, Property 2: ``validate_element``
    rejects Python field-name keys on leaf elements.

    **Validates: Requirements 3.4**
    """
    element = data.draw(leaf_instance_strategy(element_type), label="element")
    aliases = _alias_to_name(_LEAF_MODELS_WITH_ALIASES[element_type])
    present = sorted(a for a in aliases if a in element)
    assume(present)
    alias = data.draw(st.sampled_from(present), label="alias")
    name = aliases[alias]
    element[name] = element.pop(alias)

    result = validate_element(element, element_type)
    assert result.valid is False, f"{element_type}: accepted {name!r}. {ROOT_CAUSE_5}"
    assert _element_has_extra_forbidden(result, name), (
        f"{element_type}: no extra_forbidden at {name!r} (renamed from "
        f"{alias!r}); errors={result.errors}. {ROOT_CAUSE_5}"
    )


_rlink_lists = st.lists(rlink_models, min_size=1, max_size=4).filter(
    lambda rls: any(r.media_type is not None for r in rls)
)


@given(data=st.data(), rlinks=_rlink_lists, uuid=uuids)
def test_validate_element_rejects_name_keyed_nested_rlink(
    data: st.DataObject, rlinks: list[Rlink], uuid: str
) -> None:
    """Feature: oscal-default-serialization-fix, Property 2: ``validate_element``
    rejects a Python field-name key nested at ``resource.rlinks[i]``.

    **Validates: Requirements 3.4**
    """
    element = Resource.model_validate({"uuid": uuid, "rlinks": rlinks}).model_dump(
        by_alias=True, exclude_none=True
    )
    with_media = [i for i, r in enumerate(rlinks) if r.media_type is not None]
    i = data.draw(st.sampled_from(with_media), label="i")
    nested = element["rlinks"][i]
    nested["media_type"] = nested.pop("media-type")

    result = validate_element(element, "resource")
    path = f"rlinks.{i}.media_type"
    assert result.valid is False, f"resource: accepted {path}. {ROOT_CAUSE_5}"
    assert _element_has_extra_forbidden(result, path), (
        f"resource: no extra_forbidden at {path}; errors={result.errors}. "
        f"{ROOT_CAUSE_5}"
    )


# --- Unknown keys stay rejected (3.5) ----------------------------------------


@given(data=st.data())
def test_unknown_key_rejected_at_depth(
    all_corpus_docs: list[CorpusDoc], data: st.DataObject
) -> None:
    """Feature: oscal-default-serialization-fix, Property 2: unknown keys are
    rejected at any depth.

    **Validates: Requirements 3.5**
    """
    corpus_doc = data.draw(st.sampled_from(_small_docs(all_corpus_docs)), label="doc")
    site = data.draw(
        st.sampled_from(_sites(corpus_doc.raw_bytes).objects), label="site"
    )
    tree = json.loads(corpus_doc.raw_bytes)
    subtree = _node_at(tree, site.path)
    subtree[UNKNOWN_KEY] = "x"
    where = _describe(corpus_doc, site.path, UNKNOWN_KEY)

    with pytest.raises(OscalParseError) as excinfo:
        parse_oscal(json.dumps(tree))
    assert _has_extra_forbidden(excinfo.value.errors, site.path, UNKNOWN_KEY), where

    with pytest.raises(ValidationError) as direct:
        type(site.owner).model_validate(subtree)
    assert _has_extra_forbidden(direct.value.errors(), (), UNKNOWN_KEY), where


# --- serialize_oscal output (3.1) --------------------------------------------


@given(data=st.data())
def test_serialize_oscal_equals_explicit_alias_exclude_none_dump(
    all_corpus_docs: list[CorpusDoc], data: st.DataObject
) -> None:
    """Feature: oscal-default-serialization-fix, Property 2: ``serialize_oscal``
    is the explicit ``by_alias=True, exclude_none=True`` dump.

    Byte-identity against the pre-fix tree is checked separately by comparing
    SHA-256 digests captured before the fix (task 3.9).

    **Validates: Requirements 3.1**
    """
    corpus_doc = data.draw(st.sampled_from(all_corpus_docs), label="doc")
    doc = _sites(corpus_doc.raw_bytes).doc
    where = f"{corpus_doc.corpus_name}:{corpus_doc.rel_path}"
    assert serialize_oscal(doc) == doc.model_dump_json(
        indent=2, by_alias=True, exclude_none=True
    ), where
    assert serialize_oscal(doc, indent=None) == doc.model_dump_json(
        by_alias=True, exclude_none=True
    ), where


# --- Element types (3.7) -----------------------------------------------------


def test_supported_element_types_match_pre_fix_snapshot() -> None:
    """**Validates: Requirements 3.7**"""
    snapshot = SNAPSHOT_PATH.read_text(encoding="utf-8").split()
    assert len(snapshot) == len(set(snapshot)), "duplicate names in the snapshot"
    current = get_supported_element_types()
    assert set(current) == set(snapshot), (
        f"added: {sorted(set(current) - set(snapshot))}; "
        f"removed: {sorted(set(snapshot) - set(current))}"
    )
    assert "oscal-base-model" not in current
    assert "root-model" in current  # pre-existing quirk, preserved on purpose


# --- Builders with valid arguments (3.8) -------------------------------------


@given(hash_strategy())
def test_make_hash_equals_pre_fix_construction(kwargs: dict[str, Any]) -> None:
    """**Validates: Requirements 3.8**"""
    algorithm = Algorithm(kwargs.get("algorithm", Algorithm.SHA_256))
    expected = Hash.model_validate({"algorithm": algorithm, "value": kwargs["value"]})
    assert make_hash(**kwargs) == expected


@given(rlink_strategy())
def test_make_rlink_equals_pre_fix_construction(kwargs: dict[str, Any]) -> None:
    """**Validates: Requirements 3.8**"""
    expected = Rlink.model_validate(
        {
            "href": kwargs["href"],
            "media-type": kwargs.get("media_type"),
            "hashes": kwargs.get("hashes"),
        }
    )
    assert make_rlink(**kwargs) == expected


@given(resource_strategy())
def test_make_resource_equals_pre_fix_construction(kwargs: dict[str, Any]) -> None:
    """Valid ``document_ids`` only (the strategy draws non-empty ``DocumentId``
    lists); invalid ones are the 1.7 / 2.13 fix, not preservation.

    **Validates: Requirements 3.8**
    """
    actual = make_resource(**kwargs)
    expected = Resource.model_validate(
        {
            "uuid": kwargs.get("uuid", actual.uuid),
            "title": kwargs.get("title"),
            "description": kwargs.get("description"),
            "rlinks": kwargs.get("rlinks"),
            "document-ids": kwargs.get("document_ids"),
        }
    )
    assert actual == expected
    assert actual.model_dump_json(
        by_alias=True, exclude_none=True
    ) == expected.model_dump_json(by_alias=True, exclude_none=True)


# --- OscalDoc accessors and attribute access by Python name (3.9, 3.11) ------


@given(data=st.data())
def test_facade_and_attribute_access_unchanged(
    all_corpus_docs: list[CorpusDoc], data: st.DataObject
) -> None:
    """Feature: oscal-default-serialization-fix, Property 2: ``OscalDoc``
    accessors and Python-name attribute access resolve the same values.

    **Validates: Requirements 3.9, 3.11**
    """
    corpus_doc, sites, site = _draw_alias_site(data, all_corpus_docs)
    where = _describe(corpus_doc, site.path, site.name, site.alias)
    raw = json.loads(corpus_doc.raw_bytes)
    body_raw = raw[corpus_doc.root_key]

    facade = OscalDoc(sites.doc)
    assert facade.wrapper is sites.doc.root
    assert facade.body is getattr(facade.wrapper, corpus_doc.root_key.replace("-", "_"))
    assert facade.uuid == body_raw["uuid"]
    assert facade.oscal_version == body_raw["metadata"]["oscal-version"]
    assert facade.metadata.title == body_raw["metadata"]["title"]
    if corpus_doc.root_key in {"assessment-plan", "assessment-results"}:
        facade.assessment_period()
    else:
        with pytest.raises(OscalAccessError):
            facade.assessment_period()

    # Python-name attribute access on an alias-differing field.
    value = getattr(site.owner, site.name)
    assert value is not None, where
    raw_value = _node_at(raw, site.path)[site.alias]
    if isinstance(value, str):
        assert value == raw_value, where
