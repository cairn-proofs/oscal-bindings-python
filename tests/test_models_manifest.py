"""The committed ``models.py`` against the naming manifest, at runtime.

``tests/test_postprocess.py`` checks the source text of ``models.py`` with the
guards of the post-processor. These tests import the module and check the
objects that users get:

1. Each manifest name is a module attribute of the kind that the manifest
   records, and each class or union alias of the module is a manifest name.
2. Each union alias accepts each variant and rejects the combination of the
   variant properties. ``MappingCollectionMappings`` accepts one ``Mapping`` or
   a non-empty list and round-trips both forms.
3. Each name that names a different type than in 0.2.x (README, "Upgrading to
   0.3.0", item 2) validates its own type, rejects the data of the other type,
   and is the type of the field that holds it.
"""

from __future__ import annotations

import copy
import enum
import json
import types
import typing
from typing import TYPE_CHECKING, Annotated, Any, Union, get_args, get_origin

import pytest
from pydantic import BaseModel, RootModel, TypeAdapter, ValidationError
from support.canonical_json import canonicalize
from support.model_instances import _value_for, synthesize_instance
from support.scripts import load_script
from support.spec_artifact import corpus_root, ensure_spec_artifact

from oscal_bindings import parse_mapping_collection, parse_oscal, serialize_oscal
from oscal_bindings.v1 import models

if TYPE_CHECKING:
    from collections.abc import Iterator


def _released_manifest() -> dict[str, Any]:
    pin = load_script("spec_artifact")
    manifest: dict[str, Any] = load_script("manifest").load_validated_manifest(
        pin.artifact_paths(ensure_spec_artifact())
    )
    return manifest


MANIFEST = _released_manifest()
ENTRIES: dict[str, dict[str, Any]] = {e["name"]: e for e in MANIFEST["types"]}
UNIONS = [e for e in MANIFEST["types"] if e["kind"] == "union"]


def _is_model(obj: object) -> bool:
    return isinstance(obj, type) and issubclass(obj, BaseModel)


def _runtime_kind(obj: object) -> str:
    """The manifest kind that a module attribute has at runtime."""
    if isinstance(obj, type) and issubclass(obj, enum.Enum):
        return "enum"
    if _is_model(obj) and issubclass(obj, RootModel):  # type: ignore[arg-type]
        return "root model"
    if _is_model(obj):
        return "class"
    if isinstance(obj, types.UnionType):
        return "union"
    return f"other ({type(obj).__name__})"


#: The runtime kind that each manifest kind requires.
EXPECTED_KIND = {
    "object": "class",
    "document": "class",
    "enum": "enum",
    "union": "union",
    "single-or-many": "root model",
    "document-union": "root model",
}


# ---------------------------------------------------------------------------
# 1. Names and kinds
# ---------------------------------------------------------------------------


def test_manifest_kind_counts() -> None:
    """The released manifest has the kinds that the change was planned for."""
    counts: dict[str, int] = {}
    for entry in MANIFEST["types"]:
        counts[entry["kind"]] = counts.get(entry["kind"], 0) + 1
    assert counts == {
        "object": 177,
        "document": 8,
        "enum": 44,
        "union": 13,
        "single-or-many": 1,
        "document-union": 1,
    }


def test_each_manifest_name_has_its_kind_at_runtime() -> None:
    wrong = {
        name: _runtime_kind(getattr(models, name, None))
        for name, entry in ENTRIES.items()
        if _runtime_kind(getattr(models, name, None)) != EXPECTED_KIND[entry["kind"]]
    }
    assert wrong == {}


def test_each_class_of_the_module_is_a_manifest_name() -> None:
    """No model or enum class of ``models`` has a name outside the manifest."""
    classes = {
        name
        for name, obj in vars(models).items()
        if isinstance(obj, type)
        and obj.__module__ == models.__name__
        and (_is_model(obj) or issubclass(obj, enum.Enum))
    }
    assert classes - set(ENTRIES) == set()
    # A class is reachable under its own name only, not as a second binding.
    assert all(getattr(models, name).__name__ == name for name in classes)


def test_each_union_value_of_the_module_is_a_manifest_union() -> None:
    unions = {
        name for name, obj in vars(models).items() if isinstance(obj, types.UnionType)
    }
    assert unions == {e["name"] for e in UNIONS}


def test_each_document_wraps_one_body() -> None:
    """A ``document`` class has one required field, the body, beside ``$schema``."""
    for name, entry in ENTRIES.items():
        if entry["kind"] != "document":
            continue
        fields = getattr(models, name).model_fields
        required = [f for f in fields.values() if f.is_required()]
        assert len(required) == 1, name
        assert {f.alias for f in fields.values() if not f.is_required()} == {
            "$schema"
        }, name
        assert _is_model(required[0].annotation), name


# ---------------------------------------------------------------------------
# 2. Union aliases and MappingCollectionMappings
# ---------------------------------------------------------------------------


