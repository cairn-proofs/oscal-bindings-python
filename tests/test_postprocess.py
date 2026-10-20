"""Tests for the codegen post-processor (`scripts/postprocess_models.py`).

The post-processor completes the codegen output of the hoisted schema: phase 1
(scalar collapse and pattern fixes), the union aliases, `OscalDocument`,
`MappingCollectionMappings`, and the scalar names. Then three guards compare
the module with the naming manifest. The tests run the steps on small copies
of generated source with a small manifest, and they check the committed
`models.py` against the released manifest.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import typing
from typing import TYPE_CHECKING, Any

import pytest
from pydantic import RootModel, TypeAdapter, ValidationError
from support.scripts import load_script
from support.spec_artifact import ensure_spec_artifact

from oscal_bindings.v1 import models

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path
    from types import ModuleType

pp: ModuleType = load_script("postprocess_models")
PostprocessError = pp.PostprocessError

HEADER = (
    "from __future__ import annotations\n"
    "\n"
    "from enum import Enum\n"
    "from typing import Annotated\n"
    "\n"
    "from oscal_bindings.v1._base import OscalBaseModel\n"
    "from pydantic import ConfigDict, EmailStr, Field, RootModel\n"
)

#: A schema whose namespaced definition keys name the scalar aliases.
SCHEMA: dict[str, Any] = {
    "definitions": {
        "oscal-complete-oscal-metadata:location-uuid": {"type": "string"},
        "oscal-complete-oscal-metadata:email-address": {"type": "string"},
        "TokenDatatype": {"type": "string"},
    }
}


def _object(name: str, *fields: str) -> str:
    body = "".join(f"    {field}\n" for field in fields) or "    pass\n"
    return f"\n\nclass {name}(OscalBaseModel):\n{body}"


def _enum(name: str, *values: str) -> str:
    body = "".join(f"    {v} = '{v}'\n" for v in values)
    return f"\n\nclass {name}(Enum):\n{body}"


#: The codegen output for the small manifest below, before post-processing.
RAW = (
    HEADER
    + _enum("HashAlgorithm", "sha")
    + _object("Mapping", "uuid: str")
    # Phase 1 reads the 10 lines above a pattern, so the imports stay out of reach.
    + "\n\nclass OscalCompleteOscalMetadataLocationUuid(RootModel[str]):\n"
    "    root: Annotated[str, Field(pattern='^[0-9a-f]+$', title='Location')]\n"
    + "\n\nclass TokenDatatype(RootModel[str]):\n"
    "    root: Annotated[str, Field(pattern='^\\\\S+$')]\n"
    + "\n\nclass MappingCollectionMappings1(RootModel[list[Mapping]]):\n"
    "    root: Annotated[list[Mapping], Field(min_length=1)]\n"
    + _object("GroupWithControls", "controls: list[str]")
    + _object(
        "GroupWithGroups",
        "groups: list[GroupWithControls | GroupWithGroups] | None = None",
        "location: OscalCompleteOscalMetadataLocationUuid | None = None",
    )
    + _object(
        "Catalog",
        "groups: Annotated[\n"
        "        list[GroupWithGroups | GroupWithControls] | None,\n"
        "        Field(min_length=1),\n"
        "    ] = None",
        "algorithm: TokenDatatype | HashAlgorithm | None = None",
    )
    + _object("MappingCollection", "mappings: Mapping | MappingCollectionMappings1")
    + _object("CatalogDocument", "catalog: Catalog")
    + _object("MappingCollectionDocument", "mapping_collection: MappingCollection")
    + "\n\nclass Model(RootModel[CatalogDocument | MappingCollectionDocument]):\n"
    "    root: CatalogDocument | MappingCollectionDocument\n"
    + "\n\nGroupWithGroups.model_rebuild()\n"
)


def _manifest(*extra: dict[str, Any]) -> dict[str, Any]:
    types: list[dict[str, Any]] = [
        {"name": "HashAlgorithm", "kind": "enum", "closed": False},
        {"name": "Mapping", "kind": "object"},
        {
            "name": "MappingCollectionMappings",
            "kind": "single-or-many",
            "item": "Mapping",
        },
        {"name": "GroupWithControls", "kind": "object"},
        {"name": "GroupWithGroups", "kind": "object"},
        {
            "name": "Group",
            "kind": "union",
            "variants": [
                {"type": "GroupWithControls", "property": "controls"},
                {"type": "GroupWithGroups", "property": "groups"},
            ],
        },
        {"name": "Catalog", "kind": "object"},
        {"name": "MappingCollection", "kind": "object"},
        {"name": "CatalogDocument", "kind": "document"},
        {"name": "MappingCollectionDocument", "kind": "document"},
        {
            "name": "OscalDocument",
            "kind": "document-union",
            "members": ["CatalogDocument", "MappingCollectionDocument"],
        },
    ]
    return {"format": 1, "types": [*types, *extra]}


@pytest.fixture(scope="module")
def done() -> str:
    result: str = pp.postprocess(RAW, _manifest(), SCHEMA)
    return result


def _failures(content: str, manifest: dict[str, Any] | None = None) -> list[str]:
    with pytest.raises(PostprocessError) as info:
        pp.postprocess(content, manifest or _manifest(), SCHEMA)
    failures: list[str] = info.value.failures
    return failures


@pytest.fixture(scope="module")
def generated(done: str, tmp_path_factory: pytest.TempPathFactory) -> Iterator[Any]:
    """The post-processed small module, imported from a file."""
    path = tmp_path_factory.mktemp("generated") / "generated_under_test.py"
    path.write_text(done)
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        del sys.modules[spec.name]


# ---------------------------------------------------------------------------
# Added types
# ---------------------------------------------------------------------------


class TestUnionAliases:
    def test_alias_lists_the_variants_in_manifest_order(self, done: str) -> None:
        assert "Group: TypeAlias = GroupWithControls | GroupWithGroups\n" in done

    def test_alias_follows_the_last_variant_class(self, done: str) -> None:
        lines = done.split("\n")
        alias = lines.index("Group: TypeAlias = GroupWithControls | GroupWithGroups")
        last_variant = lines.index("class GroupWithGroups(OscalBaseModel):")
        catalog = lines.index("class Catalog(OscalBaseModel):")
        assert last_variant < alias < catalog

    def test_inline_unions_of_the_variant_set_use_the_alias(self, done: str) -> None:
        """The match ignores the order of the names and keeps ``None``."""
        assert "groups: list[Group] | None = None" in done
        assert "list[Group] | None,\n" in done
        assert "GroupWithGroups | GroupWithControls" not in done
        assert "GroupWithControls | GroupWithGroups]" not in done

    def test_type_alias_is_imported(self, done: str) -> None:
        assert "from typing import Annotated, TypeAlias\n" in done

    def test_a_partial_or_larger_set_stays_inline(self) -> None:
        source = (
            RAW
            + _object("Other", "x: GroupWithControls | None = None")
            + _object("Wider", "y: GroupWithControls | GroupWithGroups | Mapping")
        )
        manifest = _manifest(
            {"name": "Other", "kind": "object"}, {"name": "Wider", "kind": "object"}
        )
        result = pp.postprocess(source, manifest, SCHEMA)
        assert "x: GroupWithControls | None = None" in result
        assert "y: GroupWithControls | GroupWithGroups | Mapping" in result

    def test_a_long_alias_is_wrapped(self) -> None:
        text = pp._alias_text("Name", ["A" * 40, "B" * 40])  # noqa: SLF001
        assert text == f"Name: TypeAlias = (\n    {'A' * 40}\n    | {'B' * 40}\n)"

    def test_a_missing_variant_class_fails(self) -> None:
        source = RAW.replace(
            "class GroupWithControls(OscalBaseModel):",
            "class Elsewhere(OscalBaseModel):",
        )
        failures = _failures(source)
        assert any("GroupWithControls are not defined" in f for f in failures)

    def test_the_generated_module_resolves_the_alias(self, generated: Any) -> None:
        catalog = generated.Catalog.model_validate(
            {"groups": [{"controls": ["a"]}, {"groups": [{"controls": ["b"]}]}]}
        )
        assert type(catalog.groups[0]).__name__ == "GroupWithControls"
        assert type(catalog.groups[1]).__name__ == "GroupWithGroups"


class TestOscalDocument:
    def test_root_model_over_the_documents_takes_the_manifest_name(
        self, done: str
    ) -> None:
        assert "class OscalDocument(RootModel[CatalogDocument | " in done
        assert "class Model(" not in done

    def test_no_matching_root_model_fails(self) -> None:
        source = RAW.replace(
            "class Model(RootModel[CatalogDocument | MappingCollectionDocument]):",
            "class Model(RootModel[CatalogDocument]):",
        )
        failures = _failures(source)
        assert any(
            "OscalDocument: expected one RootModel over the 2 document types" in f
            for f in failures
        )


class TestMappingCollectionMappings:
    def test_root_model_of_one_item_or_a_list(self, done: str) -> None:
        assert (
            "class MappingCollectionMappings(RootModel[Mapping | list[Mapping]]):\n"
            "    root: Mapping | Annotated[list[Mapping], Field(min_length=1)]\n"
        ) in done
        assert "MappingCollectionMappings1" not in done

    def test_field_takes_the_entry_name(self, done: str) -> None:
        assert "mappings: MappingCollectionMappings\n" in done

    def test_one_item_or_a_non_empty_list_validates(self, generated: Any) -> None:
        cls = generated.MappingCollection
        one = cls.model_validate({"mappings": {"uuid": "u"}})
        many = cls.model_validate({"mappings": [{"uuid": "u"}, {"uuid": "v"}]})
        assert one.model_dump()["mappings"] == {"uuid": "u"}
        assert many.model_dump()["mappings"] == [{"uuid": "u"}, {"uuid": "v"}]
        with pytest.raises(ValidationError):
            cls.model_validate({"mappings": []})

    def test_no_list_root_model_fails(self) -> None:
        source = RAW.replace(
            "mappings: Mapping | MappingCollectionMappings1", "mappings: Mapping"
        )
        failures = _failures(source)
        assert any(
            "MappingCollectionMappings: expected one RootModel of list[Mapping]" in f
            for f in failures
        )


class TestScalarAliases:
    def test_namespaced_scalar_keeps_its_local_name(self, done: str) -> None:
        assert "LocationUuid = Annotated[str, Field(pattern=" in done
        assert "location: LocationUuid | None = None" in done
        assert "OscalCompleteOscal" not in done

    def test_scalar_without_a_prefix_keeps_its_name(self, done: str) -> None:
        assert "TokenDatatype = Annotated[str, Field(pattern=" in done

    def test_open_enum_field_keeps_the_base_alias(self, done: str) -> None:
        assert "algorithm: TokenDatatype | HashAlgorithm | None = None" in done

    def test_only_scalar_aliases_are_renamed(self) -> None:
        """A class with a namespaced name is not renamed, so guard 2 reports it."""
        source = RAW + (
            "\n\nclass OscalCompleteOscalMetadataEmailAddress(OscalBaseModel):\n"
            "    x: str\n"
        )
        failures = _failures(source)
        assert any(
            "OscalCompleteOscalMetadataEmailAddress" in f and "[guard 2]" in f
            for f in failures
        )


# ---------------------------------------------------------------------------
# Phase 1
# ---------------------------------------------------------------------------


class TestPhase1:
    def test_scalar_root_model_collapses_to_annotated(self) -> None:
        source = (
            "class Token(RootModel[str]):\n"
            "    root: Annotated[str, Field(pattern='^x$')]\n"
        )
        assert pp.collapse_scalar_root_models(source).startswith(
            "Token = Annotated[str, Field(pattern='^x$')]"
        )

    def test_multi_line_scalar_root_model_collapses(self) -> None:
        source = (
            "class Token(\n    RootModel[str]\n):\n"
            "    root: Annotated[\n        str, Field(pattern='^x$')\n    ]\n"
        )
        result = pp.collapse_scalar_root_models(source)
        assert result.startswith("Token = Annotated[\n        str, Field(")

    def test_preserved_and_union_root_models_stay(self) -> None:
        source = (
            "class Keep(RootModel[str]):\n    root: str\n\n\n"
            "class Either(RootModel[A | B]):\n    root: A | B\n"
        )
        result = pp.collapse_scalar_root_models(source, frozenset({"Keep"}))
        assert result == source

    def test_email_pattern_is_removed(self) -> None:
        source = "x: Annotated[EmailStr, Field(pattern='^.+@.+$', title='E')]"
        assert pp.fix_email_str_patterns(source) == (
            "x: Annotated[EmailStr, Field(title='E')]"
        )

    def test_non_string_pattern_is_removed(self) -> None:
        source = (
            "x: Annotated[\n    AwareDatetime,\n    Field(pattern='^d$', title='T'),\n]"
        )
        assert "pattern=" not in pp.fix_non_string_patterns(source)

    def test_string_pattern_stays(self) -> None:
        source = "x: Annotated[\n    str,\n    Field(pattern='^d$', title='T'),\n]"
        assert pp.fix_non_string_patterns(source) == source


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------


class TestGuards:
    def test_output_of_the_small_manifest_passes(self, done: str) -> None:
        assert pp.guard_failures(done, _manifest()) == []

    def test_every_missing_manifest_name_is_listed(self, done: str) -> None:
        manifest = _manifest(
            {"name": "Absent", "kind": "object"},
            {"name": "AlsoAbsent", "kind": "union", "variants": []},
        )
        failures = pp.guard_failures(done, manifest)
        assert failures == [
            "[guard 1] the manifest name Absent (object) is missing",
            "[guard 1] the manifest name AlsoAbsent (union) is missing",
        ]

    def test_a_name_in_the_wrong_form_fails(self, done: str) -> None:
        manifest = _manifest()
        for entry in manifest["types"]:
            if entry["name"] == "Mapping":
                entry["kind"] = "enum"
        failures = pp.guard_failures(done, manifest)
        assert failures == ["[guard 1] Mapping (enum) is defined as class, not as enum"]

    def test_every_class_outside_the_manifest_is_listed(self, done: str) -> None:
        content = done + _object("Stray", "x: str") + _enum("StrayEnum", "a")
        failures = pp.guard_failures(content, _manifest())
        assert len(failures) == 2
        assert failures[0].startswith("[guard 2] Stray (line ")
        assert failures[0].endswith(") is defined as class outside the manifest")
        assert failures[1].startswith("[guard 2] StrayEnum (line ")
        assert failures[1].endswith(") is defined as enum outside the manifest")

    def test_every_scalar_alias_with_a_manifest_name_is_listed(self) -> None:
        manifest = _manifest(
            {"name": "LocationUuid", "kind": "object"},
            {"name": "TokenDatatype", "kind": "object"},
        )
        failures = _failures(RAW, manifest)
        scalar = [f for f in failures if "has a manifest name" in f]
        assert len(scalar) == 2
        assert "the scalar alias LocationUuid" in scalar[0]
        assert "the scalar alias TokenDatatype" in scalar[1]

    def test_every_duplicate_name_is_listed(self, done: str) -> None:
        content = (
            done
            + _object("Catalog", "again: str")
            + _object("Mapping", "again: str")
            + _object("Mapping", "third: str")
        )
        failures = pp.guard_failures(content, _manifest())
        duplicates = [f for f in failures if "is defined" in f]
        assert len(duplicates) == 2
        assert duplicates[0].startswith("[guard 3] Catalog is defined 2 times")
        assert duplicates[1].startswith("[guard 3] Mapping is defined 3 times")

    def test_all_guards_report_in_one_error(self) -> None:
        source = RAW + _object("Stray", "x: str") + _object("Catalog", "again: str")
        manifest = _manifest({"name": "Absent", "kind": "object"})
        failures = _failures(source, manifest)
        assert [f[:9] for f in failures] == ["[guard 1]", "[guard 2]", "[guard 3]"]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestCli:
    def test_defaults_resolve_independently(self, tmp_path: Path) -> None:
        models_path = tmp_path / "models.py"
        args = pp.parse_args(["--models", str(models_path)])
        assert args.models == models_path
        assert args.schema == pp.DEFAULT_SCHEMA_PATH
        args = pp.parse_args([])
        assert args.models == pp.DEFAULT_MODELS_PATH
        assert args.schema == pp.DEFAULT_SCHEMA_PATH

    def test_defaults_point_at_existing_files(self) -> None:
        assert pp.DEFAULT_MODELS_PATH.exists()
        assert pp.DEFAULT_SCHEMA_PATH.exists()

    @pytest.fixture
    def files(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        monkeypatch.setattr(pp, "load_manifest", _manifest)
        (tmp_path / "schema.json").write_text(json.dumps(SCHEMA))
        (tmp_path / "models.py").write_text(RAW)
        return tmp_path

    def _run(self, files: Path) -> int:
        status: int = pp.main(
            [
                "--models",
                str(files / "models.py"),
                "--schema",
                str(files / "schema.json"),
            ]
        )
        return status

    def test_main_writes_the_completed_module(
        self, files: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert self._run(files) == 0
        written = (files / "models.py").read_text()
        assert "Group: TypeAlias = GroupWithControls | GroupWithGroups" in written
        assert str(files / "models.py") in capsys.readouterr().out

    def test_main_writes_nothing_on_a_guard_failure(
        self, files: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        before = RAW + _object("Stray", "x: str") + _object("Lost", "y: str")
        (files / "models.py").write_text(before)
        assert self._run(files) == 1
        assert (files / "models.py").read_text() == before
        err = capsys.readouterr().err
        assert "Stray" in err
        assert "Lost" in err
        assert "was not written" in err

    @pytest.mark.parametrize("absent", ["models.py", "schema.json"])
    def test_a_missing_path_fails_with_its_name(
        self, files: Path, absent: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (files / absent).unlink()
        before = {p.name: p.read_text() for p in files.iterdir()}
        assert self._run(files) == 1
        assert str(files / absent) in capsys.readouterr().err
        assert {p.name: p.read_text() for p in files.iterdir()} == before


# ---------------------------------------------------------------------------
# The committed models.py
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def released_manifest() -> dict[str, Any]:
    manifest_mod = load_script("manifest")
    pin = load_script("spec_artifact")
    manifest: dict[str, Any] = manifest_mod.load_validated_manifest(
        pin.artifact_paths(ensure_spec_artifact())
    )
    return manifest


class TestCommittedModels:
    def test_passes_the_guards(self, released_manifest: dict[str, Any]) -> None:
        content = pp.DEFAULT_MODELS_PATH.read_text()
        assert pp.guard_failures(content, released_manifest) == []

    def test_each_union_alias_is_the_union_of_its_variants(
        self, released_manifest: dict[str, Any]
    ) -> None:
        for entry in released_manifest["types"]:
            if entry["kind"] != "union":
                continue
            alias = getattr(models, entry["name"])
            variants = [getattr(models, v["type"]) for v in entry["variants"]]
            assert list(typing.get_args(alias)) == variants, entry["name"]

    def test_mapping_collection_mappings_is_a_root_model(self) -> None:
        cls = models.MappingCollectionMappings
        assert issubclass(cls, RootModel)
        field = models.MappingCollection.model_fields["mappings"]
        assert field.annotation is cls

    def test_oscal_document_is_the_root_model_of_the_documents(
        self, released_manifest: dict[str, Any]
    ) -> None:
        (entry,) = [
            e for e in released_manifest["types"] if e["kind"] == "document-union"
        ]
        root = models.OscalDocument.model_fields["root"].annotation
        assert {t.__name__ for t in typing.get_args(root)} == set(entry["members"])

    def test_union_alias_validates_each_variant(self) -> None:
        adapter = TypeAdapter(models.CatalogGroup)
        group = adapter.validate_python(
            {
                "id": "g",
                "title": "G",
                "groups": [
                    {"id": "h", "title": "H", "controls": [{"id": "c", "title": "C"}]}
                ],
            }
        )
        assert isinstance(group, models.CatalogGroupWithGroups)
