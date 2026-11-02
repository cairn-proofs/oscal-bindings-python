from typing import TYPE_CHECKING, Any

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

if TYPE_CHECKING:
    from oscal_bindings.v1.extensions.yaml_io import (
        parse_oscal_yaml,
        parse_oscal_yaml_file,
        serialize_oscal_yaml,
    )

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

# The YAML operations live in the optional `yaml_io` module, which imports
# PyYAML. They are re-exported lazily so that importing this package without the
# `yaml` extra still works: the ImportError with its install hint is raised only
# when a caller first touches one of these names (design Decision 5).
_YAML_NAMES = frozenset(
    {"parse_oscal_yaml", "parse_oscal_yaml_file", "serialize_oscal_yaml"}
)


def __getattr__(name: str) -> Any:
    if name in _YAML_NAMES:
        from oscal_bindings.v1.extensions import yaml_io  # noqa: PLC0415 - lazy

        return getattr(yaml_io, name)
    message = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(message)
