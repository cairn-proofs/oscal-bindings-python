"""PyYAML-backed implementation of :mod:`oscal_bindings.v1.extensions.yaml_io`.

Private. The public functions in ``yaml_io`` import this module when they are
called, so only a call needs PyYAML. See ``yaml_io`` for the contract, and the
``add-yaml-io`` design for the decisions this module implements.

The parse has three stages, and none of them recurses per nesting level:

1. ``_shield`` replaces each raw U+0085, U+2028, and U+2029 with a private-use
   placeholder. PyYAML's scanner reads these three characters as line breaks
   (YAML 1.1). YAML 1.2 reads them as content, and the composer restores them.
2. ``_compose`` reads PyYAML's event stream (a state machine in both the libyaml
   and the pure-Python parser) and builds a node tree with an explicit stack.
   It checks the written depth, resolves anchors as YAML 1.2 does, and rejects
   an alias inside its own anchored node.
3. ``_Walk`` walks the tree with an explicit stack and writes JSON text. It
   types each scalar from the schema at its location, rejects duplicate and
   non-scalar keys, checks the expanded depth, and charges the alias budget.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, NoReturn

import yaml
from yaml.events import (
    AliasEvent,
    CollectionStartEvent,
    DocumentEndEvent,
    DocumentStartEvent,
    MappingStartEvent,
    ScalarEvent,
    StreamEndEvent,
    StreamStartEvent,
)

from oscal_bindings.v1.extensions.yaml_io import (
    ALIAS_CHAR_LIMIT,
    ALIAS_NODE_LIMIT,
    DEPTH_LIMIT,
)
from oscal_bindings.v1.models import OscalDocument
from oscal_bindings.v1.parser import (
    JSON_DIGIT_LIMIT,
    JSON_DIGIT_LIMIT_MSG,
    OscalParseError,
    _read_oscal_file,
    parse_oscal,
)

if TYPE_CHECKING:
    from pathlib import Path


def select_loader(module: Any = yaml) -> Any:
    """Return libyaml's event parser when ``module`` has it, else PyYAML's own.

    libyaml's parser is about four times faster, and both emit the same events
    and marks. A PyYAML build without libyaml has only the pure-Python parser.
    """
    return getattr(module, "CSafeLoader", module.SafeLoader)


#: The event parser that the parse uses.
_LOADER: Any = select_loader()

#: The YAML versions that a `%YAML` directive can name. YAML 1.2.2 section 6.8.1
#: requires a 1.2 processor to accept a 1.1 document and to read it as 1.2.
_VERSIONS = frozenset({(1, 1), (1, 2)})

#: A surrogate code point. Only an escape can put one in a scalar's text, and
#: YAML 1.2 defines an escape as a Unicode scalar value, which a surrogate is not.
_SURROGATE = re.compile("[\ud800-\udfff]")

#: The maximum number of input characters that a parse-error message quotes.
_QUOTE_LIMIT = 40

# JSON string encoder: escapes every non-ASCII character, so a lone surrogate
# from a YAML escape reaches the JSON parser as an escape, as `json.dumps` does.
_encode_str = json.encoder.encode_basestring_ascii  # type: ignore[attr-defined]


# --- Errors ------------------------------------------------------------------


def _brief(text: str) -> str:
    """Return ``repr(text)``, shortened to ``_QUOTE_LIMIT`` characters of text.

    A message quotes input through this function, so a large hostile scalar
    cannot make a message, or a log that writes it, as large as the input. The
    error entry's ``input`` key keeps the whole text.
    """
    if len(text) <= _QUOTE_LIMIT:
        return repr(text)
    return f"{text[:_QUOTE_LIMIT]!r}... ({len(text):,} characters)"


def _fail(
    kind: str,
    message: str,
    *,
    loc: tuple[str | int, ...] = (),
    at: tuple[int | None, int | None] = (None, None),
    text: str | None = None,
) -> NoReturn:
    """Raise a parse error with one entry in the Pydantic entry shape.

    ``loc`` is the JSON path, as in a Pydantic entry. ``at`` is the 1-based line
    and column in the YAML source.
    """
    line, column = at
    entry = {
        "type": f"yaml_{kind}",
        "loc": loc,
        "msg": message,
        "input": text,
        "line": line,
        "column": column,
    }
    raise OscalParseError(message, errors=[entry])


# --- Stage 1: YAML 1.1 line-break characters ----------------------------------

#: The characters that YAML 1.1 reads as line breaks and YAML 1.2 reads as
#: content.
_YAML11_BREAKS = ("\x85", "\u2028", "\u2029")

#: A `\u` or `\U` escape. The code point it names is not free as a placeholder,
#: because a double-quoted scalar can produce it. A match outside a quoted
#: scalar only excludes one more code point, which is safe.
_ESCAPE = re.compile(r"\\(?:u([0-9A-Fa-f]{4})|U([0-9A-Fa-f]{8}))")

#: The placeholder candidates, in the order the binding takes them: the
#: supplementary private-use planes 15 and 16, then the BMP private-use area.
#: Both parsers read a private-use character as printable content. About
#: 137,000 candidates, so only an input built to hold every one of them, at
#: least 520 KB, leaves too few free (a documented limit, PRS-010).
PLACEHOLDER_CANDIDATES = (
    range(0xF0000, 0xFFFFE),
    range(0x100000, 0x10FFFE),
    range(0xE000, 0xF900),
)


def _is_private_use(cp: int) -> bool:
    return any(cp in r for r in PLACEHOLDER_CANDIDATES)


def _shield(text: str) -> tuple[str, dict[int, int] | None]:
    """Replace each YAML 1.1 line-break character with a free placeholder.

    Returns the new text and the ``str.translate`` table that restores the
    original characters, or ``None`` when the text holds none of them.
    """
    if not any(ch in text for ch in _YAML11_BREAKS):
        return text, None
    taken = {cp for cp in map(ord, set(text)) if _is_private_use(cp)}
    for m in _ESCAPE.finditer(text):
        taken.add(int(m.group(1) or m.group(2), 16))
    free = (cp for r in PLACEHOLDER_CANDIDATES for cp in r if cp not in taken)
    chosen = [cp for _, cp in zip(_YAML11_BREAKS, free, strict=False)]
    if len(chosen) < len(_YAML11_BREAKS):
        _fail(
            "line_break_placeholder",
            "YAML input holds U+0085, U+2028, or U+2029 and leaves no free "
            "private-use placeholder for it",
        )
    forward = {ord(ch): cp for ch, cp in zip(_YAML11_BREAKS, chosen, strict=True)}
    restore = {cp: ord(ch) for ch, cp in zip(_YAML11_BREAKS, chosen, strict=True)}
    return text.translate(forward), restore


# --- Stage 2: the composer ------------------------------------------------------

_SCALAR, _SEQUENCE, _MAPPING = 0, 1, 2


@dataclass(eq=False, slots=True)
class _Node:
    """One node of the composed tree.

    ``text`` holds a scalar's text. ``items`` holds a sequence's children, or a
    mapping's keys and values in alternation. A child is a ``_Node`` or an
    ``_Alias``. ``closed`` is false while the node is open on the composer's
    stack.
    """

    kind: int
    line: int
    column: int
    items: list[_Node | _Alias]
    text: str = ""
    closed: bool = False


#: The ``items`` of every scalar node. A scalar never adds an item, so one shared
#: empty list saves one list per scalar.
_NO_ITEMS: list[_Node | _Alias] = []


@dataclass(eq=False, slots=True)
class _Alias:
    """A use of an alias: a reference to its anchored node, and its position."""

    target: _Node
    line: int
    column: int


def _mark(event: Any) -> tuple[int, int]:
    mark = event.start_mark
    return mark.line + 1, mark.column + 1


def _compose(text: str, restore: dict[int, int] | None) -> _Node:
    """Compose the one document of ``text`` into a node tree (YML-002).

    A syntax error, a stream with no document, and a stream with more than one
    document are parse errors. The composer checks the written depth against
    ``DEPTH_LIMIT``.
    """
    loader = None
    try:
        # Both parsers can reject the text when they are created: the
        # pure-Python one rejects a NUL, and libyaml rejects a lone surrogate.
        loader = _LOADER(text)
        return _compose_events(loader, restore)
    except yaml.MarkedYAMLError as exc:
        mark = exc.problem_mark or exc.context_mark
        line = mark.line + 1 if mark is not None else None
        column = mark.column + 1 if mark is not None else None
        # libyaml rejects a `%YAML` version it does not know in the parser.
        kind = "version" if "incompatible YAML document" in str(exc) else "syntax"
        _fail(kind, f"Invalid YAML: {exc}", at=(line, column))
    except yaml.YAMLError as exc:
        # A reader error: a character that YAML does not allow, such as a NUL.
        _fail("syntax", f"Invalid YAML: {exc}")
    except UnicodeEncodeError as exc:
        _fail(
            "encoding",
            "YAML input holds a lone surrogate, which is not a Unicode character",
            at=_position(text[: exc.start]),
        )
    finally:
        if loader is not None:
            loader.dispose()


def _compose_child(
    event: Any,
    depth: int,
    anchors: dict[str, _Node],
    restore: dict[int, int] | None,
) -> _Node | _Alias:
    """Build the child that a scalar, collection-start, or alias event adds.

    ``depth`` is the number of open collections, which is the child's depth.
    """
    at = _mark(event)
    if depth > DEPTH_LIMIT:
        _fail(
            "depth_limit",
            f"YAML nesting exceeds the depth limit of {DEPTH_LIMIT}",
            at=at,
        )
    if isinstance(event, AliasEvent):
        target = anchors.get(event.anchor or "")
        if target is None:
            _fail(
                "undefined_alias",
                "YAML alias refers to an undefined anchor: "
                f"{_brief(event.anchor or '')}",
                at=at,
            )
        if not target.closed:
            _fail(
                "alias_cycle",
                "YAML alias refers to a node inside its own anchored node",
                at=at,
            )
        return _Alias(target, *at)
    if isinstance(event, ScalarEvent):
        text = event.value if restore is None else event.value.translate(restore)
        if _SURROGATE.search(text):
            _fail(
                "surrogate_escape",
                "YAML escape names a surrogate, which is not a Unicode character",
                at=at,
            )
        child = _Node(_SCALAR, *at, _NO_ITEMS, text=text, closed=True)
    else:
        kind = _MAPPING if isinstance(event, MappingStartEvent) else _SEQUENCE
        child = _Node(kind, *at, [])
    if event.anchor is not None:
        # YAML 1.2: a later anchor with the same name redefines it.
        anchors[event.anchor] = child
    return child


def _compose_events(loader: Any, restore: dict[int, int] | None) -> _Node:
    event = loader.get_event()
    if not isinstance(event, StreamStartEvent):  # pragma: no cover - parser invariant
        _fail("syntax", "Invalid YAML: no stream start")
    if loader.check_event(StreamEndEvent):
        _fail("stream", "YAML input holds no document", at=_mark(loader.peek_event()))
    start = loader.get_event()
    if isinstance(start, DocumentStartEvent) and start.version is not None:
        version = tuple(start.version)
        if version not in _VERSIONS:
            _fail(
                "version",
                f"YAML version {'.'.join(map(str, version))} is not supported; "
                "the binding reads YAML 1.2 and YAML 1.1 documents",
                at=_mark(start),
            )

    anchors: dict[str, _Node] = {}
    stack: list[_Node] = []
    root: _Node | _Alias | None = None

    while root is None or stack:
        event = loader.get_event()
        if not isinstance(event, ScalarEvent | CollectionStartEvent | AliasEvent):
            stack.pop().closed = True  # SequenceEndEvent or MappingEndEvent
            continue
        child = _compose_child(event, len(stack), anchors, restore)
        if stack:
            stack[-1].items.append(child)
        else:
            root = child
        if isinstance(child, _Node) and child.kind != _SCALAR:
            stack.append(child)

    if not isinstance(loader.get_event(), DocumentEndEvent):  # pragma: no cover
        _fail("syntax", "Invalid YAML: no document end")
    if not loader.check_event(StreamEndEvent):
        _fail(
            "stream",
            "YAML input holds more than one document",
            at=_mark(loader.peek_event()),
        )
    if not isinstance(root, _Node):  # pragma: no cover - no anchor precedes the root
        _fail("undefined_alias", "YAML document root is an alias")
    return root


# --- Schema model of scalar locations ---------------------------------------
#
# The walk needs the base JSON type at each scalar location. OSCAL writes no
# `type` keyword at a scalar site. A location resolves through `$ref`, `anyOf`,
# and `allOf`. The Pydantic JSON Schema of the root document has the same
# structure (an optional field is an `anyOf` with a `null` branch), so the walk
# resolves against it.

_SCALAR_TYPES = ("string", "number", "integer", "boolean")


class _Schema:
    """A resolver over the root document's JSON Schema (design Decision 1).

    Maps a scalar location to its base JSON type, a mapping location and a key
    to the key's subschema, and a sequence location to its item subschema. It
    follows ``$ref``, drops the ``null`` branch of an optional field, folds an
    ``allOf`` to one base type, and reads a string-plus-enum ``anyOf`` (an OSCAL
    open enum) as a string location. Results are cached by schema identity.
    """

    def __init__(self) -> None:
        schema = OscalDocument.model_json_schema()
        self.defs: dict[str, Any] = schema.get("$defs", {})
        #: The root location: an `anyOf` over the eight document wrappers.
        self.root: Any = schema
        # The caches key on `id()` of a subschema, never on a key from the
        # input, so their size is bounded by the schema. `id()` keys are safe
        # only because every subschema is part of `self.root`, which `_SCHEMA`
        # keeps for the life of the process, so no `id()` is reused. Do not
        # cache a schema dict that the resolver builds on the fly (see `deref`).
        self._props_cache: dict[int, dict[str, Any]] = {}
        self._items_cache: dict[int, Any] = {}
        self._type_cache: dict[int, str | None] = {}

    def cache_sizes(self) -> tuple[int, int, int]:
        """Return the entry counts of the three caches, for tests."""
        return len(self._props_cache), len(self._items_cache), len(self._type_cache)

    def deref(self, node: Any) -> Any:
        """Follow a ``$ref`` once to its definition."""
        if isinstance(node, dict) and "$ref" in node:
            name = node["$ref"].rsplit("/", 1)[-1]
            return self.defs.get(name, {})
        return node

    def branches(self, node: Any) -> list[Any]:
        """Return the non-null branches of an ``anyOf``/``oneOf``, else ``[node]``."""
        node = self.deref(node)
        if not isinstance(node, dict):
            return [node]
        for key in ("anyOf", "oneOf"):
            if key in node:
                out: list[Any] = []
                for branch in node[key]:
                    resolved = self.deref(branch)
                    if isinstance(resolved, dict) and resolved.get("type") == "null":
                        continue
                    out.append(resolved)
                return out
        return [node]

    def field(self, schema: Any, key: str) -> Any:
        """Return the subschema of mapping key ``key``, or ``None``.

        The first object branch that declares the key decides. The schema keys
        its properties by OSCAL name (``last-modified``), which is the YAML key.
        """
        if schema is None:
            return None
        return self.properties(schema).get(key)

    def properties(self, schema: Any) -> dict[str, Any]:
        """Return the merged properties of a mapping location.

        The first branch that declares a key wins. The result is cached per
        schema node, so an unknown key from the input adds no cache entry.
        """
        cache_key = id(schema)
        cached = self._props_cache.get(cache_key)
        if cached is not None:
            return cached
        merged: dict[str, Any] = {}
        for branch in self.branches(schema):
            resolved = self.deref(branch)
            props = resolved.get("properties") if isinstance(resolved, dict) else None
            if isinstance(props, dict):
                for name, sub in props.items():
                    merged.setdefault(name, sub)
        self._props_cache[cache_key] = merged
        return merged

    def items(self, schema: Any) -> Any:
        """Return the item subschema of a sequence location, or ``None``."""
        if schema is None:
            return None
        cache_key = id(schema)
        if cache_key in self._items_cache:
            return self._items_cache[cache_key]
        found = None
        for branch in self.branches(schema):
            resolved = self.deref(branch)
            if isinstance(resolved, dict) and "items" in resolved:
                found = resolved["items"]
                break
        self._items_cache[cache_key] = found
        return found

    def scalar_types(self, schema: Any) -> set[str]:
        """Return every base JSON type that a scalar location names."""
        found: set[str] = set()
        for branch in self.branches(schema):
            resolved = self.deref(branch)
            if not isinstance(resolved, dict):
                continue
            t = resolved.get("type")
            if t in _SCALAR_TYPES:
                found.add(t)
            elif "allOf" in resolved:
                for member in resolved["allOf"]:
                    mt = self.deref(member).get("type")
                    if mt in _SCALAR_TYPES:
                        found.add(mt)
            elif "enum" in resolved:
                # A bare enum with no type sits beside a string datatype in an
                # OSCAL open enum. Read it as a string location.
                found.add("string")
        return found

    def base_type(self, schema: Any) -> str | None:
        """Return the base JSON type of a scalar location, or ``None``.

        One of ``"string"``, ``"number"``, ``"integer"``, or ``"boolean"``. More
        than one type folds by priority. A test checks that no location of the
        pinned schema has more than one.
        """
        if schema is None:
            return None
        cache_key = id(schema)
        if cache_key in self._type_cache:
            return self._type_cache[cache_key]
        found = self.scalar_types(schema)
        result = next((t for t in _SCALAR_TYPES if t in found), None)
        self._type_cache[cache_key] = result
        return result


_SCHEMA = _Schema()


# --- Stage 3: the walk --------------------------------------------------------

#: The JSON number grammar of RFC 8259: an optional minus, an integer part with
#: no leading zero, an optional fraction, and an optional exponent. No leading
#: plus, no leading zero, no hexadecimal (YML-004.07, YML-004.10).
_JSON_NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")

#: The integer part of a number that matches ``_JSON_NUMBER``: group 1 holds
#: its digits, without the sign.
_INTEGER_PART = re.compile(r"-?([0-9]+)")


@dataclass(slots=True)
class _Frame:
    """One open sequence or mapping of the walk."""

    node: _Node
    schema: Any
    slot: str | int | None  # this frame's key or index in its parent
    depth: int  # the depth of this collection
    charged: bool  # true inside an alias
    index: int = 0
    keys: set[str] = field(default_factory=set)


class _Walk:
    """Write the JSON text of a composed tree, with an explicit stack."""

    #: The walk joins its output into one chunk after this many pieces, so it
    #: keeps the JSON text, not one string object per node.
    CHUNK = 4096

    def __init__(self) -> None:
        self.out: list[str] = []
        self.chunks: list[str] = []
        self.stack: list[_Frame] = []
        self.alias_nodes = 0
        self.alias_chars = 0

    def path(self, slot: str | int | None) -> tuple[str | int, ...]:
        """Return the JSON path of ``slot`` in the innermost open frame."""
        parts = [f.slot for f in self.stack]
        parts.append(slot)
        return tuple(p for p in parts if p is not None)

    def charge(
        self, chars: int, line: int, column: int, slot: str | int | None
    ) -> None:
        """Charge one node and ``chars`` characters against the alias budget."""
        self.alias_nodes += 1
        self.alias_chars += chars
        if self.alias_nodes > ALIAS_NODE_LIMIT:
            _fail(
                "alias_budget",
                f"YAML aliases add more than the limit of {ALIAS_NODE_LIMIT:,} nodes",
                loc=self.path(slot),
                at=(line, column),
            )
        if self.alias_chars > ALIAS_CHAR_LIMIT:
            _fail(
                "alias_budget",
                "YAML aliases add more than the limit of "
                f"{ALIAS_CHAR_LIMIT:,} characters",
                loc=self.path(slot),
                at=(line, column),
            )

    def run(self, root: _Node) -> str:
        self.emit(root, _SCHEMA.root, None, 0, charged=False)
        out = self.out
        stack = self.stack
        while stack:
            if len(out) > self.CHUNK:
                self.chunks.append("".join(out))
                out.clear()
            f = stack[-1]
            items = f.node.items
            if f.node.kind == _SEQUENCE:
                if f.index == len(items):
                    out.append("]")
                    stack.pop()
                    continue
                if f.index:
                    out.append(",")
                slot: str | int = f.index
                child = items[f.index]
                f.index += 1
                self.emit(child, _SCHEMA.items(f.schema), slot, f.depth + 1, f.charged)
            else:
                if f.index == len(items):
                    out.append("}")
                    stack.pop()
                    continue
                key = self.key(f, items[f.index])
                child = items[f.index + 1]
                if f.index:
                    out.append(",")
                f.index += 2
                out.append(_encode_str(key))
                out.append(":")
                self.emit(
                    child, _SCHEMA.field(f.schema, key), key, f.depth + 1, f.charged
                )
        self.chunks.append("".join(out))
        return "".join(self.chunks)

    def key(self, f: _Frame, key_item: _Node | _Alias) -> str:
        """Return a mapping key's text, after the key rules of YML-003."""
        charged = f.charged
        node = key_item
        if isinstance(node, _Alias):
            charged = True
            node = node.target
        if node.kind != _SCALAR:
            _fail(
                "key_not_scalar",
                "YAML mapping key is not a scalar",
                loc=self.path(None),
                at=(node.line, node.column),
            )
        key = node.text
        if charged:
            self.charge(len(key), node.line, node.column, key)
        if key in f.keys:
            _fail(
                "duplicate_key",
                f"YAML mapping has a duplicate key: {_brief(key)}",
                loc=self.path(key),
                at=(node.line, node.column),
                text=key,
            )
        f.keys.add(key)
        return key

    def emit(
        self,
        item: _Node | _Alias,
        schema: Any,
        slot: str | int | None,
        depth: int,
        charged: bool,
    ) -> None:
        """Write one value, or open a frame for a collection."""
        node = item.target if isinstance(item, _Alias) else item
        charged = charged or node is not item
        if depth > DEPTH_LIMIT:
            _fail(
                "depth_limit",
                f"YAML nesting exceeds the depth limit of {DEPTH_LIMIT}",
                loc=self.path(slot),
                at=(item.line, item.column),
            )
        if node.kind == _SCALAR:
            if charged:
                self.charge(len(node.text), node.line, node.column, slot)
            self.out.append(self.scalar(node, schema, slot))
            return
        if charged:
            self.charge(0, node.line, node.column, slot)
        self.out.append("[" if node.kind == _SEQUENCE else "{")
        self.stack.append(_Frame(node, schema, slot, depth, charged))

    def scalar(self, node: _Node, schema: Any, slot: str | int | None) -> str:
        """Return the JSON text of one scalar, typed by its location (Decision 1).

        The node's tag is ignored: a tag does not change a value (YML-009).
        """
        text = node.text
        base = _SCHEMA.base_type(schema)
        if base is None or base == "string":
            # A string location, or a location with no scalar type: keep the
            # text. `null`, `~`, and an empty scalar stay their text.
            return _encode_str(text)  # type: ignore[no-any-return]
        if base in ("number", "integer"):
            # The number is written as the text of its scalar (YML-005). The
            # schema's integer constraint is Pydantic's to enforce.
            if _JSON_NUMBER.fullmatch(text):
                # The JSON digit limit (PRS-010, design D2a). The reader checks
                # it here, so that the error gives the YAML location, not a
                # position in the JSON text that the reader builds.
                integer = _INTEGER_PART.match(text)
                if integer and len(integer[1]) > JSON_DIGIT_LIMIT:
                    entry = {
                        "type": "json_digit_limit",
                        "loc": self.path(slot),
                        "msg": JSON_DIGIT_LIMIT_MSG,
                        "input": None,
                        "line": node.line,
                        "column": node.column,
                    }
                    raise OscalParseError(JSON_DIGIT_LIMIT_MSG, errors=[entry])
                return text
            _fail(
                "number_grammar",
                f"YAML scalar {_brief(text)} does not match the JSON number grammar "
                "at this location",
                loc=self.path(slot),
                at=(node.line, node.column),
                text=text,
            )
        if text in ("true", "false"):
            return text
        _fail(
            "boolean_grammar",
            f"YAML scalar {_brief(text)} is not a JSON boolean (true or false) "
            "at this location",
            loc=self.path(slot),
            at=(node.line, node.column),
            text=text,
        )