def _field_for_alias(cls: type[BaseModel], key: str) -> Any:
    for name, info in cls.model_fields.items():
        if (info.alias or name) == key:
            return info
    msg = f"{cls.__name__} has no field with the key {key!r}"
    raise AssertionError(msg)


def _variant_data(variant: dict[str, Any]) -> dict[str, Any]:
    """Valid data for ``variant`` that sets its discriminating property."""
    cls = getattr(models, variant["type"])
    data: dict[str, Any] = synthesize_instance(cls).model_dump(mode="json")
    if variant["property"] not in data:
        info = _field_for_alias(cls, variant["property"])
        value = _value_for(info.annotation, list(info.metadata), 1)
        filled = cls.model_validate({**data, variant["property"]: value})
        data = filled.model_dump(mode="json")
    assert variant["property"] in data, variant
    return data


def _union_variant_params() -> Iterator[Any]:
    for entry in UNIONS:
        for variant in entry["variants"]:
            yield pytest.param(
                entry["name"], variant, id=f"{entry['name']}-{variant['type']}"
            )


@pytest.mark.parametrize(("alias", "variant"), list(_union_variant_params()))
def test_union_alias_selects_each_variant(alias: str, variant: dict[str, Any]) -> None:
    data = _variant_data(variant)
    adapter: TypeAdapter[Any] = TypeAdapter(getattr(models, alias))
    value = adapter.validate_python(data)
    assert type(value) is getattr(models, variant["type"])
    assert adapter.dump_python(value, mode="json") == data


@pytest.mark.parametrize("entry", UNIONS, ids=[e["name"] for e in UNIONS])
def test_union_alias_rejects_the_combination_of_variants(entry: dict[str, Any]) -> None:
    """Data with the property of every variant matches no variant."""
    combined: dict[str, Any] = {}
    for variant in entry["variants"]:
        combined.update(_variant_data(variant))
    adapter: TypeAdapter[Any] = TypeAdapter(getattr(models, entry["name"]))
    with pytest.raises(ValidationError) as info:
        adapter.validate_python(combined)
    assert any(e["type"] == "extra_forbidden" for e in info.value.errors())


def test_catalog_group_with_groups_and_controls_fails() -> None:
    adapter: TypeAdapter[Any] = TypeAdapter(models.CatalogGroup)
    with pytest.raises(ValidationError) as info:
        adapter.validate_python(
            {
                "title": "G",
                "controls": [{"id": "c", "title": "C"}],
                "groups": [{"title": "H"}],
            }
        )
    rejected = {(e["loc"][0], e["loc"][1]) for e in info.value.errors()}
    assert rejected == {
        ("CatalogGroupWithControls", "groups"),
        ("CatalogGroupWithGroups", "controls"),
    }


def test_union_without_a_variant_property_selects_the_first_variant() -> None:
    """design.md D2: pydantic selects the first variant in manifest order."""
    value = TypeAdapter(models.Parameter).validate_python({"id": "p"})
    assert type(value) is models.ParameterWithSelect


def _corpus_mapping_collection() -> dict[str, Any]:
    path = corpus_root() / "documents" / "valid" / "mapping-collection.json"
    data: dict[str, Any] = json.loads(path.read_bytes())
    return data


class TestMappingCollectionMappings:
    @pytest.fixture
    def mapping(self) -> dict[str, Any]:
        mapping: dict[str, Any] = _corpus_mapping_collection()["mapping-collection"][
            "mappings"
        ][0]
        return mapping

    def test_one_mapping_validates_as_the_item(self, mapping: dict[str, Any]) -> None:
        value = models.MappingCollectionMappings.model_validate(mapping)
        assert isinstance(value.root, models.Mapping)

    def test_a_list_validates_as_a_list(self, mapping: dict[str, Any]) -> None:
        other = copy.deepcopy(mapping)
        other["uuid"] = "6d9f3c2b-0e4a-4b8f-a7d1-3f5a9b2e4c51"
        value = models.MappingCollectionMappings.model_validate([mapping, other])
        assert isinstance(value.root, list)
        assert [m.uuid for m in value.root] == [mapping["uuid"], other["uuid"]]

    def test_an_empty_list_fails(self) -> None:
        with pytest.raises(ValidationError) as info:
            models.MappingCollectionMappings.model_validate([])
        assert any(e["type"] == "too_short" for e in info.value.errors())

    @pytest.mark.parametrize("value", [None, "x", [None], {}])
    def test_other_values_fail(self, value: object) -> None:
        with pytest.raises(ValidationError):
            models.MappingCollectionMappings.model_validate(value)

    @pytest.mark.parametrize("form", ["one", "list"])
    def test_document_round_trips_byte_identically(
        self, form: str, mapping: dict[str, Any]
    ) -> None:
        doc = _corpus_mapping_collection()
        if form == "one":
            doc["mapping-collection"]["mappings"] = mapping
        text = json.dumps(doc)

        parsed = parse_mapping_collection(text)
        written = serialize_oscal(parse_oscal(text))
        assert canonicalize(written) == canonicalize(text)
        # Serialize -> parse -> serialize is a fixed point, byte for byte.
        assert serialize_oscal(parse_oscal(written)) == written
        held = parsed.mapping_collection.mappings.root
        assert isinstance(held, models.Mapping if form == "one" else list)


