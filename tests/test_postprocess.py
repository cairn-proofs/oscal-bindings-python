"""Tests for the codegen post-processor CLI (`scripts/postprocess_models.py`).

Covers the argparse surface: independent `--models` / `--schema` defaults and
the missing-path exit behavior.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

REPO_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "postprocess_models.py"


def _load_postprocess() -> ModuleType:
    """Load the post-processor script as a module (it lives outside the package)."""
    spec = importlib.util.spec_from_file_location("postprocess_models", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def pp() -> ModuleType:
    return _load_postprocess()


@pytest.fixture
def fake_models(tmp_path: Path) -> Path:
    """A minimal generated-source file the post-processor can rewrite."""
    path = tmp_path / "models.py"
    path.write_text(
        "from __future__ import annotations\n"
        "\n"
        "from pydantic import BaseModel\n"
        "\n"
        "\n"
        "class OscalCompleteOscalCatalogCatalog(BaseModel):\n"
        "    uuid: str\n"
    )
    return path


@pytest.fixture
def fake_schema(tmp_path: Path) -> Path:
    """A minimal schema with one namespaced definition."""
    path = tmp_path / "schema.json"
    path.write_text(
        json.dumps({"definitions": {"oscal-complete-oscal-catalog:catalog": {}}})
    )
    return path


class TestDefaultsResolveIndependently:
    """Each argument falls back to its own default regardless of the other."""

    def test_both_supplied(self, pp: ModuleType, fake_models: Path, fake_schema: Path):
        args = pp.parse_args(
            ["--models", str(fake_models), "--schema", str(fake_schema)]
        )
        assert args.models == fake_models
        assert args.schema == fake_schema

    def test_schema_only(self, pp: ModuleType, fake_schema: Path):
        args = pp.parse_args(["--schema", str(fake_schema)])
        assert args.schema == fake_schema
        assert args.models == pp.DEFAULT_MODELS_PATH

    def test_models_only(self, pp: ModuleType, fake_models: Path):
        args = pp.parse_args(["--models", str(fake_models)])
        assert args.models == fake_models
        assert args.schema == pp.DEFAULT_SCHEMA_PATH

    def test_neither_supplied(self, pp: ModuleType):
        args = pp.parse_args([])
        assert args.models == pp.DEFAULT_MODELS_PATH
        assert args.schema == pp.DEFAULT_SCHEMA_PATH

    def test_defaults_point_at_existing_files(self, pp: ModuleType):
        assert pp.DEFAULT_MODELS_PATH.exists()
        assert pp.DEFAULT_SCHEMA_PATH.exists()


class TestMainHonorsResolvedPaths:
    """End-to-end: main() reads and writes exactly the resolved paths."""

    def test_both_supplied(
        self, pp: ModuleType, fake_models: Path, fake_schema: Path, capsys
    ):
        pp.main(["--models", str(fake_models), "--schema", str(fake_schema)])
        assert "Catalog" in fake_models.read_text()
        assert "OscalCompleteOscalCatalogCatalog" not in fake_models.read_text()
        assert str(fake_models) in capsys.readouterr().out

    def test_models_only_uses_default_schema(
        self,
        pp: ModuleType,
        fake_models: Path,
        fake_schema: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setattr(pp, "DEFAULT_SCHEMA_PATH", fake_schema)
        pp.main(["--models", str(fake_models)])
        assert "class Catalog(BaseModel):" in fake_models.read_text()

    def test_schema_only_uses_default_models(
        self,
        pp: ModuleType,
        fake_models: Path,
        fake_schema: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setattr(pp, "DEFAULT_MODELS_PATH", fake_models)
        pp.main(["--schema", str(fake_schema)])
        assert "class Catalog(BaseModel):" in fake_models.read_text()

    def test_neither_supplied_uses_both_defaults(
        self,
        pp: ModuleType,
        fake_models: Path,
        fake_schema: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setattr(pp, "DEFAULT_MODELS_PATH", fake_models)
        monkeypatch.setattr(pp, "DEFAULT_SCHEMA_PATH", fake_schema)
        pp.main([])
        assert "class Catalog(BaseModel):" in fake_models.read_text()


class TestMissingPaths:
    def test_missing_models_exits_nonzero_with_path(
        self, pp: ModuleType, fake_schema: Path, tmp_path: Path, capsys
    ):
        absent = tmp_path / "nope.py"
        with pytest.raises(SystemExit) as exc:
            pp.main(["--models", str(absent), "--schema", str(fake_schema)])
        assert exc.value.code != 0
        assert str(absent) in capsys.readouterr().err

    def test_missing_schema_exits_nonzero_with_path(
        self, pp: ModuleType, fake_models: Path, tmp_path: Path, capsys
    ):
        absent = tmp_path / "nope.json"
        with pytest.raises(SystemExit) as exc:
            pp.main(["--models", str(fake_models), "--schema", str(absent)])
        assert exc.value.code != 0
        assert str(absent) in capsys.readouterr().err

    def test_models_left_untouched_when_schema_missing(
        self, pp: ModuleType, fake_models: Path, tmp_path: Path
    ):
        before = fake_models.read_text()
        with pytest.raises(SystemExit):
            pp.main(
                ["--models", str(fake_models), "--schema", str(tmp_path / "nope.json")]
            )
        assert fake_models.read_text() == before


def test_build_namespace_renames_uses_supplied_schema(
    pp: ModuleType, fake_schema: Path
):
    renames = pp.build_namespace_renames(fake_schema)
    assert renames == {"OscalCompleteOscalCatalogCatalog": "Catalog"}


class TestCollisionGuard:
    """The guard accumulates every uncovered collision and refuses to write."""

    @staticmethod
    def _colliding_source(names: list[str]) -> str:
        """Generated source where each supplied name is defined twice."""
        lines = [
            "from __future__ import annotations",
            "",
            "from pydantic import BaseModel",
            "",
        ]
        for name in names:
            for field in ("uuid", "title"):
                lines += ["", f"class {name}(BaseModel):", f"    {field}: str", ""]
        return "\n".join(lines)

    def test_finds_every_duplicate_not_just_the_first(self, pp: ModuleType):
        source = self._colliding_source(["Alpha", "Beta", "Gamma"])
        assert pp.find_duplicate_class_definitions(source) == {
            "Alpha": 2,
            "Beta": 2,
            "Gamma": 2,
        }

    def test_clean_source_has_no_duplicates(self, pp: ModuleType):
        source = (
            "class Alpha(BaseModel):\n    uuid: str\n\n\n"
            "class Beta(BaseModel):\n    uuid: str\n"
        )
        assert pp.find_duplicate_class_definitions(source) == {}

    def test_detects_multi_line_class_headers(self, pp: ModuleType):
        source = (
            "class Alpha(\n    BaseModel\n):\n    uuid: str\n"
            "\n\nclass Alpha(\n    BaseModel\n):\n    title: str\n"
        )
        assert pp.find_duplicate_class_definitions(source) == {"Alpha": 2}

    def test_counts_more_than_two_definitions(self, pp: ModuleType):
        source = "".join(
            f"class Alpha(BaseModel):\n    f{i}: str\n\n\n" for i in range(3)
        )
        assert pp.find_duplicate_class_definitions(source) == {"Alpha": 3}

    def test_main_exits_nonzero_and_reports_all(
        self, pp: ModuleType, fake_models: Path, fake_schema: Path, capsys
    ):
        """Every collision appears in the single report produced by one run."""
        names = ["Alpha", "Beta", "Gamma", "Delta"]
        fake_models.write_text(self._colliding_source(names))

        with pytest.raises(SystemExit) as exc:
            pp.main(["--models", str(fake_models), "--schema", str(fake_schema)])

        assert exc.value.code != 0
        err = capsys.readouterr().err
        for name in names:
            assert f"{name}: 2 definitions" in err
        # One run, one report: a single error header covering all four collisions.
        assert err.count("Error:") == 1
        assert f"{len(names)} class-name collision(s)" in err

    def test_main_leaves_models_unwritten_on_collision(
        self, pp: ModuleType, fake_models: Path, fake_schema: Path
    ):
        before = self._colliding_source(["Alpha", "Beta"])
        fake_models.write_text(before)

        with pytest.raises(SystemExit):
            pp.main(["--models", str(fake_models), "--schema", str(fake_schema)])

        assert fake_models.read_text() == before

    def test_real_schema_output_has_no_collisions(self, pp: ModuleType):
        """The committed models output must not trip the guard (no false positives)."""
        content = pp.DEFAULT_MODELS_PATH.read_text()
        assert pp.find_duplicate_class_definitions(content) == {}


HEADER = "from __future__ import annotations\n\nfrom pydantic import BaseModel\n"

#: The eight OSCAL document root keys as they appear as generated field names
#: (snake_case, because ``datamodel-codegen`` sanitizes the kebab-case JSON keys).
ROOT_KEYS = (
    "catalog",
    "profile",
    "component_definition",
    "system_security_plan",
    "assessment_plan",
    "assessment_results",
    "plan_of_action_and_milestones",
    "mapping_collection",
)


def _wrapper(name: str, *root_keys: str) -> str:
    fields = "".join(f"    {key}: str\n" for key in root_keys)
    return (
        f"\n\nclass {name}(BaseModel):\n    field_schema: str | None = None\n{fields}"
    )


def _schema_with_document_types(path: Path, count: int) -> Path:
    """Write a schema declaring ``count`` document types in its top-level ``oneOf``."""
    path.write_text(
        json.dumps(
            {
                "definitions": {"oscal-complete-oscal-catalog:catalog": {}},
                "oneOf": [{"required": [f"doc-{i}"]} for i in range(count)],
            }
        )
    )
    return path


def _generated_source(ordinal_for_key: dict[str, int]) -> str:
    """Synthesize generated source mapping each root key onto ``Model<ordinal>``.

    Wrapper classes are emitted in ordinal order, mirroring ``datamodel-codegen``,
    so shuffling the assignment shuffles both the names *and* the source positions.
    """
    ordered = sorted(ordinal_for_key.items(), key=lambda kv: kv[1])
    return HEADER + "".join(
        _wrapper(f"Model{ordinal}", key) for key, ordinal in ordered
    )


class TestDerivationTracksContentNotPosition:
    """Req 3.1-3.4: names come from each wrapper's Root_Key, never its ordinal."""

    def test_pascal_case_document_names_derived_from_root_keys(self, pp: ModuleType):
        source = _generated_source({key: i + 1 for i, key in enumerate(ROOT_KEYS)})
        assert pp.derive_document_renames(source) == {
            "Model1": "CatalogDocument",
            "Model2": "ProfileDocument",
            "Model3": "ComponentDefinitionDocument",
            "Model4": "SystemSecurityPlanDocument",
            "Model5": "AssessmentPlanDocument",
            "Model6": "AssessmentResultsDocument",
            "Model7": "PlanOfActionAndMilestonesDocument",
            "Model8": "MappingCollectionDocument",
        }

    def test_shuffled_ordinals_follow_their_content(self, pp: ModuleType):
        """Deliberately shuffled ordinals: each name tracks its own body field.

        ``Model1`` now holds ``plan_of_action_and_milestones``, which the retired
        positional map called ``CatalogDocument``. The derivation must disagree with
        the positional map here — that disagreement is the defect being fixed.
        """
        shuffled = {
            "plan_of_action_and_milestones": 1,
            "assessment_results": 2,
            "mapping_collection": 3,
            "catalog": 4,
            "profile": 5,
            "system_security_plan": 6,
            "component_definition": 7,
            "assessment_plan": 8,
        }
        derived = pp.derive_document_renames(_generated_source(shuffled))

        assert derived == {
            "Model1": "PlanOfActionAndMilestonesDocument",
            "Model2": "AssessmentResultsDocument",
            "Model3": "MappingCollectionDocument",
            "Model4": "CatalogDocument",
            "Model5": "ProfileDocument",
            "Model6": "SystemSecurityPlanDocument",
            "Model7": "ComponentDefinitionDocument",
            "Model8": "AssessmentPlanDocument",
        }
        assert derived != pp.POSITIONAL_DOCUMENT_RENAMES_SNAPSHOT

    def test_published_name_set_is_invariant_under_shuffling(self, pp: ModuleType):
        """Whatever the ordinal assignment, the same eight names come out."""
        forward = {key: i + 1 for i, key in enumerate(ROOT_KEYS)}
        reversed_ = {key: len(ROOT_KEYS) - i for i, key in enumerate(ROOT_KEYS)}

        assert set(
            pp.derive_document_renames(_generated_source(forward)).values()
        ) == set(pp.derive_document_renames(_generated_source(reversed_)).values())

    def test_main_renames_wrappers_by_content(
        self, pp: ModuleType, fake_models: Path, tmp_path: Path
    ):
        """End-to-end: the written file carries the content-derived names."""
        schema = _schema_with_document_types(tmp_path / "schema.json", 2)
        fake_models.write_text(
            HEADER + _wrapper("Model1", "profile") + _wrapper("Model2", "catalog")
        )
        pp.main(["--models", str(fake_models), "--schema", str(schema)])

        written = fake_models.read_text()
        assert "class ProfileDocument(BaseModel):" in written
        assert "class CatalogDocument(BaseModel):" in written
        assert "class Model1(" not in written
        assert "class Model2(" not in written

    def test_schema_only_wrapper_is_not_a_document(self, pp: ModuleType):
        """The union root carries ``field_schema`` alone.

        Nothing to derive, and no error.
        """
        source = HEADER + _wrapper("Model") + _wrapper("Model1", "catalog")
        assert pp.derive_document_renames(source) == {"Model1": "CatalogDocument"}

    def test_classes_without_the_directive_field_are_ignored(self, pp: ModuleType):
        """Ordinary model classes have many fields but no ``field_schema``."""
        source = (
            HEADER
            + "\n\nclass Catalog(BaseModel):\n    uuid: str\n    metadata: str\n"
            + _wrapper("Model1", "catalog")
        )
        assert pp.derive_document_renames(source) == {"Model1": "CatalogDocument"}


