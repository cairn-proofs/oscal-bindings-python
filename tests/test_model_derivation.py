"""The type names and kinds of the models follow the model-derivation spec.

The store derives the canonical names and writes them to the naming manifest;
the binding takes them from there (MDL-009). These tests apply the naming rules
of the spec, as a second and independent implementation, to the schema and to
the override data of the pinned artifact. They check that each name that the
rules give is the name in the manifest, and that ``oscal_bindings.v1.models``
holds a class of that name whose shape is the shape of the site in the schema.
So a binding that renamed a type, kept an ordinal name, or merged two types
would fail here.
"""

from __future__ import annotations

import collections
import copy
import enum
import json
import re
import types
from typing import Any

import pytest
from pydantic import BaseModel, RootModel, TypeAdapter
from support.model_instances import synthesize_instance
from support.scripts import load_script
from support.spec_artifact import ensure_spec_artifact

from oscal_bindings.v1 import models

pin = load_script("spec_artifact")
manifest_mod = load_script("manifest")
hoist_mod = load_script("hoist_names")

PATHS = pin.artifact_paths(ensure_spec_artifact())
MANIFEST: dict[str, Any] = manifest_mod.load_validated_manifest(PATHS)
SCHEMA: dict[str, Any] = json.loads(PATHS.schema.read_bytes())
OVERRIDES: dict[str, Any] = json.loads(
    (PATHS.names.parent / "overrides.json").read_text("utf-8")
)
ENTRIES: dict[str, dict[str, Any]] = {t["name"]: t for t in MANIFEST["types"]}
BY_SITE: dict[str, dict[str, Any]] = {
    site: entry for entry in MANIFEST["types"] for site in entry["sites"]
}
LOCAL_NAME_COUNT = collections.Counter(
    key.split(":", 1)[1] for key in SCHEMA["definitions"] if ":" in key
)
MODULE_PREFIX = "oscal-complete-oscal-"
DEFINITION = "#/definitions/" + MODULE_PREFIX
ROOT = "#"


def _pascal(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("-"))


def _is_branch(site: str) -> bool:
    """A site that is one branch of a union of the manifest."""
    match = re.fullmatch(r"(.*)/anyOf/\d+", site)
    return bool(match) and BY_SITE.get(match.group(1), {}).get("kind") == "union"


def _distinguishing(site: str) -> str:
    """The one property that the branch at ``site`` has and no other branch has."""
    union, _, index = site.rpartition("/anyOf/")
    branches = _site_node(union)["anyOf"]
    mine = branches[int(index)]
    others: set[str] = set()
    for i, other in enumerate(branches):
        if i != int(index):
            others |= set(other.get("properties", {}))
    (only,) = set(mine.get("properties", {})) - others
    return only


def _merged_first_site(site: str) -> str:
    for group in OVERRIDES["merges"]:
        if site in group:
            return str(group[0])
    return site


def derive(site: str) -> str:  # noqa: PLR0911 -- one return per rule
    """The canonical name of a site, by the rules of MDL-002 to MDL-018."""
    site = _merged_first_site(site)
    if site in OVERRIDES["names"]:
        return str(OVERRIDES["names"][site])
    if site.startswith("#/oneOf/"):
        wrapper = SCHEMA["oneOf"][int(site.rsplit("/", 1)[1])]
        (body,) = set(wrapper["properties"]) - {"$schema"}
        return f"{_pascal(body)}Document"
    if site == ROOT:
        return "OscalDocument"
    if _is_branch(site):  # MDL-006
        return derive(site.rsplit("/", 2)[0]) + "With" + _pascal(_distinguishing(site))
    tokens = site.split("/")
    if len(tokens) == 3:  # a definition, MDL-014 rule 1, MDL-015, MDL-005
        namespace, local = tokens[2].split(":")
        if LOCAL_NAME_COUNT[local] == 1:
            return _pascal(local)
        return _pascal(namespace.removeprefix(MODULE_PREFIX)) + _pascal(local)
    held = site
    if BY_SITE[site]["kind"] == "enum" and re.search(r"/(anyOf|allOf)/\d+$", site):
        held = site.rsplit("/", 2)[0]
        if len(held.split("/")) == 3:  # an enum that a definition holds, MDL-018
            return derive(held)
    if held.endswith("/items"):  # MDL-014 rule 3
        local = OVERRIDES["local-names"][held]
    else:  # MDL-014 rule 2
        local = held.rsplit("/", 1)[1]
    parent = held.rsplit("/properties/", 1)[0]
    while parent not in BY_SITE:
        parent = parent.rsplit("/", 1)[0]
    if _is_branch(parent):  # MDL-010: the parent of a branch's child is the union
        parent = parent.rsplit("/", 2)[0]
    return derive(parent) + _pascal(local)