# ---------------------------------------------------------------------------
# 3. Names that name a different type than in 0.2.x
# ---------------------------------------------------------------------------


def _leaves(annotation: Any) -> set[Any]:
    origin, args = get_origin(annotation), get_args(annotation)
    if origin is Annotated:
        return _leaves(args[0])
    if origin in {Union, types.UnionType, list}:
        return set().union(*(_leaves(arg) for arg in args))
    return {annotation}


#: ``(owner, field, type)``: the field of each reused name and of the type
#: that had the name in 0.2.x.
FIELD_TYPES = [
    (models.SystemCharacteristics, "status", models.Status),
    (models.SystemComponent, "status", models.SystemComponentStatus),
    (models.Finding, "origins", models.Origin),
    (models.Observation, "origins", models.Origin),
    (models.Risk, "origins", models.Origin),
    (models.PoamItem, "origins", models.PoamItemOrigin),
    (models.PlanOfActionAndMilestones, "local_definitions", models.LocalDefinitions),
    (
        models.AssessmentPlan,
        "local_definitions",
        models.AssessmentPlanLocalDefinitions,
    ),
    (models.MergeWithFlat, "flat", models.MergeFlat),
    (models.MergeWithCustom, "custom", models.MergeCustom),
]


@pytest.mark.parametrize(
    ("owner", "field", "expected"),
    FIELD_TYPES,
    ids=[f"{o.__name__}.{f}" for o, f, _ in FIELD_TYPES],
)
def test_reused_name_is_the_type_of_its_field(
    owner: type[BaseModel], field: str, expected: type[BaseModel]
) -> None:
    assert _leaves(owner.model_fields[field].annotation) - {type(None)} == {expected}


ACTOR = {
    "type": "tool",
    "actor-uuid": "11111111-1111-4111-8111-111111111111",
}
TASK = {"task-uuid": "11111111-1111-4111-8111-111111111111"}


def test_status_is_the_status_of_the_system() -> None:
    """Only the system status has the state ``under-major-modification``."""
    data = {"state": "under-major-modification"}
    assert models.Status.model_validate(data).state.value == data["state"]
    with pytest.raises(ValidationError):
        models.SystemComponentStatus.model_validate(data)
    both = {"state": "operational"}
    assert (
        models.SystemComponentStatus.model_validate(both).state.value == "operational"
    )


def test_origin_has_related_tasks_and_poam_item_origin_does_not() -> None:
    data = {"actors": [ACTOR], "related-tasks": [TASK]}
    origin = models.Origin.model_validate(data)
    assert origin.related_tasks is not None
    with pytest.raises(ValidationError) as info:
        models.PoamItemOrigin.model_validate(data)
    assert [(e["type"], e["loc"]) for e in info.value.errors()] == [
        ("extra_forbidden", ("related-tasks",))
    ]
    assert models.PoamItemOrigin.model_validate({"actors": [ACTOR]}).actors


def test_local_definitions_is_the_poam_type() -> None:
    poam_only = {
        "assessment-assets": {"assessment-platforms": [{"uuid": TASK["task-uuid"]}]}
    }
    assert models.LocalDefinitions.model_validate(poam_only).assessment_assets
    with pytest.raises(ValidationError):
        models.AssessmentPlanLocalDefinitions.model_validate(poam_only)
    ap_only = {"users": [{"uuid": TASK["task-uuid"]}]}
    assert models.AssessmentPlanLocalDefinitions.model_validate(ap_only).users
    with pytest.raises(ValidationError):
        models.LocalDefinitions.model_validate(ap_only)


def test_merge_flat_is_the_empty_flat_directive() -> None:
    assert models.MergeFlat.model_fields == {}
    assert models.MergeFlat.model_validate({}).model_dump() == {}
    with pytest.raises(ValidationError):
        models.MergeFlat.model_validate({"flat": {}})
    merge = models.MergeWithFlat.model_validate({"flat": {}})
    assert isinstance(merge.flat, models.MergeFlat)


def test_merge_custom_is_the_custom_grouping() -> None:
    custom = {"groups": [{"title": "G"}]}
    assert models.MergeCustom.model_validate(custom).groups
    with pytest.raises(ValidationError):
        models.MergeCustom.model_validate({"custom": custom})
    merge = models.MergeWithCustom.model_validate({"custom": custom})
    assert isinstance(merge.custom, models.MergeCustom)


def test_runtime_type_hints_resolve() -> None:
    """Every model's annotations resolve, so no union alias is a dangling name."""
    for name, entry in ENTRIES.items():
        if entry["kind"] in {"object", "document"}:
            typing.get_type_hints(getattr(models, name), include_extras=True)