class TestAmbiguityGuardFailsFast:
    """Req 3.5: report the first ambiguous wrapper and stop scanning."""

    def test_derivation_raises_on_first_offender(self, pp: ModuleType):
        source = (
            HEADER
            + _wrapper("Model1", "catalog", "profile")
            + _wrapper("Model2", "assessment_plan", "assessment_results")
        )
        with pytest.raises(pp.AmbiguousWrapperError) as exc:
            pp.derive_document_renames(source)
        assert exc.value.class_name == "Model1"
        assert exc.value.body_fields == ["catalog", "profile"]
        assert "Model2" not in str(exc.value)

    def test_main_exits_nonzero_naming_only_the_first(
        self, pp: ModuleType, fake_models: Path, fake_schema: Path, capsys
    ):
        fake_models.write_text(
            HEADER
            + _wrapper("Alpha", "catalog", "profile")
            + _wrapper("Bravo", "assessment_plan", "assessment_results")
        )
        with pytest.raises(SystemExit) as exc:
            pp.main(["--models", str(fake_models), "--schema", str(fake_schema)])

        assert exc.value.code != 0
        err = capsys.readouterr().err
        assert "Alpha" in err
        assert "Bravo" not in err

    def test_wrappers_after_the_offender_are_left_unscanned(
        self, pp: ModuleType, fake_models: Path, fake_schema: Path, capsys
    ):
        """A *valid* wrapper following the offender is absent from the report too.

        If the scan had continued, this wrapper would have been derived and could
        surface downstream; its absence is the evidence the scan stopped.
        """
        fake_models.write_text(
            HEADER
            + _wrapper("Alpha", "catalog", "profile")
            + _wrapper("Charlie", "system_security_plan")
        )
        with pytest.raises(SystemExit):
            pp.main(["--models", str(fake_models), "--schema", str(fake_schema)])

        err = capsys.readouterr().err
        assert "Charlie" not in err
        assert "SystemSecurityPlanDocument" not in err

    def test_models_left_unwritten_on_ambiguity(
        self, pp: ModuleType, fake_models: Path, fake_schema: Path
    ):
        before = HEADER + _wrapper("Alpha", "catalog", "profile")
        fake_models.write_text(before)
        with pytest.raises(SystemExit):
            pp.main(["--models", str(fake_models), "--schema", str(fake_schema)])
        assert fake_models.read_text() == before

    def test_real_bundle_output_is_unambiguous(self, pp: ModuleType):
        """No false positives against the committed models output."""
        pp.derive_document_renames(pp.DEFAULT_MODELS_PATH.read_text())