def _site_node(site: str) -> Any:
    return manifest_mod.resolve_pointer(SCHEMA, site)


def _aliases(cls: type[BaseModel]) -> set[str]:
    return {f.alias or name for name, f in cls.model_fields.items()}


def _assert_class_has_site_shape(name: str, site: str) -> None:
    """The class of ``name`` is the class that the schema defines at ``site``."""
    kind = ENTRIES[name]["kind"]
    obj = getattr(models, name)
    node = _site_node(site)
    if kind == "object":
        assert isinstance(obj, type)
        assert issubclass(obj, BaseModel)
        assert _aliases(obj) == set(node.get("properties", {})), name
    elif kind == "document":
        assert issubclass(obj, BaseModel)
        assert _aliases(obj) == set(node["properties"]), name
    elif kind == "enum":
        assert issubclass(obj, enum.Enum)
        assert {m.value for m in obj} == set(node["enum"]), name
    elif kind == "union":
        assert isinstance(obj, types.UnionType)
        assert {v["type"] for v in ENTRIES[name]["variants"]} == {
            m.__name__ for m in obj.__args__
        }


def _check(site: str, name: str) -> None:
    assert derive(site) == name
    assert BY_SITE[site]["name"] == name
    _assert_class_has_site_shape(name, site)


D = DEFINITION
SSP_CI = f"{D}ssp:control-implementation"
CD_CI = f"{D}component-definition:control-implementation"
FT_STATUS = f"{D}assessment-common:finding-target/properties/status"
SC_STATUS = f"{D}implementation-common:system-component/properties/status"
MERGE = f"{D}profile:merge"
GROUP = f"{D}catalog:group"
RISK = f"{D}assessment-common:risk"
OBSERVATION = f"{D}assessment-common:observation"
BACK_MATTER = f"{D}metadata:back-matter"

