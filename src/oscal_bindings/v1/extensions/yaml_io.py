"""Optional YAML parse and serialize for OSCAL documents.

This module implements the store's ``yaml-documents`` capability (YML-001 to
YML-011). It reads one YAML 1.2 document in UTF-8, converts it to the JSON value
that the existing JSON parser accepts, and reuses :func:`parse_oscal`. So the
YAML parse result equals the JSON parse result for the JSON text of the input
(YML-005), and the YAML path inherits the JSON path's Pydantic validation and
error detail.

YAML is an optional feature. It is available only when the ``yaml`` extra is
installed (``pip install oscal-bindings[yaml]``). Importing this module without
PyYAML raises :class:`ImportError` with an install hint (design Decision 5).

The loader is PyYAML driven through its node layer (``compose``), with a custom
walk, because PyYAML's defaults break the contract (design Decision 2):

* PyYAML follows YAML 1.1, so its implicit resolver would turn ``yes`` into a
  boolean and ``1.0`` into a float. The walk ignores the resolver and decides
  each scalar's type from the OSCAL schema at the scalar's location (YML-004).
* PyYAML silently overwrites a duplicate mapping key. The walk detects a
  repeated key at the node layer (YML-003).
* PyYAML treats ``<<`` as a merge key. The walk keys a mapping on the ``<<``
  text, so a merge key reaches Pydantic as an unknown field (YML-009).

The schema that drives scalar typing is reconstructed at import time from the
generated Pydantic models (``OscalDocument.model_json_schema()``), so no schema
artifact is needed at run time.

The binding limits collection-alias expansion to a fixed count (design
Decision 3, spec ``yaml-resource-limit``). An input whose collection aliases
expand past the limit is a parse error.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as _exc:  # pragma: no cover - exercised via a sys.modules shim
    _MSG = (
        "YAML support requires the 'yaml' extra. "
        "Install it with: pip install oscal-bindings[yaml]"
    )
    raise ImportError(_MSG) from _exc

from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

from oscal_bindings.v1.models import OscalDocument
from oscal_bindings.v1.parser import OscalParseError, parse_oscal

__all__ = [
    "parse_oscal_yaml",
    "parse_oscal_yaml_file",
    "serialize_oscal_yaml",
]

#: The maximum number of collection-alias resolutions the walk follows across a
#: whole document. An input whose collection aliases expand past this limit is a
#: parse error (spec ``yaml-resource-limit``, design Decision 3). The value sits
#: with the defaults of comparable parsers (js-yaml 100, SnakeYAML 128, Symfony
#: 128, Apple pkl 50). It is not configurable in this release.
COLLECTION_ALIAS_LIMIT = 100


# --- Schema model of scalar locations -------------------------------------
#
# The converter needs the base JSON type at each scalar location. OSCAL writes
# no `type` keyword at a scalar site; a location resolves through `$ref`,
# `anyOf`, and `allOf`. The Pydantic JSON Schema of the root document carries
# the same structure (an optional field appears as an `anyOf` with a `null`
# branch), so the converter resolves against it. The schema is built once.


class _Schema:
    """A resolver over the root document's JSON Schema.

    Maps a scalar location to its base JSON type, descends a mapping to a named
    field's subschema, and descends a sequence to its item subschema. It follows
    ``$ref``, strips the ``null`` branch of an optional field, folds an ``allOf``
    to one base type, and treats a string-plus-enum ``anyOf`` (an OSCAL open
    enum) as a string location (design Decision 1).
    """

    def __init__(self) -> None:
        schema = OscalDocument.model_json_schema()
        self._defs: dict[str, Any] = schema.get("$defs", {})
        # The root is an `anyOf` over the eight document wrappers.
        self.root: Any = schema

    def _deref(self, node: Any) -> Any:
        """Follow a ``$ref`` once to its definition."""
        if isinstance(node, dict) and "$ref" in node:
            name = node["$ref"].rsplit("/", 1)[-1]
            return self._defs.get(name, {})
        return node

    def _branches(self, node: Any) -> list[Any]:
        """Return the non-null branches of an ``anyOf``/``oneOf``, else ``[node]``.

        A ``null`` branch marks an optional field; it carries no type and is
        dropped. An ``allOf`` member list is not split here: ``_base_type``
        folds it.
        """
        node = self._deref(node)
        if not isinstance(node, dict):
            return [node]
        for key in ("anyOf", "oneOf"):
            if key in node:
                out: list[Any] = []
                for branch in node[key]:
                    resolved = self._deref(branch)
                    if resolved.get("type") == "null":
                        continue
                    out.append(resolved)
                return out
        return [node]

    def field(self, schema: Any, key: str) -> Any:
        """Return the subschema of mapping field ``key``, or ``None``.

        The key is matched against the ``properties`` of the resolved schema and
        of each object branch of an ``anyOf``/``oneOf``. The schema keys its
        properties by OSCAL alias (``last-modified``), which is the YAML key.
        """
        for branch in self._branches(schema):
            resolved = self._deref(branch)
            if not isinstance(resolved, dict):
                continue
            props = resolved.get("properties")
            if isinstance(props, dict) and key in props:
                return props[key]
        return None

    def items(self, schema: Any) -> Any:
        """Return the item subschema of a sequence location, or ``None``."""
        for branch in self._branches(schema):
            resolved = self._deref(branch)
            if isinstance(resolved, dict) and "items" in resolved:
                return resolved["items"]
        return None

    def base_type(self, schema: Any) -> str | None:
        """Return the base JSON type of a scalar location.

        One of ``"string"``, ``"number"``, ``"integer"``, or ``"boolean"``, or
        ``None`` when the location names no scalar type. A string-plus-enum
        ``anyOf`` (an OSCAL open enum) and an ``allOf`` over one integer or
        number base both fold to a single base type.
        """
        found: set[str] = set()
        for branch in self._branches(schema):
            resolved = self._deref(branch)
            if not isinstance(resolved, dict):
                continue
            t = resolved.get("type")
            if t in ("string", "number", "integer", "boolean"):
                found.add(t)
            elif "allOf" in resolved:
                for member in resolved["allOf"]:
                    mt = self._deref(member).get("type")
                    if mt in ("string", "number", "integer", "boolean"):
                        found.add(mt)
            elif "enum" in resolved:
                # A bare enum with no type sits beside a string datatype in an
                # OSCAL open enum. Treat it as a string location.
                found.add("string")
        if not found:
            return None
        # A number location that also admits an integer is a number location.
        if "string" in found:
            return "string"
        if "number" in found:
            return "number"
        if "integer" in found:
            return "integer"
        return "boolean"


# Built once at import; the schema does not change at run time.
_SCHEMA = _Schema()


# --- JSON number grammar (RFC 8259 section 6) ------------------------------

#: The JSON number grammar of RFC 8259: an optional minus, an integer part with
#: no leading zero, an optional fraction, and an optional exponent. No leading
#: plus, no leading zero, no hexadecimal (YML-004.07, YML-004.10).
_JSON_NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?\Z")


def _located_error(message: str, node: Node) -> OscalParseError:
    """Build a parse error with one structured entry at the node's location.

    The entry names the location (YML-010, PRS-006). PyYAML's node mark carries
    the line and column of the scalar in the input.
    """
    mark = node.start_mark
    loc = {"line": mark.line + 1, "column": mark.column + 1}
    return OscalParseError(message, errors=[{"loc": loc, "msg": message}])


# --- The node walk ---------------------------------------------------------


class _Walk:
    """Convert a composed PyYAML node graph to a JSON value.

    One instance handles one document. It carries the cumulative
    collection-alias count and the ancestor set that detects an alias inside its
    own anchored node.
    """

    def __init__(self) -> None:
        self._alias_resolutions = 0
        # Collection nodes seen at least once, by id. A second visit to one of
        # these is a collection-alias resolution (the node was reached again
        # through an alias), which counts against the limit. A node's first
        # visit is ordinary structure and does not count.
        self._seen: set[int] = set()
        # Nodes on the current ancestor path, by id, to catch a self-referential
        # alias (YML-009.02). `compose` does not raise on a cycle.
        self._ancestors: set[int] = set()

    def convert(self, node: Node, schema: Any) -> Any:
        """Convert ``node`` at schema location ``schema`` to a JSON value."""
        if isinstance(node, ScalarNode):
            return self._scalar(node, schema)
        if isinstance(node, SequenceNode):
            return self._sequence(node, schema)
        if isinstance(node, MappingNode):
            return self._mapping(node, schema)
        # PyYAML composes only scalar, sequence, and mapping nodes.
        kind = type(node).__name__  # pragma: no cover
        message = f"Unsupported YAML node: {kind}"  # pragma: no cover
        raise _located_error(message, node)  # pragma: no cover

    def _enter_collection(self, node: Node) -> None:
        """Guard a collection-node visit: the cycle check and the alias limit.

        A node already on the ancestor path is an alias inside its own anchored
        node (YML-009.02). A revisit to a collection node the walk has seen
        before is a collection-alias resolution: the same shared node was reached
        again through an alias. Each such resolution counts against the limit, so
        a billion-laughs expansion, which revisits shared collection nodes
        multiplicatively, trips the limit. A node's first visit is ordinary
        structure and does not count.
        """
        if id(node) in self._ancestors:
            message = "YAML alias refers to a node inside its own anchored node"
            raise _located_error(message, node)
        if id(node) in self._seen:
            self._alias_resolutions += 1
            if self._alias_resolutions > COLLECTION_ALIAS_LIMIT:
                message = (
                    "YAML collection-alias expansion exceeds the limit of "
                    f"{COLLECTION_ALIAS_LIMIT}"
                )
                raise _located_error(message, node)
        self._seen.add(id(node))
        self._ancestors.add(id(node))

    def _sequence(self, node: SequenceNode, schema: Any) -> list[Any]:
        self._enter_collection(node)
        item_schema = _SCHEMA.items(schema)
        result = [self.convert(child, item_schema) for child in node.value]
        self._ancestors.discard(id(node))
        return result

    def _mapping(self, node: MappingNode, schema: Any) -> dict[str, Any]:
        self._enter_collection(node)
        result: dict[str, Any] = {}
        for key_node, value_node in node.value:
            if not isinstance(key_node, ScalarNode):
                message = "YAML mapping key is not a scalar"
                raise _located_error(message, key_node)
            key = key_node.value
            if key in result:
                message = f"YAML mapping has a duplicate key: {key!r}"
                raise _located_error(message, key_node)
            field_schema = _SCHEMA.field(schema, key)
            result[key] = self.convert(value_node, field_schema)
        self._ancestors.discard(id(node))
        return result

    def _scalar(self, node: ScalarNode, schema: Any) -> Any:
        """Type one scalar from the schema location (design Decision 1).

        The node's tag is ignored: a tag does not change a value (YML-009).
        """
        text = node.value
        base = _SCHEMA.base_type(schema) if schema is not None else None
        if base is None or base == "string":
            # A string location, or a location with no scalar type: keep the
            # text. `null`, `~`, and an empty scalar stay their text.
            return text
        if base in ("number", "integer"):
            # A number or integer location accepts any JSON number token; the
            # schema's integer constraint is Pydantic's to enforce downstream.
            # A non-matching text (`+443`, `007`, `0x1BB`) is a located grammar
            # error (YML-004.07, YML-004.10, YML-010).
            if _JSON_NUMBER.match(text):
                return json.loads(text)
            message = (
                f"YAML scalar {text!r} does not match the JSON number grammar "
                "at this location"
            )
            raise _located_error(message, node)
        # base == "boolean"
        if text == "true":
            return True
        if text == "false":
            return False
        message = (
            f"YAML scalar {text!r} is not a JSON boolean (true or false) "
            "at this location"
        )
        raise _located_error(message, node)


# --- Stream handling (design Decision 6) -----------------------------------


def _compose_single(text: str) -> Node:
    """Compose one YAML document node from ``text``.

    Requires exactly one document. A syntax error, a stream with no document,
    and a stream with more than one document are all parse errors (YML-002.01 to
    YML-002.03).
    """
    try:
        nodes = list(yaml.compose_all(text, Loader=yaml.SafeLoader))
    except yaml.YAMLError as exc:
        message = f"Invalid YAML: {exc}"
        raise OscalParseError(message) from exc
    if not nodes:
        message = "YAML input holds no document"
        raise OscalParseError(message)
    if len(nodes) > 1:
        message = "YAML input holds more than one document"
        raise OscalParseError(message)
    return nodes[0]


def _decode(data: str | bytes) -> str:
    """Decode a YAML input to text, as the JSON parsers do (PRS-001.03).

    The binding decodes bytes as UTF-8 itself and maps a decode failure to the
    parse error, rather than passing raw bytes to PyYAML. PyYAML honors a UTF-16
    byte-order mark, so passing bytes would accept a UTF-16 input that YML-002.04
    requires the binding to reject.
    """
    if isinstance(data, str):
        return data
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        message = "YAML input is not valid UTF-8"
        raise OscalParseError(message) from exc


# --- Public operations -----------------------------------------------------


def parse_oscal_yaml(data: str | bytes) -> OscalDocument:
    """Parse an OSCAL YAML document into a typed Pydantic model (YML-005).

    Converts the YAML input to the JSON value that the JSON parser accepts,
    serializes it to JSON text, and calls :func:`parse_oscal`. The result equals
    the JSON parse result for the JSON text of the input.

    Args:
        data: One YAML 1.2 document, as ``str`` or ``bytes``. ``bytes`` is
            decoded as UTF-8 by the binding (YML-002.04).

    Returns:
        An :class:`OscalDocument` representing the parsed document.

    Raises:
        OscalParseError: The input is not one well-formed YAML 1.2 document in
            UTF-8, holds a duplicate key, carries a scalar whose text does not
            match the type at its location, expands collection aliases past the
            documented limit, or does not conform to the OSCAL schema.
    """
    text = _decode(data)
    node = _compose_single(text)
    json_value = _Walk().convert(node, _SCHEMA.root)
    return parse_oscal(json.dumps(json_value))


def parse_oscal_yaml_file(path: Path | str) -> OscalDocument:
    """Parse an OSCAL YAML file into a typed Pydantic model (YML-006).

    Reads the file at ``path`` and parses its content as :func:`parse_oscal_yaml`
    does. A missing file reports the not-found condition, as
    :func:`parse_oscal_file` does; that condition is distinct from the parse
    error (PRS-002).

    Args:
        path: Path to an OSCAL YAML file.

    Returns:
        An :class:`OscalDocument` representing the parsed document.

    Raises:
        FileNotFoundError: The file does not exist.
        OscalParseError: The file content is not valid OSCAL YAML.
    """
    file_path = Path(path)
    if not file_path.exists():
        message = f"OSCAL file not found: {file_path}"
        raise FileNotFoundError(message)
    try:
        raw = file_path.read_bytes()
    except OSError as exc:
        message = f"Failed to read file: {exc}"
        raise OscalParseError(message) from exc
    return parse_oscal_yaml(raw)


def serialize_oscal_yaml(model: OscalDocument) -> str:
    """Serialize an OSCAL model to a YAML string (YML-008).

    Dumps the model through the JSON value with the JSON rules (OSCAL alias keys,
    no null), then writes that value as block-style YAML. SER-003 (the pretty and
    compact forms) does not apply to YAML, so this operation takes no form
    option. A string-shaped scalar is quoted, so a round-trip keeps a value like
    ``"1.0"`` a string (YML-008.02).

    Args:
        model: An :class:`OscalDocument` to serialize.

    Returns:
        A YAML string representation of the document.
    """
    json_value = json.loads(model.model_dump_json(by_alias=True, exclude_none=True))
    dumped: str = yaml.safe_dump(
        json_value,
        default_flow_style=False,
        sort_keys=True,
        allow_unicode=True,
    )
    return dumped
