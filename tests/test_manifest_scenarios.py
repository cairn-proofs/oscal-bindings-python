"""Scenarios of the naming-manifest capability about the released manifest.

``tests/test_manifest.py`` checks the validation of a changed manifest. These
tests check what the released ``names.json`` of the pinned spec artifact holds
(the shape of each kind of entry, the pointers, the data that an entry does not
hold) and what the models and the post-processor make of it.
"""

from __future__ import annotations

import ast
import copy
import json
import re
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter
from support.scripts import load_script
from support.spec_artifact import ensure_spec_artifact

from oscal_bindings.v1 import models

manifest_mod = load_script("manifest")
pin = load_script("spec_artifact")

_PATHS = pin.artifact_paths(ensure_spec_artifact())
MANIFEST: dict[str, Any] = json.loads(_PATHS.names.read_bytes())
NAMES_SCHEMA: dict[str, Any] = json.loads(_PATHS.names_schema.read_bytes())
SCHEMA_BYTES: bytes = _PATHS.schema.read_bytes()
SCHEMA: dict[str, Any] = json.loads(SCHEMA_BYTES)
ENTRIES: dict[str, dict[str, Any]] = {t["name"]: t for t in MANIFEST["types"]}
DEF = "#/definitions/oscal-complete-oscal-"


def _validate(manifest: object) -> list[str]:
    failures: list[str] = manifest_mod.validate_manifest(
        manifest, NAMES_SCHEMA, SCHEMA_BYTES, pin.OSCAL_RELEASE
    )
    return failures


def _owners(site: str) -> list[str]:
    return [t["name"] for t in MANIFEST["types"] if site in t["sites"]]


@pytest.mark.spec("NAM-001.01")
def test_definition_is_identified_by_its_definition_pointer() -> None:
    assert ENTRIES["Hash"]["sites"] == [f"{DEF}metadata:hash"]
    assert manifest_mod.resolve_pointer(SCHEMA, f"{DEF}metadata:hash") is not None


@pytest.mark.spec("NAM-009.01")
def test_merged_type_holds_the_place_of_each_parties_branch() -> None:
    entry = ENTRIES["MetadataPartyExternalId"]
    base = f"{DEF}metadata:metadata/properties/parties/items/anyOf"
    expected = [
        f"{base}/0/properties/external-ids/items",
        f"{base}/1/properties/external-ids/items",
    ]
    assert entry["sites"] == expected
    for site in expected:
        assert manifest_mod.resolve_pointer(SCHEMA, site) is not None
        assert _owners(site) == ["MetadataPartyExternalId"]


@pytest.mark.spec("NAM-009.03")
def test_scalar_definition_with_an_enum_has_an_entry() -> None:
    entry = ENTRIES["RiskStatus"]
    assert entry["kind"] == "enum"
    (site,) = entry["sites"]
    assert site.startswith(f"{DEF}assessment-common:risk-status")
    target = manifest_mod.resolve_pointer(SCHEMA, site)
    assert isinstance(target, dict)
    assert "enum" in target


@pytest.mark.spec("NAM-009.04")
def test_scalar_definition_without_an_enum_has_no_entry() -> None:
    sites = {site for t in MANIFEST["types"] for site in t["sites"]}
    scalars = [
        key
        for key, body in SCHEMA["definitions"].items()
        if isinstance(body, dict)
        and (body.get("type") == "string" or "$ref" in body)
        and "enum" not in body
        and "properties" not in body
        and "anyOf" not in body
        and "oneOf" not in body
    ]
    assert len(scalars) > 10
    assert {f"#/definitions/{key}" for key in scalars}.isdisjoint(sites)


@pytest.mark.spec("NAM-010.01")
def test_document_entry_records_its_body_field() -> None:
    entry = ENTRIES["SystemSecurityPlanDocument"]
    assert entry["kind"] == "document"
    assert entry["body-field"] == "system-security-plan"