# One entry for each example that the spec gives, with its scenario as the marker.
_RULE_EXAMPLES = [
    pytest.param(
        f"{D}metadata:hash",
        "Hash",
        marks=pytest.mark.spec("MDL-014.01"),
        id="MDL-014.01-Hash",
    ),
    pytest.param(
        f"{OBSERVATION}/properties/methods/items/anyOf/1",
        "ObservationMethod",
        marks=pytest.mark.spec("MDL-014.02"),
        id="MDL-014.02-ObservationMethod",
    ),
    pytest.param(
        f"{D}control-common:parameter",
        "Parameter",
        marks=pytest.mark.spec("MDL-015.01"),
        id="MDL-015.01-Parameter",
    ),
    pytest.param(
        f"{RISK}/properties/risk-log",
        "RiskLog",
        marks=pytest.mark.spec("MDL-017.01"),
        id="MDL-017.01-RiskLog",
    ),
    pytest.param(
        SSP_CI,
        "SspControlImplementation",
        marks=pytest.mark.spec("MDL-005.01"),
        id="MDL-005.01-SspControlImplementation",
    ),
    pytest.param(
        CD_CI,
        "ComponentDefinitionControlImplementation",
        marks=pytest.mark.spec("MDL-005.01"),
        id="MDL-005.01-ComponentDefinitionControlImplementation",
    ),
    pytest.param(
        f"{D}ssp:status",
        "Status",
        marks=pytest.mark.spec("MDL-005.03"),
        id="MDL-005.03-Status",
    ),
    pytest.param(
        SC_STATUS,
        "SystemComponentStatus",
        marks=pytest.mark.spec("MDL-005.03"),
        id="MDL-005.03-SystemComponentStatus",
    ),
    pytest.param(
        f"{MERGE}/anyOf/0",
        "MergeWithFlat",
        marks=pytest.mark.spec("MDL-006.01"),
        id="MDL-006.01-MergeWithFlat",
    ),
    pytest.param(
        f"{MERGE}/anyOf/1",
        "MergeWithAsIs",
        marks=pytest.mark.spec("MDL-006.01"),
        id="MDL-006.01-MergeWithAsIs",
    ),
    pytest.param(
        f"{MERGE}/anyOf/2",
        "MergeWithCustom",
        marks=pytest.mark.spec("MDL-006.01"),
        id="MDL-006.01-MergeWithCustom",
    ),
    pytest.param(
        f"{GROUP}/anyOf/0",
        "CatalogGroupWithGroups",
        marks=pytest.mark.spec("MDL-006.02"),
        id="MDL-006.02-CatalogGroupWithGroups",
    ),
    pytest.param(
        f"{GROUP}/anyOf/1",
        "CatalogGroupWithControls",
        marks=pytest.mark.spec("MDL-006.02"),
        id="MDL-006.02-CatalogGroupWithControls",
    ),
    pytest.param(
        MERGE, "Merge", marks=pytest.mark.spec("MDL-006.03"), id="MDL-006.03-Merge"
    ),
    pytest.param(
        SC_STATUS,
        "SystemComponentStatus",
        marks=pytest.mark.spec("MDL-010.01"),
        id="MDL-010.01-SystemComponentStatus",
    ),
    pytest.param(
        SC_STATUS,
        "SystemComponentStatus",
        marks=pytest.mark.spec("MDL-010.02"),
        id="MDL-010.02-SystemComponentStatus",
    ),
    pytest.param(
        FT_STATUS,
        "FindingTargetStatus",
        marks=pytest.mark.spec("MDL-010.02"),
        id="MDL-010.02-FindingTargetStatus",
    ),
    pytest.param(
        f"{BACK_MATTER}/properties/resources/items",
        "BackMatterResource",
        marks=pytest.mark.spec("MDL-010.03"),
        id="MDL-010.03-BackMatterResource",
    ),
    pytest.param(
        f"{BACK_MATTER}/properties/resources/items/properties/citation",
        "BackMatterResourceCitation",
        marks=pytest.mark.spec("MDL-010.03"),
        id="MDL-010.03-BackMatterResourceCitation",
    ),
    pytest.param(
        f"{D}assessment-common:task/properties/timing/anyOf/0/properties/on-date",
        "TaskTimingOnDate",
        marks=pytest.mark.spec("MDL-010.04"),
        id="MDL-010.04-TaskTimingOnDate",
    ),
    pytest.param(
        f"{RISK}/properties/risk-log",
        "RiskLog",
        marks=pytest.mark.spec("MDL-010.05"),
        id="MDL-010.05-RiskLog",
    ),
    pytest.param(
        f"{RISK}/properties/risk-log/properties/entries/items",
        "RiskLogEntry",
        marks=pytest.mark.spec("MDL-010.05"),
        id="MDL-010.05-RiskLogEntry",
    ),
    pytest.param(
        f"{D}poam:poam-item/properties/origins/items",
        "PoamItemOrigin",
        marks=pytest.mark.spec("MDL-010.06"),
        id="MDL-010.06-PoamItemOrigin",
    ),
    pytest.param(
        f"{D}control-common:parameter-selection/properties/how-many/allOf/1",
        "ParameterSelectionHowMany",
        marks=pytest.mark.spec("MDL-011.02"),
        id="MDL-011.02-ParameterSelectionHowMany",
    ),
    pytest.param(
        f"{D}metadata:hash/properties/algorithm/anyOf/1",
        "HashAlgorithm",
        marks=pytest.mark.spec("MDL-018.01"),
        id="MDL-018.01-HashAlgorithm",
    ),
    pytest.param(
        f"{D}assessment-common:risk-status/anyOf/1",
        "RiskStatus",
        marks=pytest.mark.spec("MDL-018.02"),
        id="MDL-018.02-RiskStatus",
    ),
    pytest.param(
        f"{FT_STATUS}/properties/state/allOf/1",
        "FindingTargetStatusState",
        marks=pytest.mark.spec("MDL-018.03"),
        id="MDL-018.03-FindingTargetStatusState",
    ),
    pytest.param(
        f"{FT_STATUS}/properties/reason/anyOf/1",
        "FindingTargetStatusReason",
        marks=pytest.mark.spec("MDL-018.03"),
        id="MDL-018.03-FindingTargetStatusReason",
    ),
    pytest.param(
        f"{D}ssp:status/properties/state/allOf/1",
        "StatusState",
        marks=pytest.mark.spec("MDL-018.04"),
        id="MDL-018.04-StatusState",
    ),
    pytest.param(
        f"{SC_STATUS}/properties/state/allOf/1",
        "SystemComponentStatusState",
        marks=pytest.mark.spec("MDL-018.04"),
        id="MDL-018.04-SystemComponentStatusState",
    ),
    pytest.param(
        f"{FT_STATUS}/properties/state/allOf/1",
        "FindingTargetStatusState",
        marks=pytest.mark.spec("MDL-018.04"),
        id="MDL-018.04-FindingTargetStatusState",
    ),
    pytest.param(
        f"{OBSERVATION}/properties/methods/items/anyOf/1",
        "ObservationMethod",
        marks=pytest.mark.spec("MDL-018.05"),
        id="MDL-018.05-ObservationMethod",
    ),
]


