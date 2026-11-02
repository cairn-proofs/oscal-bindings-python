from oscal_bindings.v1.extensions.builders import (
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
    get_supported_element_types,
    validate_element,
)
from oscal_bindings.v1.extensions.validate_element import (
    ValidationError as ElementValidationError,
)
from oscal_bindings.v1.extensions.yaml_io import (
    parse_oscal_yaml,
    parse_oscal_yaml_file,
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
    "OscalDoc",
    "OscalWrapper",
    "get_supported_element_types",
    "make_hash",
    "make_resource",
    "make_rlink",
    "parse_oscal_yaml",
    "parse_oscal_yaml_file",
    "serialize_oscal_yaml",
    "validate_element",
]