class TestWrapperCountGuard:
    """Req 3.6: derived wrapper count must match the schema's document-type count."""

    def test_mismatch_reports_both_counts(
        self, pp: ModuleType, fake_models: Path, tmp_path: Path, capsys
    ):
        schema = _schema_with_document_types(tmp_path / "schema.json", 3)
        fake_models.write_text(HEADER + _wrapper("Alpha", "catalog"))

        with pytest.raises(SystemExit) as exc:
            pp.main(["--models", str(fake_models), "--schema", str(schema)])

        assert exc.value.code != 0
        err = capsys.readouterr().err
        assert "1 wrapper" in err
        assert "3 document type" in err

    def test_surplus_wrappers_also_report_both_counts(
        self, pp: ModuleType, fake_models: Path, tmp_path: Path, capsys
    ):
        """The guard is symmetric.

        More derived wrappers than declared types fails too.
        """
        schema = _schema_with_document_types(tmp_path / "schema.json", 1)
        fake_models.write_text(
            HEADER + _wrapper("Alpha", "catalog") + _wrapper("Bravo", "profile")
        )

        with pytest.raises(SystemExit) as exc:
            pp.main(["--models", str(fake_models), "--schema", str(schema)])

        assert exc.value.code != 0
        err = capsys.readouterr().err
        assert "2 wrapper" in err
        assert "1 document type" in err

    def test_models_left_unwritten_on_mismatch(
        self, pp: ModuleType, fake_models: Path, tmp_path: Path
    ):
        schema = _schema_with_document_types(tmp_path / "schema.json", 3)
        before = HEADER + _wrapper("Alpha", "catalog")
        fake_models.write_text(before)

        with pytest.raises(SystemExit):
            pp.main(["--models", str(fake_models), "--schema", str(schema)])

        assert fake_models.read_text() == before

    def test_match_passes(self, pp: ModuleType, fake_models: Path, tmp_path: Path):
        schema = _schema_with_document_types(tmp_path / "schema.json", 1)
        fake_models.write_text(HEADER + _wrapper("Alpha", "catalog"))
        pp.main(["--models", str(fake_models), "--schema", str(schema)])
        assert "class CatalogDocument(BaseModel):" in fake_models.read_text()

    def test_schema_without_one_of_is_not_judged(
        self, pp: ModuleType, fake_schema: Path
    ):
        """No top-level ``oneOf`` means no declared document types to compare."""
        assert pp.count_schema_document_types(fake_schema) is None

    def test_real_bundle_counts_eight(self, pp: ModuleType):
        assert pp.count_schema_document_types(pp.DEFAULT_SCHEMA_PATH) == 8