@pytest.mark.parametrize(("site", "name"), _RULE_EXAMPLES)
def test_example_of_the_naming_rules(site: str, name: str) -> None:
    """The rules, the manifest, and the model class agree on the example."""
    _check(site, name)


def test_the_rules_give_the_manifest_name_of_every_site() -> None:
    """Each site of the manifest has the name that the naming rules derive."""
    wrong = {
        site: (entry["name"], derive(site))
        for site, entry in BY_SITE.items()
        if derive(site) != entry["name"]
    }
    assert wrong == {}


def test_no_name_of_the_models_carries_an_ordinal() -> None:
    """MDL-001: a canonical name is not a generator ordinal such as ``Model1``."""
    names = {n for n, o in vars(models).items() if isinstance(o, type)}
    # ``Base64`` is a word of OSCAL, not an ordinal.
    assert {n for n in names if re.search(r"\d$", n.replace("Base64", ""))} == set()
    assert {n for n in ENTRIES if re.search(r"\d$", n.replace("Base64", ""))} == set()


@pytest.mark.spec("MDL-001.02")
def test_reordered_definitions_keep_every_name() -> None:
    """The hoist names a place by its pointer, so the order of definitions is moot."""
    reordered = copy.deepcopy(SCHEMA)
    reordered["definitions"] = dict(reversed(list(SCHEMA["definitions"].items())))
    assert list(reordered["definitions"]) != list(SCHEMA["definitions"])
    plain = hoist_mod.hoist(copy.deepcopy(SCHEMA), MANIFEST)
    other = hoist_mod.hoist(reordered, MANIFEST)
    assert other["definitions"] == plain["definitions"]
    assert set(other["definitions"]) >= set(ENTRIES) - {"OscalDocument"} - {
        n for n, e in ENTRIES.items() if e["kind"] == "document"
    }


@pytest.mark.spec("MDL-016.01")
def test_the_root_schema_is_oscal_document() -> None:
    assert derive(ROOT) == "OscalDocument"
    assert BY_SITE[ROOT]["name"] == "OscalDocument"
    assert ENTRIES["OscalDocument"]["kind"] == "document-union"
    assert issubclass(models.OscalDocument, RootModel)


