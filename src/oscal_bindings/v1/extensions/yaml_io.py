"""Optional YAML parse and serialize for OSCAL documents.

This module implements the store's ``yaml-documents`` capability (YML-001 to
YML-011), with one documented exception: the serializer inherits the JSON
path's datetime defect, so a seven-fraction-digit datetime loses its seventh
digit on a round trip. That narrows YML-008 and SER-005 until issue #19 closes.
The corpus marks ``yaml-round-trip/string-scalars`` as a known defect, and the
conformance run xfails it.

YAML is an optional feature. It needs the ``yaml`` extra
(``pip install oscal-bindings[yaml]``). This module does not import PyYAML when
it is imported, so every import path of the package works without the extra.
A call to one of the three operations imports PyYAML and raises
:class:`ImportError` with an install hint when the extra is missing.

A parse reads one YAML 1.2 document in UTF-8, converts it to JSON text, and
passes that text to :func:`~oscal_bindings.v1.parser.parse_oscal`. So the YAML
parse result equals the JSON parse result for the JSON text of the input
(YML-005), and the YAML path has the JSON path's validation and error detail.
The OSCAL schema decides the type of each scalar at its location (YML-004).

Resource limits (YML-011). A parse applies three documented limits, and an input
past any of them is an :class:`~oscal_bindings.v1.parser.OscalParseError`:

1. Alias nodes: aliases can add at most :data:`ALIAS_NODE_LIMIT` nodes. Each use
   of an alias adds every scalar, sequence, mapping, and mapping key of the
   value it expands to.
2. Alias characters: aliases can add at most :data:`ALIAS_CHAR_LIMIT` characters
   of scalar text and key text.
3. Depth: no node can sit deeper than :data:`DEPTH_LIMIT` sequences and
   mappings, counted after alias expansion.

Content that the input writes out, and that no alias repeats, does not count
against the two alias limits. No step of the parse recurses per nesting level,
so the depth limit, not the interpreter's stack, rejects deep input.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from oscal_bindings.v1.models import OscalDocument

__all__ = [
    "parse_oscal_yaml",
    "parse_oscal_yaml_file",
    "serialize_oscal_yaml",
]

#: The maximum number of nodes that aliases can add to one YAML input. Each use
#: of an alias adds every scalar, sequence, mapping, and mapping key of the value
#: it expands to, and an alias inside a repeated value adds its value each time.
ALIAS_NODE_LIMIT = 100_000

#: The maximum number of characters of scalar text and key text that aliases can
#: add to one YAML input, counted as :data:`ALIAS_NODE_LIMIT` counts nodes.
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
    """Import PyYAML, or raise :class:`ImportError` with the install hint."""
    try:
        import yaml  # noqa: F401, PLC0415 - imported at call time by design
    except ImportError as exc:
        raise ImportError(_INSTALL_HINT) from exc


def parse_oscal_yaml(data: str | bytes) -> OscalDocument:
    """Parse an OSCAL YAML document into a typed Pydantic model (YML-005).

    Converts the YAML input to JSON text and calls
    :func:`~oscal_bindings.v1.parser.parse_oscal`. The result equals the JSON
    parse result for the JSON text of the input. Requires the ``yaml`` extra.

    Args:
        data: One YAML 1.2 document, as ``str`` or ``bytes``. The binding
            decodes ``bytes`` as UTF-8 (YML-002.04).

    Returns:
        An :class:`~oscal_bindings.v1.models.OscalDocument` for the document.

    Raises:
        OscalParseError: The input is not one well-formed YAML 1.2 document in
            UTF-8, holds a duplicate or non-scalar key, holds a scalar whose
            text does not match the type at its location, passes a resource
            limit of this module, or does not conform to the OSCAL schema. A
            failure that the YAML layer finds carries one ``errors`` entry with
            the keys ``type``, ``loc`` (the JSON path), ``msg``, ``input``,
            ``line``, and ``column``.
        ImportError: The ``yaml`` extra is not installed.
    """
    _require_yaml()
    from oscal_bindings.v1.extensions import _yaml_loader  # noqa: PLC0415

    return _yaml_loader.parse_oscal_yaml(data)


def parse_oscal_yaml_file(path: Path | str) -> OscalDocument:
    """Parse an OSCAL YAML file into a typed Pydantic model (YML-006).

    Reads the file at ``path`` and parses its content as
    :func:`parse_oscal_yaml` does. A missing file reports the not-found
    condition, as :func:`~oscal_bindings.v1.parser.parse_oscal_file` does. That
    condition is distinct from the parse error (PRS-002). Requires the ``yaml``
    extra.

    Args:
        path: Path to an OSCAL YAML file.

    Returns:
        An :class:`~oscal_bindings.v1.models.OscalDocument` for the document.

    Raises:
        FileNotFoundError: The file does not exist.
        OscalParseError: The file cannot be read, or its content is not valid
            OSCAL YAML, as :func:`parse_oscal_yaml` defines.
        ImportError: The ``yaml`` extra is not installed.
    """
    _require_yaml()
    from oscal_bindings.v1.extensions import _yaml_loader  # noqa: PLC0415

    return _yaml_loader.parse_oscal_yaml_file(Path(path))


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
        model: An :class:`~oscal_bindings.v1.models.OscalDocument` to serialize.

    Returns:
        A YAML string for the document.

    Raises:
        ImportError: The ``yaml`` extra is not installed.
    """
    _require_yaml()
    from oscal_bindings.v1.extensions import _yaml_loader  # noqa: PLC0415

    return _yaml_loader.serialize_oscal_yaml(model)
