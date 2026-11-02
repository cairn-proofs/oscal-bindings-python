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
from oscal_bindings.v1.models import DocumentId

# The YAML operations are not re-exported here. They live in the optional
# `yaml_io` submodule (which imports PyYAML) and are exposed as call-time
# wrappers from `oscal_bindings.v1` (design Decision 5). Keeping them out of this
# package's `__all__` is what lets `from oscal_bindings.v1.extensions import *`,
# and the top-level compatibility module that star-imports it, work on a base
# install without the `yaml` extra.
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
    "validate_element",
]
