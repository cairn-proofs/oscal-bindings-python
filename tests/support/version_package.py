"""Shared fixtures-as-data for the ``major-version-namespace`` move.

The pre-move public-surface snapshot and the Active_Schema_Bundle lookup are
asserted from two places — the example-based back-compat suite
(``tests/test_oscal_bindings.py``) and the property suite
(``tests/test_prop_version_package.py``). They live here so there is exactly one
snapshot of record: two copies would eventually disagree, and a disagreement
between them would be indistinguishable from the drift they exist to catch.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
POSTPROCESS_SCRIPT = REPO_ROOT / "scripts" / "postprocess_models.py"

#: The top-level ``__all__`` as it stood immediately before the ``v1`` move,
#: transcribed from the pre-move ``src/oscal_bindings/__init__.py``. Deliberately
#: a literal rather than something derived at runtime: derived expectations drift
#: with the code they are meant to pin, and the whole point is to detect drift.
PRE_MOVE_ALL = frozenset(
    {
        "AssessmentPlanDocument",
        "AssessmentResultsDocument",
        "CatalogDocument",
        "ComponentDefinitionDocument",
        "DocumentId",
        "ElementValidationError",
        "ElementValidationResult",
        "MappingCollectionDocument",
        "OscalAccessError",
        "OscalBody",
        "OscalDoc",
        "OscalDocument",
        "OscalParseError",
        "OscalWrapper",
        "PlanOfActionAndMilestonesDocument",
        "ProfileDocument",
        "SystemSecurityPlanDocument",
        "get_supported_element_types",
        "make_hash",
        "make_resource",
        "make_rlink",
        "parse_assessment_plan",
        "parse_assessment_results",
        "parse_catalog",
        "parse_component_definition",
        "parse_mapping_collection",
        "parse_oscal",
        "parse_oscal_file",
        "parse_plan_of_action_and_milestones",
        "parse_profile",
        "parse_system_security_plan",
        "serialize_oscal",
        "validate_element",
        "validate_oscal",
    }
)

#: major.minor.patch, and nothing else (Req 6.2).
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


def active_schema_path() -> Path:
    """The Active_Schema_Bundle schema path, per the post-processor's default.

    Read from the post-processor rather than restated here so the tests follow
    whichever bundle codegen actually runs against (Req 1.4: selection is by
    supplied path, never by scanning ``schemas/``).
    """
    spec = importlib.util.spec_from_file_location(
        "postprocess_models_for_version_tests", POSTPROCESS_SCRIPT
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    path: Path = module.DEFAULT_SCHEMA_PATH
    return path


def schema_release(schema_path: Path) -> str:
    """The release element of a bundle's schema ``$id``.

    The ``$id`` is ``.../ns/oscal/<namespace>/<release>/oscal-complete-schema.json``,
    so the release is the path element before the filename — the namespace
    (``1.0``) is major-scoped and deliberately *not* what we read here.
    """
    schema_id: str = json.loads(schema_path.read_text())["$id"]
    return schema_id.rstrip("/").split("/")[-2]
