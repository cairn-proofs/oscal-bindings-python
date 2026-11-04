"""OSCAL JSON parsing, serialization, and validation utilities.

This module provides convenience functions for parsing OSCAL JSON documents
into Pydantic models and serializing them back to JSON.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, cast

from pydantic import ValidationError

from oscal_bindings.v1.models import (
    AssessmentPlanDocument,
    AssessmentResultsDocument,
    CatalogDocument,
    ComponentDefinitionDocument,
    MappingCollectionDocument,
    OscalDocument,
    PlanOfActionAndMilestonesDocument,
    ProfileDocument,
    SystemSecurityPlanDocument,
)


class OscalParseError(Exception):
    """Raised when an OSCAL document cannot be parsed or validated.

    ``errors`` holds the structured entries, in the Pydantic entry shape. A
    schema-conformance failure gives one entry for each failing location. An
    input over a documented resource limit gives one entry whose ``type`` names
    the limit, such as ``json_depth_limit`` or ``json_digit_limit``, and whose
    ``input`` is ``None``. For a JSON limit, ``line`` and ``column`` give the
    position in the JSON text, and ``column`` counts UTF-8 bytes, not
    characters.
    """

    def __init__(self, message: str, errors: list[Any] | None = None) -> None:
        super().__init__(message)
        self.errors = errors or []


#: The JSON depth limit (PRS-010). A value that more than this many arrays and
#: objects hold is a parse error. pydantic-core's JSON parser sets the value,
#: and tests pin it at the boundary.
JSON_DEPTH_LIMIT = 200

#: The JSON digit limit (PRS-010). A number whose integer part has more than
#: this many digits is a parse error. A sign, a fraction, and an exponent do not
#: count. pydantic-core's JSON parser sets the value, and tests pin it.
JSON_DIGIT_LIMIT = 4300

JSON_DEPTH_LIMIT_MSG = f"JSON nesting exceeds the depth limit of {JSON_DEPTH_LIMIT}"
JSON_DIGIT_LIMIT_MSG = (
    f"A JSON number exceeds the limit of {JSON_DIGIT_LIMIT:,} digits "
    "in its integer part"
)

# The ctx.error prefixes of pydantic-core's json_invalid entry for each limit.
_LIMIT_PREFIXES = (
    ("recursion limit exceeded", "json_depth_limit", JSON_DEPTH_LIMIT_MSG),
    ("number out of range", "json_digit_limit", JSON_DIGIT_LIMIT_MSG),
)
_POSITION = re.compile(r" at line (\d+) column (\d+)$")


def _limit_entry(e: ValidationError) -> dict[str, Any] | None:
    """Return the limit entry for a JSON limit rejection, or None (design D2).

    The entry has the keys of a YAML limit entry. It holds no input text.
    """
    if e.error_count() != 1:
        return None
    (error,) = e.errors(include_url=False, include_input=False)
    if error["type"] != "json_invalid":
        return None
    detail = str(error.get("ctx", {}).get("error", ""))
    for prefix, kind, message in _LIMIT_PREFIXES:
        if detail.startswith(prefix):
            match = _POSITION.search(detail)
            line, column = (int(match[1]), int(match[2])) if match else (None, None)
            return {
                "type": kind,
                "loc": (),
                "msg": message,
                "input": None,
                "line": line,
                "column": column,
            }
    return None


def parse_oscal(data: str | bytes) -> OscalDocument:
    """Parse an OSCAL JSON document into a typed Pydantic model.

    Args:
        data: A valid OSCAL JSON document, as either a `str` or `bytes`.
            Passing `bytes` skips an intermediate UTF-8 decode and is
            preferable when the document comes from a byte-source
            (HTTP response body, S3 GET, file read, etc.).

    Returns:
        An OscalDocument instance representing the parsed document.

    Raises:
        OscalParseError: If the input is not valid JSON, contains
            invalid UTF-8 bytes, does not conform to the OSCAL schema, or
            exceeds the JSON depth limit or the JSON digit limit.
    """
    limit: dict[str, Any] | None = None
    try:
        return OscalDocument.model_validate_json(data)
    except ValidationError as e:
        limit = _limit_entry(e)
        if limit is None:
            count = e.error_count()
            raise OscalParseError(
                f"Failed to parse OSCAL document: {count} validation error(s)",
                errors=list(e.errors()),
            ) from e
    except ValueError as e:
        raise OscalParseError(f"Invalid JSON: {e}") from e
    # Raised outside the handler, so that neither __cause__ nor __context__
    # holds the ValidationError and its copy of the input.
    raise OscalParseError(limit["msg"], errors=[limit])


def parse_oscal_file(path: Path | str) -> OscalDocument:
    """Parse an OSCAL JSON file into a typed Pydantic model.

    Args:
        path: Path to an OSCAL JSON file.

    Returns:
        An OscalDocument instance representing the parsed document.

    Raises:
        OscalParseError: If the file cannot be read or its contents do not
            conform to the OSCAL schema.
        FileNotFoundError: If the file does not exist.
    """
    return parse_oscal(_read_oscal_file(path))


def _read_oscal_file(path: Path | str) -> bytes:
    """Read an OSCAL file for a file parser (PRS-002).

    Shared by :func:`parse_oscal_file` and the YAML file parser, so both report
    a missing file and a read failure the same way.

    Raises:
        FileNotFoundError: The file does not exist.
        OscalParseError: The file exists but cannot be read.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"OSCAL file not found: {file_path}")

    try:
        return file_path.read_bytes()
    except OSError as e:
        raise OscalParseError(f"Failed to read file: {e}") from e