_WRAPPERS = [
    "CatalogDocument",
    "ProfileDocument",
    "ComponentDefinitionDocument",
    "SystemSecurityPlanDocument",
    "AssessmentPlanDocument",
    "AssessmentResultsDocument",
    "PlanOfActionAndMilestonesDocument",
    "MappingCollectionDocument",
]


@pytest.mark.spec("MDL-002.01")
def test_a_wrapper_is_named_from_its_body_field() -> None:
    entry = ENTRIES["SystemSecurityPlanDocument"]
    assert entry["body-field"] == "system-security-plan"
    (site,) = entry["sites"]
    assert derive(site) == "SystemSecurityPlanDocument"
    body = models.SystemSecurityPlanDocument.model_fields["system_security_plan"]
    assert body.alias == "system-security-plan"
    assert body.is_required()


@pytest.mark.spec("MDL-002.02")
def test_the_schema_directive_is_not_the_body_field() -> None:
    for name in _WRAPPERS:
        entry = ENTRIES[name]
        assert entry["body-field"] != "$schema"
        (site,) = entry["sites"]
        assert "$schema" in _site_node(site)["properties"]
        # derive() reads the one property that is not "$schema"
        assert derive(site) == name
        fields = getattr(models, name).model_fields
        assert [f.alias or n for n, f in fields.items() if f.is_required()] == [
            entry["body-field"]
        ]
        assert fields["field_schema"].alias == "$schema"
        assert not fields["field_schema"].is_required()


@pytest.mark.spec("MDL-002.03")
def test_the_eight_wrapper_names() -> None:
    documents = {n for n, e in ENTRIES.items() if e["kind"] == "document"}
    assert documents == set(_WRAPPERS)
    assert {derive(s) for n in _WRAPPERS for s in ENTRIES[n]["sites"]} == set(_WRAPPERS)
    assert set(ENTRIES["OscalDocument"]["members"]) == set(_WRAPPERS)
    for name in _WRAPPERS:
        assert issubclass(getattr(models, name), BaseModel)


@pytest.mark.spec("MDL-005.02", "MDL-009.02")
def test_the_models_take_every_class_name_from_the_manifest() -> None:
    """A class of the models is a manifest name, and the manifest names are all there.

    The module-prefixed names (``SspControlImplementation``) are the names that the
    manifest records, so a binding that applied its own rule would differ.
    """
    classes = {
        name
        for name, obj in vars(models).items()
        if isinstance(obj, type)
        and obj.__module__ == models.__name__
        and (issubclass(obj, BaseModel) or issubclass(obj, enum.Enum))
        and "[" not in name
    }
    assert classes <= set(ENTRIES)
    for name in ENTRIES:
        assert hasattr(models, name), name
    for name in (
        "SspControlImplementation",
        "ComponentDefinitionControlImplementation",
    ):
        assert name in ENTRIES
        assert ENTRIES[name]["sites"] == [
            {"SspControlImplementation": SSP_CI}.get(name, CD_CI)
        ]


@pytest.mark.spec("MDL-006.01", "MDL-006.02")
def test_each_branch_is_named_from_the_union_and_its_own_property() -> None:
    """``<Union>With<Property>``, with a property that only the branch has."""
    for entry in MANIFEST["types"]:
        if entry["kind"] != "union":
            continue
        for variant in entry["variants"]:
            if any(  # a pinned override name takes precedence (MDL-006.02)
                site in OVERRIDES["names"] for site in ENTRIES[variant["type"]]["sites"]
            ):
                continue
            assert variant["type"] == entry["name"] + "With" + _pascal(
                variant["property"]
            )
            cls = getattr(models, variant["type"])
            assert issubclass(cls, BaseModel)
            assert variant["property"] in _aliases(cls)
            for other in entry["variants"]:
                if other is not variant:
                    assert other["property"] not in _aliases(cls)


