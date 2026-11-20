from oscal_bindings.v1.extensions.builders import (
    OscalBuilderError,
    make_hash,
    make_resource,
    make_rlink,
)
from oscal_bindings.v1.extensions.document import (
    OscalAccessError,
    OscalBody,
    OscalDoc,
    OscalWrapper,
)
from oscal_bindings.v1.extensions.validate_element import (
    ElementValidationResult,
    OscalLimitExceededError,
    OscalUnknownElementTypeError,
    get_supported_element_types,
    validate_element,
)
from oscal_bindings.v1.extensions.validate_element import (
    ValidationError as ElementValidationError,
)
from oscal_bindings.v1.extensions.yaml_io import (
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
)
from oscal_bindings.v1.models import DocumentId

# `yaml_io` imports PyYAML only when one of its operations is called, so these
# re-exports work on a base install without the `yaml` extra (design Decision 5).
__all__ = [
    "DocumentId",
    "ElementValidationError",
    "ElementValidationResult",
    "OscalAccessError",
    "OscalBody",
    "OscalBuilderError",
    "OscalDoc",
    "OscalLimitExceededError",
    "OscalUnknownElementTypeError",
    "OscalWrapper",
    "get_supported_element_types",
    "make_hash",
    "make_resource",
    "make_rlink",
    "parse_assessment_plan_yaml",
    "parse_assessment_results_yaml",
    "parse_catalog_yaml",
    "parse_component_definition_yaml",
    "parse_mapping_collection_yaml",
    "parse_oscal_yaml",
    "parse_oscal_yaml_file",
    "parse_plan_of_action_and_milestones_yaml",
    "parse_profile_yaml",
    "parse_system_security_plan_yaml",
    "serialize_oscal_yaml",
    "validate_element",
]
