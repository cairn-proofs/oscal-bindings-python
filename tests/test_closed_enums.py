"""Closed enums are Enum classes that accept their values only (design.md D6, #21).

A closed-enum field holds the Enum class, for example ``how_many:
ParameterSelectionHowMany | None``. An open-enum field is the union of a base
type (``str`` or ``AnyUrl``) and its Enum class, so it also accepts values
outside the enum. Both serialize to the value string.
"""

from __future__ import annotations

import enum
import json
import types
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Any, Union, get_args, get_origin

import pytest
from pydantic import ValidationError
from support.model_instances import OBJECT_MODELS, ModelCls, synthesize_instance
from support.scripts import load_script
from support.spec_artifact import corpus_root, ensure_spec_artifact

from oscal_bindings import (
    OscalParseError,
    parse_oscal,
    serialize_oscal,
    validate_oscal,
)
from oscal_bindings.v1 import models

if TYPE_CHECKING:
    from collections.abc import Iterator

NOT_A_MEMBER = "zz-not-a-member"


def _arms(annotation: Any) -> Iterator[tuple[Any, bool]]:
    """``(leaf type, inside a list)`` for each arm of a field annotation."""
    origin, args = get_origin(annotation), get_args(annotation)
    if origin is Annotated:
        yield from _arms(args[0])
    elif origin is Union or origin is types.UnionType:
        for arm in args:
            yield from _arms(arm)
    elif origin is list:
        yield from ((leaf, True) for leaf, _ in _arms(args[0]))
    else:
        yield annotation, False


@dataclass(frozen=True)
class EnumSite:
    """A field whose annotation holds ``enum_cls``."""

    enum_cls: type[enum.Enum]
    owner: ModelCls
    field: str
    alias: str
    is_list: bool
    # The annotation also has a base arm, for example ``str`` or ``AnyUrl``, that
    # takes values outside the enum: an open enum.
    is_open: bool


def _enum_sites() -> list[EnumSite]:
    sites = []
    for owner in OBJECT_MODELS:
        for name, info in owner.model_fields.items():
            arms = list(_arms(info.annotation))
            is_open = any(
                leaf is not type(None)
                and not (isinstance(leaf, type) and issubclass(leaf, enum.Enum))
                for leaf, _ in arms
            )
            sites.extend(
                EnumSite(leaf, owner, name, info.alias or name, is_list, is_open)
                for leaf, is_list in arms
                if isinstance(leaf, type) and issubclass(leaf, enum.Enum)
            )
    return sites


ENUM_SITES = _enum_sites()
# The first field of each closed enum, found by walking the models.
CLOSED_SITES: dict[str, EnumSite] = {}
for _site in ENUM_SITES:
    if not _site.is_open:
        CLOSED_SITES.setdefault(_site.enum_cls.__name__, _site)


@pytest.fixture(scope="module")
def manifest_enums() -> dict[str, bool]:
    """``{enum name: closed}`` for each enum entry of the naming manifest."""
    pin = load_script("spec_artifact")
    manifest = load_script("manifest").load_validated_manifest(
        pin.artifact_paths(ensure_spec_artifact())
    )
    return {
        entry["name"]: entry["closed"]
        for entry in manifest["types"]
        if entry["kind"] == "enum"
    }


def _how_many_catalog(how_many: str) -> str:
    """The corpus's minimal valid catalog with one parameter selection."""
    path = corpus_root() / "documents" / "valid" / "minimal-catalog.json"
    doc = json.loads(path.read_bytes())
    doc["catalog"]["params"] = [
        {"id": "p1", "select": {"how-many": how_many, "choice": ["a"]}}
    ]
    return json.dumps(doc)


def _parsed_selection(text: str) -> models.ParameterSelection:
    selection = parse_oscal(text).root.catalog.params[0].select  # type: ignore[union-attr]
    assert isinstance(selection, models.ParameterSelection)
    return selection


# --- ParameterSelectionHowMany ------------------------------------------------


def test_how_many_is_a_closed_enum() -> None:
    assert issubclass(models.ParameterSelectionHowMany, enum.Enum)
    assert {m.value for m in models.ParameterSelectionHowMany} == {"one", "one-or-more"}
    field = models.ParameterSelection.model_fields["how_many"]
    arms = {leaf for leaf, _ in _arms(field.annotation)}
    assert arms == {models.ParameterSelectionHowMany, type(None)}, arms


@pytest.mark.parametrize("value", ["one", "one-or-more"])
def test_how_many_accepts_each_value(value: str) -> None:
    selection = models.ParameterSelection.model_validate({"how-many": value})
    assert selection.how_many is models.ParameterSelectionHowMany(value)