@pytest.mark.spec("MDL-006.03")
def test_a_union_is_named_from_its_place_and_each_branch_starts_with_it() -> None:
    entry = ENTRIES["Merge"]
    assert entry["sites"] == [MERGE]
    assert {v["type"] for v in entry["variants"]} == {
        "MergeWithFlat",
        "MergeWithAsIs",
        "MergeWithCustom",
    }
    assert all(v["type"].startswith("Merge") for v in entry["variants"])


@pytest.mark.spec("MDL-003.01")
def test_a_scalar_wrapper_is_a_constrained_value_not_an_object() -> None:
    """``LocationUuid`` is an annotated ``str``; no scalar alias is a model class."""
    alias = models.LocationUuid
    assert not isinstance(alias, type)
    adapter = TypeAdapter(alias)
    uuid = "11111111-1111-4111-8111-111111111111"
    assert adapter.validate_python(uuid) == uuid
    assert type(adapter.validate_python(uuid)) is str
    with pytest.raises(ValueError, match="pattern"):
        adapter.validate_python("not-a-uuid")
    scalar_models = [
        n
        for n, o in vars(models).items()
        if isinstance(o, type)
        and issubclass(o, RootModel)
        and o.__module__ == models.__name__
        and "[" not in n
    ]
    assert set(scalar_models) <= {"OscalDocument", "MappingCollectionMappings"}


@pytest.mark.spec("MDL-003.02", "MDL-012.01")
def test_preserved_wrappers_stay_root_models_and_one_or_many_has_its_item() -> None:
    """Only the document union and the single-or-many type are root models."""
    root_models = {
        n
        for n, o in vars(models).items()
        if isinstance(o, type)
        and o.__module__ == models.__name__
        and issubclass(o, RootModel)
        and "[" not in n
    }
    assert root_models == {"OscalDocument", "MappingCollectionMappings"}
    entry = ENTRIES["MappingCollectionMappings"]
    assert entry["kind"] == "single-or-many"
    assert entry["item"] == "Mapping"
    assert entry["sites"] == [f"{D}mapping:mapping-collection/properties/mappings"]
    assert derive(entry["sites"][0]) == "MappingCollectionMappings"
    mappings = models.MappingCollectionMappings
    mapping = synthesize_instance(models.Mapping).model_dump(mode="json", by_alias=True)
    one = mappings.model_validate(mapping).root
    many = mappings.model_validate([mapping]).root
    assert isinstance(one, models.Mapping)
    assert isinstance(many, list)
    assert [type(m) for m in many] == [models.Mapping]
    assert ENTRIES["Mapping"]["kind"] == "object"


@pytest.mark.spec("MDL-013.01")
def test_a_shared_type_is_one_canonical_type() -> None:
    """Each document type holds the one ``Metadata`` class, not a copy of its own."""
    assert ENTRIES["Metadata"]["sites"] == [f"{D}metadata:metadata"]
    bodies = [
        models.Catalog,
        models.Profile,
        models.ComponentDefinition,
        models.SystemSecurityPlan,
        models.AssessmentPlan,
        models.AssessmentResults,
        models.PlanOfActionAndMilestones,
        models.MappingCollection,
    ]
    for body in bodies:
        annotation = body.model_fields["metadata"].annotation
        assert annotation is models.Metadata, body.__name__
    assert {n for n in vars(models) if n.endswith("Metadata")} == {"Metadata"}


@pytest.mark.spec("MDL-013.02", "MDL-020.01")
def test_same_local_name_and_other_structure_are_two_types_and_no_merge() -> None:
    ssp, component = (
        ENTRIES["SspControlImplementation"],
        ENTRIES["ComponentDefinitionControlImplementation"],
    )
    assert ssp is not component
    assert models.SspControlImplementation is not (
        models.ComponentDefinitionControlImplementation
    )
    assert _aliases(models.SspControlImplementation) != _aliases(
        models.ComponentDefinitionControlImplementation
    )
    # No merge lists them, and the manifest gives each its own single site.
    merged = {site for group in OVERRIDES["merges"] for site in group}
    assert not {SSP_CI, CD_CI} & merged
    assert len(ssp["sites"]) == len(component["sites"]) == 1
    assert not hasattr(models, "ControlImplementation")


