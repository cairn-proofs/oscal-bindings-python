"""Legacy module path for the OSCAL parser helpers.

The parser now lives in :mod:`oscal_bindings.v1.parser`; this module re-exports
its public surface so that ``from oscal_bindings.parser import parse_oscal``
keeps resolving. Re-export binds the same objects, so type identity holds across
both paths.

An explicit alias module rather than ``sys.modules`` aliasing: it is greppable
and survives static analysis, ``mypy``, and ``pdoc`` without special cases.

Unlike the ``extensions`` and top-level shims, the names are listed explicitly
here because :mod:`oscal_bindings.v1.parser` declares no ``__all__`` of its own —
a star-import would drag in its module-level imports alongside the API.
"""

from oscal_bindings.v1.parser import (
    AssessmentPlanDocument,
    AssessmentResultsDocument,
    CatalogDocument,
    ComponentDefinitionDocument,
    MappingCollectionDocument,
    OscalDocument,
    OscalParseError,
    PlanOfActionAndMilestonesDocument,
    ProfileDocument,
    SystemSecurityPlanDocument,
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
    validate_oscal,
)

__all__ = [
    "AssessmentPlanDocument",
    "AssessmentResultsDocument",
    "CatalogDocument",
    "ComponentDefinitionDocument",
    "MappingCollectionDocument",
    "OscalDocument",
    "OscalParseError",
    "PlanOfActionAndMilestonesDocument",
    "ProfileDocument",
    "SystemSecurityPlanDocument",
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
    "validate_oscal",
]