# --- Public operations ---------------------------------------------------------


def _decode(data: str | bytes) -> str:
    """Decode a YAML input to text, as the JSON parsers do (PRS-001.03).

    The binding decodes bytes as UTF-8 itself. PyYAML honors a UTF-16 byte-order
    mark, so passing it bytes would accept a UTF-16 input that YML-002.04
    requires the binding to reject.
    """
    if isinstance(data, str):
        return data
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        # The bytes before the first invalid byte are valid UTF-8. Count lines
        # over LF, CR, and CRLF, as YAML 1.2 does, and columns in characters.
        at = _position(data[: exc.start].decode("utf-8"))
        _fail("encoding", "YAML input is not valid UTF-8", at=at)


_LINE_BREAK = re.compile("\r\n|\r|\n")


def _position(prefix: str) -> tuple[int, int]:
    """Return the 1-based line and character column just after ``prefix``.

    Lines break at LF, CR, and CRLF, as YAML 1.2 defines.
    """
    lines = _LINE_BREAK.split(prefix)
    return len(lines), len(lines[-1]) + 1


def to_json_text(data: str | bytes) -> str:
    """Convert one YAML document to the JSON text that YML-005 defines."""
    text, restore = _shield(_decode(data))
    return _Walk().run(_compose(text, restore))