@pytest.mark.spec("MDL-013.03")
def test_copies_in_union_branches_are_one_type_with_both_places() -> None:
    entry = ENTRIES["MetadataPartyExternalId"]
    party = f"{D}metadata:metadata/properties/parties/items"
    assert entry["sites"] == [
        f"{party}/anyOf/0/properties/external-ids/items",
        f"{party}/anyOf/1/properties/external-ids/items",
    ]
    # The two places differ only in the index of a union branch (MDL-013 rule 1)
    first, second = entry["sites"]
    assert first.replace("/anyOf/0/", "/anyOf/#/") == second.replace(
        "/anyOf/1/", "/anyOf/#/"
    )
    assert issubclass(models.MetadataPartyExternalId, BaseModel)
    assert not [
        n for n in vars(models) if re.fullmatch(r"MetadataParty\w*ExternalId\d", n)
    ]
    assert [n for n in ENTRIES if n.endswith("PartyExternalId")] == [
        "MetadataPartyExternalId"
    ]


@pytest.mark.spec("MDL-013.04")
def test_equal_enum_values_at_unrelated_places_do_not_merge() -> None:
    """Two enum sites with equal values stay two types without an explicit merge."""
    first = ENTRIES["HashAlgorithm"]["sites"][0]
    second = ENTRIES["RiskStatus"]["sites"][0]
    assert not {first, second} & {s for g in OVERRIDES["merges"] for s in g}
    schema = copy.deepcopy(SCHEMA)
    _site = manifest_mod.resolve_pointer
    _site(schema, second)["enum"] = list(_site(schema, first)["enum"])
    result = hoist_mod.hoist(schema, MANIFEST)["definitions"]
    assert result["HashAlgorithm"]["enum"] == result["RiskStatus"]["enum"]
    assert result["HashAlgorithm"] is not result["RiskStatus"]
    # the released models keep one class for each enum name, whatever the values
    assert models.HashAlgorithm is not models.RiskStatus
    by_name = {
        n: frozenset(m.value for m in getattr(models, n))
        for n, e in ENTRIES.items()
        if e["kind"] == "enum"
    }
    assert len(by_name) == 44


@pytest.mark.spec("MDL-019.01")
def test_identical_places_merge_into_one_type_with_both_places() -> None:
    """Each explicit merge of the overrides is one type with all its places.

    The hoist accepts the merge only if the places have the same body, so a
    release that hoists has merged identical places.
    """
    hoisted = hoist_mod.hoist(copy.deepcopy(SCHEMA), MANIFEST)
    for group in OVERRIDES["merges"]:
        entries = {BY_SITE[site]["name"] for site in group}
        assert len(entries) == 1, group
        (name,) = entries
        assert set(group) <= set(ENTRIES[name]["sites"])
        assert name in hoisted["definitions"]
        assert hasattr(models, name)
    bodies = [_site_node(site) for site in OVERRIDES["merges"][0]]
    stripped = [
        {k: v for k, v in body.items() if k not in {"title", "description"}}
        for body in bodies
    ]
    assert all(body == stripped[0] for body in stripped)


@pytest.mark.spec("MDL-011.03")
def test_an_open_enum_is_marked_open_and_accepts_other_values() -> None:
    entry = ENTRIES["HashAlgorithm"]
    assert entry["closed"] is False
    assert entry["sites"] == [f"{D}metadata:hash/properties/algorithm/anyOf/1"]
    assert issubclass(models.HashAlgorithm, enum.Enum)
    value = "0" * 64
    known = models.Hash.model_validate({"algorithm": "SHA-256", "value": value})
    other = models.Hash.model_validate({"algorithm": "x-other", "value": value})
    assert known.algorithm == models.HashAlgorithm("SHA-256").value
    assert other.algorithm == "x-other"
