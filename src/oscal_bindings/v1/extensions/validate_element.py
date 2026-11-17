from __future__ import annotations

import re
import types
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Annotated, Any

from pydantic import BaseModel, Field, TypeAdapter
from pydantic import ValidationError as PydanticValidationError

import oscal_bindings.v1.models as _models

if TYPE_CHECKING:
    from collections.abc import Callable


class OscalUnknownElementTypeError(Exception):
    """Raised when ``validate_element`` gets an unrecognized element type.

    Not a subclass of :class:`OscalParseError`: it is a category of its own.
    """


@dataclass
class ValidationError:
    path: str
    message: str


@dataclass
class ElementValidationResult:
    valid: bool
    errors: list[ValidationError] | None = None


def _pascal_to_kebab(name: str) -> str:
    """Convert PascalCase to kebab-case."""
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1-\2", name)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", s)
    return s.lower()


def _is_manifest_type(obj: object) -> bool:
    """Tell whether a ``models`` attribute has the run-time form of a manifest type.

    The forms are a ``BaseModel`` subclass (object, document, document-union,
    single-or-many), an ``Enum`` subclass, and a ``types.UnionType`` (union).
    The scalar aliases are ``Annotated`` objects and do not match.
    """
    if isinstance(obj, types.UnionType):
        return True
    # ``models.py`` imports ``BaseModel``-derived bases and ``Enum``; only a
    # class that ``models`` defines is an OSCAL element.
    if not (isinstance(obj, type) and obj.__module__ == _models.__name__):
        return False
    if issubclass(obj, Enum):
        return True
    # Skip parametrized generics such as the base
    # ``RootModel[Mapping | list[Mapping]]``. pydantic >= 2.14 registers a
    # module-scope parametrization in the module that writes it, with
    # ``__module__`` equal to ``models.__name__``.
    return (
        issubclass(obj, BaseModel)
        and obj.__pydantic_generic_metadata__["origin"] is None
    )


def _build_element_map() -> dict[str, Any]:
    """Build the map of kebab-case names to the manifest types of ``models``."""
    return {
        _pascal_to_kebab(name): obj
        for name, obj in vars(_models).items()
        if _is_manifest_type(obj)
    }


_ELEMENT_MAP = _build_element_map()

# One ``TypeAdapter`` for each enum or union name, made on first use.
_ADAPTERS: dict[str, TypeAdapter[Any]] = {}


def get_supported_element_types() -> list[str]:
    """Return all supported element type strings."""
    return sorted(_ELEMENT_MAP.keys())


def _validator(element_type: str) -> Callable[[Any], object]:
    """Return the validation callable of a listed element type.

    A ``BaseModel`` validates through ``model_validate``. An enum or a union
    validates through a ``TypeAdapter`` that the first call for the name makes.
    A union uses ``left_to_right`` mode, the mode of the union fields of the
    models.
    """
    target = _ELEMENT_MAP[element_type]
    if isinstance(target, type) and issubclass(target, BaseModel):
        return target.model_validate
    adapter = _ADAPTERS.get(element_type)
    if adapter is None:
        if isinstance(target, types.UnionType):
            target = Annotated[target, Field(union_mode="left_to_right")]
        adapter = _ADAPTERS[element_type] = TypeAdapter(target)
    return adapter.validate_python


def validate_element(element: Any, element_type: str) -> ElementValidationResult:
    """Validate an OSCAL element against the type of its name.

    Args:
        element: The OSCAL element. A dict for an object, a union, or a
            document; the string value for an enum.
        element_type: Kebab-case element type (e.g., 'observation',
            'back-matter', 'hash-algorithm'). See ``get_supported_element_types``.

    Returns:
        ElementValidationResult with valid=True or valid=False with errors.

    Raises:
        OscalUnknownElementTypeError: If element_type is not recognized.
    """
    if element_type not in _ELEMENT_MAP:
        raise OscalUnknownElementTypeError(
            f'Unknown element type: "{element_type}". '
            "Supported types include: "
            f"{', '.join(sorted(list(_ELEMENT_MAP.keys())[:10]))}..."
        )

    try:
        _validator(element_type)(element)
        return ElementValidationResult(valid=True)
    except PydanticValidationError as e:
        errors = [
            ValidationError(
                path=".".join(str(loc) for loc in err["loc"]) or "/",
                message=err["msg"],
            )
            for err in e.errors()
        ]
        return ElementValidationResult(valid=False, errors=errors)
    except Exception as e:
        return ElementValidationResult(
            valid=False,
            errors=[ValidationError(path="/", message=str(e))],
        )