def test_how_many_rejects_other_string_in_model() -> None:
    with pytest.raises(ValidationError) as info:
        models.ParameterSelection.model_validate({"how-many": "many"})
    assert [(e["type"], e["loc"]) for e in info.value.errors()] == [
        ("enum", ("how-many",))
    ]


def test_document_with_how_many_many_fails() -> None:
    text = _how_many_catalog("many")
    with pytest.raises(OscalParseError) as info:
        parse_oscal(text)
    assert any(
        e["type"] == "enum" and tuple(e["loc"])[-1] == "how-many"
        for e in info.value.errors
    ), info.value.errors
    assert validate_oscal(text) is False
    assert validate_oscal(_how_many_catalog("one")) is True


# --- Serialization ------------------------------------------------------------


def test_parsed_closed_enum_serializes_to_its_string() -> None:
    doc = parse_oscal(_how_many_catalog("one-or-more"))
    selection = _parsed_selection(serialize_oscal(doc))
    assert selection.how_many is models.ParameterSelectionHowMany("one-or-more")

    written = json.loads(serialize_oscal(doc))
    assert written["catalog"]["params"][0]["select"]["how-many"] == "one-or-more"
    assert '"how-many": "one-or-more"' in serialize_oscal(doc)
    dumped = doc.model_dump(mode="json")
    assert dumped["catalog"]["params"][0]["select"]["how-many"] == "one-or-more"


def test_plain_model_dump_returns_the_held_value() -> None:
    """Plain ``model_dump()`` returns the attribute value, closed or open.

    A closed-enum field always holds the Enum member, so plain ``model_dump()``
    returns the member. An open-enum field holds what its union picked: input
    ``"SHA-256"`` matches the ``str`` arm exactly, so the field holds the string,
    and an Enum member input stays a member. ``mode="json"`` writes the string
    in all cases.
    """
    closed = _parsed_selection(_how_many_catalog("one-or-more"))
    assert closed.model_dump()["how-many"] is closed.how_many
    assert closed.how_many is models.ParameterSelectionHowMany("one-or-more")

    open_from_str = models.Hash.model_validate({"algorithm": "SHA-256", "value": "a"})
    assert open_from_str.model_dump()["algorithm"] is open_from_str.algorithm
    assert type(open_from_str.algorithm) is str

    member = models.HashAlgorithm.SHA_256
    open_from_member = models.Hash.model_validate({"algorithm": member, "value": "a"})
    assert open_from_member.model_dump()["algorithm"] is member

    for model, key, value in (
        (closed, "how-many", "one-or-more"),
        (open_from_str, "algorithm", "SHA-256"),
        (open_from_member, "algorithm", "SHA-256"),
    ):
        out = model.model_dump(mode="json")[key]
        assert out == value
        assert type(out) is str


# --- Every closed enum --------------------------------------------------------


def test_closed_enums_match_the_manifest(manifest_enums: dict[str, bool]) -> None:
    """The enums with no base-type arm in models are the manifest's closed enums."""
    closed = {n for n, is_closed in manifest_enums.items() if is_closed}
    assert len(closed) == 20
    assert set(CLOSED_SITES) == closed
    for name in closed:
        assert issubclass(getattr(models, name), enum.Enum), name
    # A closed enum never appears in a field that also takes other values.
    open_uses = {s.enum_cls.__name__ for s in ENUM_SITES if s.is_open}
    assert not open_uses & closed, sorted(open_uses & closed)
    assert open_uses == {n for n, is_closed in manifest_enums.items() if not is_closed}


def _with_value(site: EnumSite, value: object) -> dict[str, Any]:
    data: dict[str, Any] = synthesize_instance(site.owner).model_dump(mode="json")
    data[site.alias] = [value] if site.is_list else value
    return data


@pytest.mark.parametrize("site", CLOSED_SITES.values(), ids=CLOSED_SITES.keys())
def test_closed_enum_accepts_member_value(site: EnumSite) -> None:
    member = next(iter(site.enum_cls))
    validated = site.owner.model_validate(_with_value(site, member.value))
    held = getattr(validated, site.field)
    assert (held[0] if site.is_list else held) is member


@pytest.mark.parametrize("site", CLOSED_SITES.values(), ids=CLOSED_SITES.keys())
def test_closed_enum_rejects_other_string(site: EnumSite) -> None:
    with pytest.raises(ValidationError) as info:
        site.owner.model_validate(_with_value(site, NOT_A_MEMBER))
    loc = (site.alias, 0) if site.is_list else (site.alias,)
    assert any(
        e["type"] == "enum" and tuple(e["loc"])[: len(loc)] == loc
        for e in info.value.errors()
    ), info.value.errors()
