"""Optional YAML parse and serialize for OSCAL documents.

This module implements the store's ``yaml-documents`` capability (YML-001 to
YML-010), with one documented exception: a double-quoted escape that names a
surrogate, such as a surrogate pair ``"\\ud83d\\ude00"``, is a parse error. YAML 1.2
defines an escape as a Unicode scalar value, which a surrogate is not. The JSON
path accepts the same pair, so this narrows YML-005. Write ``"\\U0001F600"``
instead.

YAML is an optional feature. It needs the ``yaml`` extra
(``pip install oscal-bindings[yaml]``). This module does not import PyYAML when
it is imported, so every import path of the package works without the extra.
A call to one of the eleven operations imports PyYAML and raises
`ImportError` with an install hint when the extra is missing.

The eleven operations are `parse_oscal_yaml`,
`parse_oscal_yaml_file`, `serialize_oscal_yaml`, and the eight typed
parsers ``parse_<type>_yaml`` (YML-007): ``parse_catalog_yaml``,
``parse_profile_yaml``, ``parse_component_definition_yaml``,
``parse_system_security_plan_yaml``, ``parse_assessment_plan_yaml``,
``parse_assessment_results_yaml``, ``parse_plan_of_action_and_milestones_yaml``,
and ``parse_mapping_collection_yaml``. A typed parser parses as
`parse_oscal_yaml` does, then returns the wrapper of its document type, or
raises `OscalDocumentTypeMismatchError`.

A parse reads one YAML 1.2 document in UTF-8, converts it to JSON text, and
passes that text to `parse_oscal`. So the YAML
parse result equals the JSON parse result for the JSON text of the input
(YML-005), and the YAML path has the JSON path's validation and error detail.
The OSCAL schema decides the type of each scalar at its location (YML-004). A
``%YAML 1.1`` or ``%YAML 1.2`` directive is accepted, and both read as YAML
1.2, as YAML 1.2.2 section 6.8.1 requires. Any other version is a parse error.

Resource limits (PRS-010). `parse_oscal_yaml`,
`parse_oscal_yaml_file`, and the eight typed parsers apply four documented
YAML limits, and an input
past any of them is an `OscalParseError`:

1. Alias nodes: aliases can add at most 100,000 nodes. Each use of an alias adds
   every scalar, sequence, mapping, and mapping key of the value it expands to.
2. Alias characters: aliases can add at most 1,000,000 characters of scalar
   text and key text.
3. Depth: no node can sit deeper than 128 levels of sequences and mappings,
   counted after alias expansion.
4. Line-break placeholders: an input that holds U+0085, U+2028, or U+2029 must
   leave a free private-use character for each of them. Only an input of at
   least 520 KB, built to hold or name about 137,000 private-use characters,
   leaves none.

These parse operations also apply the JSON digit limit of
`oscal_bindings.v1.parser` at each number location: a number whose
integer part has more than 4,300 digits is a parse error at its YAML location.
The YAML depth limit is lower than the JSON depth limit, so the JSON depth
limit never rejects a YAML input. docs/limits.md lists every limit.

Content that the input writes out, and that no alias repeats, does not count
against the two alias limits. No step of the parse recurses per nesting level,
so the depth limit, not the interpreter's stack, rejects deep input. The limits
do not bound the size of input without aliases. Its memory cost grows linearly
with the input size, at a higher factor than the JSON path (see PERFORMANCE.md).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from oscal_bindings.v1.models import (
    AssessmentPlanDocument,
    AssessmentResultsDocument,
    CatalogDocument,
    ComponentDefinitionDocument,
    MappingCollectionDocument,
    PlanOfActionAndMilestonesDocument,
    ProfileDocument,
    SystemSecurityPlanDocument,
)
from oscal_bindings.v1.parser import _narrow_document

if TYPE_CHECKING:
    from oscal_bindings.v1.models import OscalDocument

__all__ = [
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
]

# The three limits are not exported: docs/limits.md and DEVELOPING state each value,
# and tests/test_lint_config.py ties the prose to these constants.

#: The maximum number of nodes that aliases can add to one YAML input. Each use
#: of an alias adds every scalar, sequence, mapping, and mapping key of the value
#: it expands to, and an alias inside a repeated value adds its value each time.
ALIAS_NODE_LIMIT = 100_000

#: The maximum number of characters of scalar text and key text that aliases can
#: add to one YAML input, counted as ``ALIAS_NODE_LIMIT`` counts nodes.
ALIAS_CHAR_LIMIT = 1_000_000

#: The maximum depth of a node: the number of sequences and mappings that hold
#: it, counted in the value after alias expansion. A node at this depth is
#: accepted. A node deeper than this is a parse error.
DEPTH_LIMIT = 128

_INSTALL_HINT = (
    "YAML support requires the 'yaml' extra. "
    "Install it with: pip install oscal-bindings[yaml]"
)


def _require_yaml() -> None:
    """Import PyYAML, or raise `ImportError` with the install hint."""
    try:
        import yaml  # noqa: F401, PLC0415 - imported at call time by design
    except ImportError as exc:
        raise ImportError(_INSTALL_HINT) from exc


def parse_oscal_yaml(data: str | bytes) -> OscalDocument:
    """Parse an OSCAL YAML document into a typed Pydantic model (YML-005).

    Converts the YAML input to JSON text and calls
    `parse_oscal`. The result equals the JSON
    parse result for the JSON text of the input. Requires the ``yaml`` extra.

    Args:
        data: One YAML 1.2 document, as ``str`` or ``bytes``. The binding
            decodes ``bytes`` as UTF-8 (YML-002.04).

    Returns:
        An `OscalDocument` for the document.

    Raises:
        OscalParseError: The input is not one well-formed YAML 1.2 document in
            UTF-8, holds a duplicate or non-scalar key, holds a scalar whose
            text does not match the type at its location, passes a resource
            limit of this module, or does not conform to the OSCAL schema. A
            failure that the YAML layer finds has an ``errors`` entry with the
            keys ``type``, ``loc`` (the JSON path), ``msg``, ``input``,
            ``line``, and ``column``. A scalar that matches no grammar of
            YML-004 does not stop the parse: the error holds one such entry
            for each of them, followed by the schema entries for the rest of
            the document (PRS-006). The ``loc`` of a YAML entry is the plain JSON
            path, such as ``("catalog", "metadata", "title")``, and the ``loc``
            of a schema entry starts with the class name of the document
            type, such as ``("CatalogDocument", "catalog", ...)``, as in
            `parse_oscal`. Any other YAML
            failure is the one entry.
        ImportError: The ``yaml`` extra is not installed.
    """
    _require_yaml()
    from oscal_bindings.v1.extensions import _yaml_loader  # noqa: PLC0415

    return _yaml_loader.parse_oscal_yaml(data)


def parse_oscal_yaml_file(path: Path | str) -> OscalDocument:
    """Parse an OSCAL YAML file into a typed Pydantic model (YML-006).

    Reads the file at ``path`` and parses its content as
    `parse_oscal_yaml` does. A missing file reports the not-found
    condition, as `parse_oscal_file` does. That
    condition is distinct from the parse error (PRS-002). Requires the ``yaml``
    extra.

    Args:
        path: Path to an OSCAL YAML file.

    Returns:
        An `OscalDocument` for the document.

    Raises:
        FileNotFoundError: No file can exist at the path.
        OscalReadError: The file cannot be read for another reason.
        OscalParseError: The content of the file is not valid OSCAL YAML, as
            `parse_oscal_yaml` defines.
        ImportError: The ``yaml`` extra is not installed.
    """
    _require_yaml()
    from oscal_bindings.v1.extensions import _yaml_loader  # noqa: PLC0415

    return _yaml_loader.parse_oscal_yaml_file(Path(path))


# --- Typed YAML parsers (YML-007) ---
#
# All eight or none: each parses its input as `parse_oscal_yaml` does (YML-005),
# then behaves as the typed JSON parser of PRS-003 for its document type. It
# returns the wrapper, or raises OscalDocumentTypeMismatchError (a subclass of
# OscalParseError) naming the expected type. Each needs the ``yaml`` extra.


def parse_catalog_yaml(data: str | bytes) -> CatalogDocument:
    """Parse an OSCAL Catalog document in YAML (YML-007).

    Parses as `parse_oscal_yaml` does, then returns the wrapper,
    a `CatalogDocument`.
    Requires the ``yaml`` extra.

    Raises:
        OscalDocumentTypeMismatchError: The document is not a Catalog.
        OscalParseError: As `parse_oscal_yaml` defines.
        ImportError: The ``yaml`` extra is not installed.
    """
    return _narrow_document(parse_oscal_yaml(data), CatalogDocument, "a Catalog")


def parse_profile_yaml(data: str | bytes) -> ProfileDocument:
    """Parse an OSCAL Profile document in YAML (YML-007).

    Parses as `parse_oscal_yaml` does, then returns the wrapper,
    a `ProfileDocument`.
    Requires the ``yaml`` extra.

    Raises:
        OscalDocumentTypeMismatchError: The document is not a Profile.
        OscalParseError: As `parse_oscal_yaml` defines.
        ImportError: The ``yaml`` extra is not installed.
    """
    return _narrow_document(parse_oscal_yaml(data), ProfileDocument, "a Profile")


def parse_component_definition_yaml(data: str | bytes) -> ComponentDefinitionDocument:
    """Parse an OSCAL Component Definition document in YAML (YML-007).

    Parses as `parse_oscal_yaml` does, then returns the wrapper,
    a `ComponentDefinitionDocument`.
    Requires the ``yaml`` extra.

    Raises:
        OscalDocumentTypeMismatchError: The document is not a Component Definition.
        OscalParseError: As `parse_oscal_yaml` defines.
        ImportError: The ``yaml`` extra is not installed.
    """
    return _narrow_document(
        parse_oscal_yaml(data), ComponentDefinitionDocument, "a Component Definition"
    )


def parse_system_security_plan_yaml(data: str | bytes) -> SystemSecurityPlanDocument:
    """Parse an OSCAL System Security Plan document in YAML (YML-007).

    Parses as `parse_oscal_yaml` does, then returns the wrapper,
    a `SystemSecurityPlanDocument`.
    Requires the ``yaml`` extra.

    Raises:
        OscalDocumentTypeMismatchError: The document is not a System Security Plan.
        OscalParseError: As `parse_oscal_yaml` defines.
        ImportError: The ``yaml`` extra is not installed.
    """
    return _narrow_document(
        parse_oscal_yaml(data), SystemSecurityPlanDocument, "a System Security Plan"
    )


def parse_assessment_plan_yaml(data: str | bytes) -> AssessmentPlanDocument:
    """Parse an OSCAL Assessment Plan document in YAML (YML-007).

    Parses as `parse_oscal_yaml` does, then returns the wrapper,
    a `AssessmentPlanDocument`.
    Requires the ``yaml`` extra.

    Raises:
        OscalDocumentTypeMismatchError: The document is not an Assessment Plan.
        OscalParseError: As `parse_oscal_yaml` defines.
        ImportError: The ``yaml`` extra is not installed.
    """
    return _narrow_document(
        parse_oscal_yaml(data), AssessmentPlanDocument, "an Assessment Plan"
    )


def parse_assessment_results_yaml(data: str | bytes) -> AssessmentResultsDocument:
    """Parse an OSCAL Assessment Results document in YAML (YML-007).

    Parses as `parse_oscal_yaml` does, then returns the wrapper,
    a `AssessmentResultsDocument`.
    Requires the ``yaml`` extra.

    Raises:
        OscalDocumentTypeMismatchError: The document is not Assessment Results.
        OscalParseError: As `parse_oscal_yaml` defines.
        ImportError: The ``yaml`` extra is not installed.
    """
    return _narrow_document(
        parse_oscal_yaml(data), AssessmentResultsDocument, "Assessment Results"
    )


def parse_plan_of_action_and_milestones_yaml(
    data: str | bytes,
) -> PlanOfActionAndMilestonesDocument:
    """Parse an OSCAL Plan of Action and Milestones document in YAML (YML-007).

    Parses as `parse_oscal_yaml` does, then returns the wrapper,
    a `PlanOfActionAndMilestonesDocument`.
    Requires the ``yaml`` extra.

    Raises:
        OscalDocumentTypeMismatchError: The document is not a Plan of Action and
            Milestones.
        OscalParseError: As `parse_oscal_yaml` defines.
        ImportError: The ``yaml`` extra is not installed.
    """
    return _narrow_document(
        parse_oscal_yaml(data),
        PlanOfActionAndMilestonesDocument,
        "a Plan of Action and Milestones",
    )


def parse_mapping_collection_yaml(data: str | bytes) -> MappingCollectionDocument:
    """Parse an OSCAL Mapping Collection document in YAML (YML-007).

    Parses as `parse_oscal_yaml` does, then returns the wrapper,
    a `MappingCollectionDocument`.
    Requires the ``yaml`` extra.

    Raises:
        OscalDocumentTypeMismatchError: The document is not a Mapping Collection.
        OscalParseError: As `parse_oscal_yaml` defines.
        ImportError: The ``yaml`` extra is not installed.
    """
    return _narrow_document(
        parse_oscal_yaml(data), MappingCollectionDocument, "a Mapping Collection"
    )


def serialize_oscal_yaml(model: OscalDocument) -> str:
    """Serialize an OSCAL model to a YAML string (YML-008).

    Dumps the model through the JSON value with the JSON rules (OSCAL keys, no
    null), then writes that value as block-style YAML. SER-003 (the pretty and
    compact forms) does not apply to YAML, so this operation takes no form
    option. The output quotes a string that would read back as a number or a
    boolean, so a value like ``"1.0"`` stays a string (YML-008.02). A string
    that holds U+0085, U+2028, or U+2029 is written in double-quoted style with
    escapes, so every YAML reader reads the same characters back. Requires the
    ``yaml`` extra.

    Args:
        model: An `OscalDocument` to serialize.

    Returns:
        A YAML string for the document.

    Raises:
        ImportError: The ``yaml`` extra is not installed.
    """
    _require_yaml()
    from oscal_bindings.v1.extensions import _yaml_loader  # noqa: PLC0415

    return _yaml_loader.serialize_oscal_yaml(model)
