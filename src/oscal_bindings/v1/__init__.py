"""OSCAL 1.x Python data bindings generated from JSON Schema.

This package provides typed Python data bindings for NIST OSCAL (Open Security
Controls Assessment Language) documents, generated from the official JSON Schema
using datamodel-code-generator with Pydantic v2 models.

The namespace carries the OSCAL **major** version only: OSCAL 1.x is
backward-compatible within its major version, so a minor or patch refresh of the
pinned schema regenerates this package in place rather than creating a new
import path. ``__oscal_schema_version__`` records the exact release the bindings
were generated from.

Key Classes:
    OscalDocument: The root model type representing any valid OSCAL document.
    CatalogDocument: A catalog document wrapper.
    ProfileDocument: A profile document wrapper.
    OscalParseError: Exception raised when parsing or validation fails.
    OscalDateTime: The ``datetime`` subclass of every OSCAL date-time field. It keeps
        every fraction digit of the text; read its docstring for the arithmetic limits.

Key Functions:
    parse_oscal: Parse an OSCAL JSON string into a typed model.
    parse_oscal_file: Parse an OSCAL JSON file into a typed model.
    serialize_oscal: Serialize an OSCAL model back to JSON.
    validate_oscal: Validate a JSON string against the OSCAL schema.
    parse_oscal_yaml: Parse an OSCAL YAML string into a typed model (``yaml`` extra).
    parse_oscal_yaml_file: Parse an OSCAL YAML file into a typed model (``yaml`` extra).
    serialize_oscal_yaml: Serialize an OSCAL model to YAML (``yaml`` extra).
    parse_catalog: Parse JSON as a Catalog document.
    parse_profile: Parse JSON as a Profile document.
    parse_catalog_yaml: Parse YAML as a Catalog document (``yaml`` extra). Each of
        the other seven document types has a ``parse_<type>_yaml`` too.

Example:
    >>> from oscal_bindings.v1 import parse_oscal_file, serialize_oscal
    >>> doc = parse_oscal_file("catalog.json")
    >>> json_str = serialize_oscal(doc)
"""

from ._datetime import OscalDateTime
from .extensions import (
    DocumentId,
    ElementValidationError,
    ElementValidationResult,
    OscalAccessError,
    OscalBody,
    OscalBuilderError,
    OscalDoc,
    OscalUnknownElementTypeError,
    OscalWrapper,
    get_supported_element_types,
    make_hash,
    make_resource,
    make_rlink,
    parse_assessment_plan_yaml,
    parse_assessment_results_yaml,
    parse_catalog_yaml,
    parse_component_definition_yaml,
    parse_mapping_collection_yaml,
    parse_oscal_yaml,
    parse_oscal_yaml_file,
    parse_plan_of_action_and_milestones_yaml,
    parse_profile_yaml,
    parse_system_security_plan_yaml,
    serialize_oscal_yaml,
    validate_element,
)
from .models import *  # noqa: F403
from .parser import (
    AssessmentPlanDocument,
    AssessmentResultsDocument,
    CatalogDocument,
    ComponentDefinitionDocument,
    MappingCollectionDocument,
    OscalDocument,
    OscalDocumentTypeMismatchError,
    OscalParseError,
    OscalReadError,
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

#: The full OSCAL release that the models in this package were generated from:
#: the release of the pinned spec artifact. Matches the release element of the
#: artifact schema ``$id``
#: (``http://csrc.nist.gov/ns/oscal/1.0/1.2.3/oscal-complete-schema.json``,
#: where ``1.0`` is the namespace and ``1.2.3`` the release). Deliberately a
#: literal: the schema does not ship in the wheel, and parsing a multi-megabyte
#: JSON file at import time to recover one string is a cost no consumer should
#: pay. Tests assert it against the pin and the artifact schema ``$id``.
__oscal_schema_version__ = "1.2.3"

__all__ = [
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
    "OscalBuilderError",
    "OscalDateTime",
    "OscalDoc",
    "OscalDocument",
    "OscalDocumentTypeMismatchError",
    "OscalParseError",
    "OscalReadError",
    "OscalUnknownElementTypeError",
    "OscalWrapper",
    "PlanOfActionAndMilestonesDocument",
    "ProfileDocument",
    "SystemSecurityPlanDocument",
    "get_supported_element_types",
    "make_hash",
    "make_resource",
    "make_rlink",
    "parse_assessment_plan",
    "parse_assessment_plan_yaml",
    "parse_assessment_results",
    "parse_assessment_results_yaml",
    "parse_catalog",
    "parse_catalog_yaml",
    "parse_component_definition",
    "parse_component_definition_yaml",
    "parse_mapping_collection",
    "parse_mapping_collection_yaml",
    "parse_oscal",
    "parse_oscal_file",
    "parse_oscal_yaml",
    "parse_oscal_yaml_file",
    "parse_plan_of_action_and_milestones",
    "parse_plan_of_action_and_milestones_yaml",
    "parse_profile",
    "parse_profile_yaml",
    "parse_system_security_plan",
    "parse_system_security_plan_yaml",
    "serialize_oscal",
    "serialize_oscal_yaml",
    "validate_element",
    "validate_oscal",
]
