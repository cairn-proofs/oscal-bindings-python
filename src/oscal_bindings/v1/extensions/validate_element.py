from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

import oscal_bindings.v1.models as _models
from oscal_bindings.v1.parser import OscalParseError


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


def _build_element_map() -> dict[str, type[BaseModel]]:
    """Build map of kebab-case names to Pydantic model classes."""
    element_map: dict[str, type[BaseModel]] = {}
    for name in dir(_models):
        obj = getattr(_models, name)
        if (
            isinstance(obj, type)
            and issubclass(obj, BaseModel)
            and obj is not BaseModel
        ):
            kebab = _pascal_to_kebab(name)
            element_map[kebab] = obj
    return element_map


_ELEMENT_MAP = _build_element_map()


def get_supported_element_types() -> list[str]:
    """Return all supported element type strings."""
    return sorted(_ELEMENT_MAP.keys())


def validate_element(
    element: dict[str, Any] | None, element_type: str
) -> ElementValidationResult:
    """Validate an OSCAL element against its Pydantic model.

    Args:
        element: Dict representing the OSCAL element.
        element_type: Kebab-case element type (e.g., 'observation', 'back-matter').

    Returns:
        ElementValidationResult with valid=True or valid=False with errors.

    Raises:
        OscalParseError: If element_type is not recognized.
    """
    if element_type not in _ELEMENT_MAP:
        raise OscalParseError(
            f'Unknown element type: "{element_type}". '
            "Supported types include: "
            f"{', '.join(sorted(list(_ELEMENT_MAP.keys())[:10]))}..."
        )

    model_class = _ELEMENT_MAP[element_type]

    try:
        model_class.model_validate(element)
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