class TestParityWithPositionalMap:
    """Req 3.7: against the active bundle, derivation reproduces the published eight.

    The committed ``models.py`` is *already* post-processed, so its wrappers are named
    ``CatalogDocument`` rather than ``Model1``. Deriving from it therefore cannot
    reproduce the positional map's ``Model1`` keys, and asserting on them would be
    theater. The real claim of Req 3.7 is about the published names, so these tests
    assert on the map's *values* — plus a reconstruction that puts the ordinal names
    back, shuffled, to show the derivation reaches the same eight names from the real
    schema's content regardless of ordinal assignment.
    """

    @staticmethod
    def _derived_from_real_output(pp: ModuleType) -> dict[str, str]:
        return pp.derive_document_renames(pp.DEFAULT_MODELS_PATH.read_text())

    def test_derived_names_equal_the_positional_maps_names(self, pp: ModuleType):
        derived = self._derived_from_real_output(pp)
        assert set(derived.values()) == set(
            pp.POSITIONAL_DOCUMENT_RENAMES_SNAPSHOT.values()
        )
        assert len(derived) == len(pp.POSITIONAL_DOCUMENT_RENAMES_SNAPSHOT)

    def test_derivation_is_a_fixed_point_on_post_processed_output(self, pp: ModuleType):
        """Re-deriving from already-renamed output maps each name onto itself.

        This is what makes the value-set assertion above load-bearing: the wrappers in
        the committed file carry exactly their published names, so re-running codegen
        over an unchanged schema cannot drift.
        """
        derived = self._derived_from_real_output(pp)
        assert all(old == new for old, new in derived.items())

    def test_ordinal_names_restored_in_shuffled_order_still_derive_the_eight(
        self, pp: ModuleType
    ):
        """Rename the real wrappers back to ``Model1..Model8``, shuffled, then derive.

        Only the class *headers* are rewritten, which is all the derivation reads. The
        bodies stay as generated, so the Root_Keys are the real bundle's.
        """
        content = pp.DEFAULT_MODELS_PATH.read_text()
        published = sorted(pp.POSITIONAL_DOCUMENT_RENAMES_SNAPSHOT.values())
        # A rotation by three: no wrapper keeps the ordinal the positional map gave it.
        shuffled = published[3:] + published[:3]

        for ordinal, name in enumerate(shuffled, start=1):
            header = f"class {name}(BaseModel):"
            assert header in content, f"expected wrapper header for {name}"
            content = content.replace(header, f"class Model{ordinal}(BaseModel):")

        derived = pp.derive_document_renames(content)

        assert set(derived) == {f"Model{i}" for i in range(1, 9)}
        assert set(derived.values()) == set(
            pp.POSITIONAL_DOCUMENT_RENAMES_SNAPSHOT.values()
        )

    def test_wrapper_count_matches_the_bundles_document_types(self, pp: ModuleType):
        derived = self._derived_from_real_output(pp)
        assert len(derived) == pp.count_schema_document_types(pp.DEFAULT_SCHEMA_PATH)