@pytest.mark.spec("NAM-010.02")
def test_union_entry_records_each_branch() -> None:
    entry = ENTRIES["CatalogGroup"]
    assert entry["kind"] == "union"
    assert entry["variants"] == [
        {"property": "controls", "type": "CatalogGroupWithControls"},
        {"property": "groups", "type": "CatalogGroupWithGroups"},
    ]
    assert ENTRIES["CatalogGroupWithControls"]["kind"] == "object"
    assert ENTRIES["CatalogGroupWithGroups"]["kind"] == "object"


@pytest.mark.spec("NAM-010.03")
def test_enum_entry_records_whether_it_is_open() -> None:
    assert ENTRIES["HashAlgorithm"]["kind"] == "enum"
    assert ENTRIES["HashAlgorithm"]["closed"] is False
    assert ENTRIES["InsertControlsOrder"]["closed"] is True
    # The consumer holds the same fact: an open enum accepts a string that its
    # members do not list.
    adapter: TypeAdapter[Any] = TypeAdapter(models.Hash)
    assert adapter.validate_python({"algorithm": "x-new", "value": "v"})


@pytest.mark.spec("NAM-010.04")
def test_single_or_many_entry_records_its_item_type() -> None:
    entry = ENTRIES["MappingCollectionMappings"]
    assert entry["kind"] == "single-or-many"
    assert entry["item"] == "Mapping"


@pytest.mark.spec("NAM-011.01")
def test_enum_entry_holds_no_enum_value() -> None:
    entry = ENTRIES["HashAlgorithm"]
    assert set(entry) == {"name", "kind", "sites", "closed"}
    members = {m.value for m in models.HashAlgorithm}
    assert members
    assert not any(value in json.dumps(entry) for value in members)
    # The consumer rejects an enum value in an entry.
    changed = copy.deepcopy(MANIFEST)
    next(t for t in changed["types"] if t["name"] == "HashAlgorithm")["values"] = [
        "SHA-256"
    ]
    assert any("[names.schema.json]" in f for f in _validate(changed))


@pytest.mark.spec("NAM-011.02")
def test_object_entry_holds_no_field_name() -> None:
    entry = ENTRIES["Hash"]
    assert set(entry) == {"name", "kind", "sites"}
    assert "algorithm" not in json.dumps(entry)
    # The consumer rejects a field list in an entry.
    changed = copy.deepcopy(MANIFEST)
    next(t for t in changed["types"] if t["name"] == "Hash")["fields"] = ["algorithm"]
    assert any("[names.schema.json]" in f for f in _validate(changed))


@pytest.mark.spec("NAM-013.02")
def test_unknown_member_fails() -> None:
    changed = copy.deepcopy(MANIFEST)
    changed["types"][0]["unknown"] = True
    failures = _validate(changed)
    assert failures
    assert all(f.startswith("[names.schema.json]") for f in failures)
    assert any("names.json/types/0" in f for f in failures)
    top = copy.deepcopy(MANIFEST)
    top["unknown"] = True
    assert any("[names.schema.json]" in f for f in _validate(top))


@pytest.mark.spec("NAM-014.01")
def test_body_field_is_written_as_an_escaped_literal() -> None:
    # The pattern of a body field leaves no quote, backslash, or newline.
    pattern = NAMES_SCHEMA["definitions"]["key"]["pattern"]
    assert not re.search(r"['\"\\\n]", pattern.replace("\\", ""))
    changed = copy.deepcopy(MANIFEST)
    next(t for t in changed["types"] if t["kind"] == "document")["body-field"] = (
        "bad'field"
    )
    assert any("[names.schema.json]" in f for f in _validate(changed))
    # The generated module holds each body field as a string literal.
    tree = ast.parse(Path(models.__file__).read_text(encoding="utf-8"))
    literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    for entry in MANIFEST["types"]:
        if entry["kind"] == "document":
            assert entry["body-field"] in literals


@pytest.mark.spec("NAM-020.01")
def test_group_without_a_distinguishing_property_conforms_to_each_branch() -> None:
    variants = ENTRIES["CatalogGroup"]["variants"]
    assert {v["property"] for v in variants} == {"groups", "controls"}
    group = {"title": "G"}
    for variant in variants:
        cls = getattr(models, variant["type"])
        assert not cls.model_fields[variant["property"]].is_required()
        assert cls.model_validate(group).title == "G"