def serialize_oscal(model: OscalDocument, *, indent: int | None = 2) -> str:
    """Serialize an OSCAL model to a JSON string.

    Emits OSCAL property names (aliases such as `media-type`) and omits
    unset optional fields. The models already default to this, so plain
    `model.model_dump_json()` gives equivalent output. The explicit
    `by_alias=True, exclude_none=True` are kept on purpose: they document
    the contract here and keep this output stable if the model defaults
    ever change.

    Args:
        model: An OscalDocument instance to serialize.
        indent: Number of spaces for JSON indentation. Use None for compact
            output. Defaults to 2.

    Returns:
        A JSON string representation of the OSCAL document.
    """
    return model.model_dump_json(indent=indent, by_alias=True, exclude_none=True)


def validate_oscal(data: str | bytes) -> bool:
    """Validate an OSCAL JSON document without returning the parsed model.

    Args:
        data: A JSON document (`str` or `bytes`) to validate against
            the OSCAL schema.

    Returns:
        True if the document is valid, False otherwise.
    """
    try:
        OscalDocument.model_validate_json(data)
    except (ValidationError, ValueError):
        return False
    else:
        return True


# --- Typed convenience parsers ---
#
# parse_oscal returns an OscalDocument whose `root` is a union of all eight
# document wrappers. The hasattr guard confirms the concrete type at runtime;
# cast tells the type checker which member of the union we've narrowed to.


def parse_catalog(data: str | bytes) -> CatalogDocument:
    """Parse an OSCAL Catalog document (accepts `str` or `bytes`)."""
    doc = parse_oscal(data)
    if not hasattr(doc.root, "catalog"):
        raise OscalParseError("Document is not a Catalog")
    return cast("CatalogDocument", doc.root)


def parse_profile(data: str | bytes) -> ProfileDocument:
    """Parse an OSCAL Profile document (accepts `str` or `bytes`)."""
    doc = parse_oscal(data)
    if not hasattr(doc.root, "profile"):
        raise OscalParseError("Document is not a Profile")
    return cast("ProfileDocument", doc.root)


def parse_component_definition(data: str | bytes) -> ComponentDefinitionDocument:
    """Parse an OSCAL Component Definition document (accepts `str` or `bytes`)."""
    doc = parse_oscal(data)
    if not hasattr(doc.root, "component_definition"):
        raise OscalParseError("Document is not a Component Definition")
    return cast("ComponentDefinitionDocument", doc.root)


def parse_system_security_plan(data: str | bytes) -> SystemSecurityPlanDocument:
    """Parse an OSCAL System Security Plan document (accepts `str` or `bytes`)."""
    doc = parse_oscal(data)
    if not hasattr(doc.root, "system_security_plan"):
        raise OscalParseError("Document is not a System Security Plan")
    return cast("SystemSecurityPlanDocument", doc.root)


def parse_assessment_plan(data: str | bytes) -> AssessmentPlanDocument:
    """Parse an OSCAL Assessment Plan document (accepts `str` or `bytes`)."""
    doc = parse_oscal(data)
    if not hasattr(doc.root, "assessment_plan"):
        raise OscalParseError("Document is not an Assessment Plan")
    return cast("AssessmentPlanDocument", doc.root)


def parse_assessment_results(data: str | bytes) -> AssessmentResultsDocument:
    """Parse an OSCAL Assessment Results document (accepts `str` or `bytes`)."""
    doc = parse_oscal(data)
    if not hasattr(doc.root, "assessment_results"):
        raise OscalParseError("Document is not Assessment Results")
    return cast("AssessmentResultsDocument", doc.root)


def parse_plan_of_action_and_milestones(
    data: str | bytes,
) -> PlanOfActionAndMilestonesDocument:
    """Parse an OSCAL Plan of Action and Milestones document.

    Accepts `str` or `bytes`.
    """
    doc = parse_oscal(data)
    if not hasattr(doc.root, "plan_of_action_and_milestones"):
        raise OscalParseError("Document is not a Plan of Action and Milestones")
    return cast("PlanOfActionAndMilestonesDocument", doc.root)


def parse_mapping_collection(data: str | bytes) -> MappingCollectionDocument:
    """Parse an OSCAL Mapping Collection document (accepts `str` or `bytes`)."""
    doc = parse_oscal(data)
    if not hasattr(doc.root, "mapping_collection"):
        raise OscalParseError("Document is not a Mapping Collection")
    return cast("MappingCollectionDocument", doc.root)
