"""Shared fixtures-as-data for the ``major-version-namespace`` move.

The pre-move public-surface snapshot and the artifact schema lookup are
asserted from two places — the example-based back-compat suite
(``tests/test_oscal_bindings.py``) and the property suite
(``tests/test_prop_version_package.py``). They live here so there is exactly one
snapshot of record: two copies would eventually disagree, and a disagreement
between them would be indistinguishable from the drift they exist to catch.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from support.spec_artifact import schema_path

if TYPE_CHECKING:
    from pathlib import Path

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
    """The complete schema of the pinned spec artifact, which codegen reads.

    Resolved through ``support.spec_artifact``, so the fetch goes through
    ``support.corpus`` and shares one cache with the corpus tests.
    """
    return schema_path()


def schema_release(path: Path) -> str:
    """The release element of a schema ``$id``.

    The ``$id`` is ``.../ns/oscal/<namespace>/<release>/oscal-complete-schema.json``,
    so the release is the path element before the filename — the namespace
    (``1.0``) is major-scoped and deliberately *not* what we read here.
    """
    schema_id: str = json.loads(path.read_text())["$id"]
    return schema_id.rstrip("/").split("/")[-2]