def parse_oscal_yaml(data: str | bytes) -> OscalDocument:
    """Implement :func:`oscal_bindings.v1.extensions.yaml_io.parse_oscal_yaml`."""
    return parse_oscal(to_json_text(data))


def parse_oscal_yaml_file(path: Path) -> OscalDocument:
    """Implement :func:`oscal_bindings.v1.extensions.yaml_io.parse_oscal_yaml_file`."""
    return parse_oscal_yaml(_read_oscal_file(path))


def _represent_str(dumper: Any, data: str) -> yaml.ScalarNode:
    # PyYAML writes U+0085 as a raw break in a single-quoted scalar, which a
    # YAML 1.1 reader folds. Double-quoted style writes the escapes \N, \L, \P.
    if any(ch in data for ch in _YAML11_BREAKS):
        return dumper.represent_scalar(  # type: ignore[no-any-return]
            "tag:yaml.org,2002:str", data, style='"'
        )
    return dumper.represent_str(data)  # type: ignore[no-any-return]


def select_dumper(module: Any = yaml) -> Any:
    """Return a safe dumper that escapes the YAML 1.1 line-break characters.

    It is built on libyaml's emitter when ``module`` has it, else on PyYAML's
    own. libyaml's emitter is about three times faster on a large catalog.
    """
    base = getattr(module, "CSafeDumper", module.SafeDumper)
    dumper: Any = type("_Dumper", (base,), {})
    dumper.add_representer(str, _represent_str)
    return dumper


#: The dumper that the serializer uses.
_DUMPER: Any = select_dumper()


def serialize_oscal_yaml(model: OscalDocument) -> str:
    """Implement :func:`oscal_bindings.v1.extensions.yaml_io.serialize_oscal_yaml`."""
    json_value = json.loads(model.model_dump_json(by_alias=True, exclude_none=True))
    dumped: str = yaml.dump(
        json_value,
        Dumper=_DUMPER,
        default_flow_style=False,
        sort_keys=True,
        allow_unicode=True,
    )
    return dumped
