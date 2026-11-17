"""Translate an ECMA-262 pattern of the OSCAL schema to a Rust ``regex`` pattern.

JSON Schema writes a ``pattern`` in the regex dialect of ECMA-262. Pydantic
evaluates a pattern with the Rust ``regex`` engine of pydantic-core. The two
dialects differ for the constructs below, so a pattern that Pydantic reads as
written accepts values that the schema rejects (PRS-007).

``translate`` reads a pattern token by token and writes a Rust pattern that
accepts and rejects the same values as the ECMA-262 pattern with the ``u`` flag.
It knows these constructs:

1. ``.`` outside a class is a class that excludes the ECMA-262 line
   terminators: LF, CR, U+2028, and U+2029. Rust ``.`` excludes only LF.
2. ``\\s`` outside a class is a class of the ECMA-262 white space and line
   terminators. ``\\S`` is the complement. The Rust ``\\s`` has U+0085 and no
   U+FEFF, and ECMA-262 has the reverse.
3. A literal, an escaped literal, a code point escape (``\\xHH``, ``\\uHHHH``,
   ``\\u{H...}``), a class, a negated class, ``\\p{...}``, ``\\P{...}``, a group,
   an alternation, a quantifier, ``^``, and ``$`` stay as they are. A class holds
   literals, escaped literals, code point escapes, ranges, and ``\\p{...}``.
   Without the multiline flag, ``^`` and ``$`` mean the same in both dialects.
4. Each other construct is an error that names the pattern: lookaround, a
   back-reference, ``\\d``, ``\\w``, ``\\b``, ``\\s`` inside a class, and an
   inline flag.

The OSCAL 1.2.3 schema uses no construct of item 4. A new release that does
fails the generation here, so the mapping is never silently wrong.
"""

from __future__ import annotations

import re
from typing import Final

__all__ = ["RegexTranslationError", "translate"]

# The ECMA-262 line terminators, as Rust escapes.
_LINE_TERMINATORS: Final = r"\n\r\u{2028}\u{2029}"
# The ECMA-262 WhiteSpace and LineTerminator code points, as the body of a Rust
# class: TAB, LF, VT, FF, CR, SP, NBSP, U+1680, U+2000 to U+200A, U+2028,
# U+2029, U+202F, U+205F, U+3000, and U+FEFF.
_WHITE_SPACE: Final = (
    r"\t\n\x0b\x0c\r \u{a0}\u{1680}\u{2000}-\u{200a}"
    r"\u{2028}\u{2029}\u{202f}\u{205f}\u{3000}\u{feff}"
)

_DOT: Final = f"[^{_LINE_TERMINATORS}]"
_SPACE: Final = f"[{_WHITE_SPACE}]"
_NOT_SPACE: Final = f"[^{_WHITE_SPACE}]"

# An escaped literal: a syntax character of ECMA-262 or "-".
_SYNTAX_CHARACTERS: Final = frozenset("^$\\.*+?()[]{}|/-")
# A control escape that both dialects read the same way.
_CONTROL_ESCAPES: Final = frozenset("nrtfv")
_PROPERTY: Final = re.compile(r"\\[pP]\{[A-Za-z_=]+\}")
# A code point escape: both dialects read it alike, and ``translate`` writes
# some (``\x0b``, ``\u{2028}``), so its output is its own fixed point.
_CODE_POINT: Final = re.compile(
    r"\\(?:x[0-9A-Fa-f]{2}|u[0-9A-Fa-f]{4}|u\{[0-9A-Fa-f]{1,6}\})"
)
_QUANTIFIER: Final = re.compile(r"\{\d+(?:,\d*)?\}")
# Rust uses the escape of a control character, so the output holds no raw LF.
_RAW_ESCAPES: Final = {"\n": r"\n", "\r": r"\r", "\t": r"\t"}


class RegexTranslationError(ValueError):
    """Raised when a pattern has a construct that ``translate`` does not map."""

    def __init__(self, pattern: str, reason: str) -> None:
        self.pattern = pattern
        self.reason = reason
        super().__init__(f"Cannot translate the pattern {pattern!r}: {reason}")


def translate(pattern: str) -> str:
    """Return the Rust ``regex`` pattern for an ECMA-262 ``pattern``.

    Raises:
        RegexTranslationError: for a construct that the module docstring lists
            as an error, and for a pattern that is not well formed.
    """
    out: list[str] = []
    i = 0
    depth = 0
    while i < len(pattern):
        c = pattern[i]
        if c == "\\":
            token, i = _escape(pattern, i, in_class=False)
        elif c == "[":
            token, i = _class(pattern, i)
        elif c == "(":
            token, i = _open_group(pattern, i)
            depth += 1
        elif c == ")":
            depth -= 1
            if depth < 0:
                raise RegexTranslationError(pattern, "unbalanced ')'")
            token, i = c, i + 1
        elif c == "{":
            token, i = _quantifier(pattern, i)
        elif c in "]}":
            raise RegexTranslationError(pattern, f"unescaped {c!r} at {i}")
        else:
            token, i = (_DOT if c == "." else _RAW_ESCAPES.get(c, c)), i + 1
        out.append(token)
    if depth:
        raise RegexTranslationError(pattern, "unbalanced '('")
    return "".join(out)


def _open_group(pattern: str, i: int) -> tuple[str, int]:
    """Translate the group opener at ``pattern[i]``: ``(`` or ``(?:``."""
    if pattern.startswith("(?:", i):
        return "(?:", i + 3
    if pattern.startswith("(?", i):
        raise RegexTranslationError(pattern, f"group construct {pattern[i : i + 3]!r}")
    return "(", i + 1


def _quantifier(pattern: str, i: int) -> tuple[str, int]:
    """Translate the ``{n}``, ``{n,}``, or ``{n,m}`` quantifier at ``pattern[i]``."""
    match = _QUANTIFIER.match(pattern, i)
    if match is None:
        raise RegexTranslationError(pattern, f"unescaped '{{' at {i}")
    return match.group(), match.end()


def _escape(pattern: str, i: int, *, in_class: bool) -> tuple[str, int]:
    """Translate the escape at ``pattern[i]``. Return the token and the next index."""
    if i + 1 >= len(pattern):
        raise RegexTranslationError(pattern, "trailing backslash")
    c = pattern[i + 1]
    for kept in (_PROPERTY, _CODE_POINT):
        match = kept.match(pattern, i)
        if match is not None:
            return match.group(), match.end()
    if c in "sS":
        if in_class:
            raise RegexTranslationError(pattern, f"'\\{c}' inside a class")
        return (_SPACE if c == "s" else _NOT_SPACE), i + 2
    if c in "dDwWbB":
        raise RegexTranslationError(pattern, f"escape '\\{c}'")
    if c.isdigit() or c == "k":
        raise RegexTranslationError(pattern, f"back-reference '\\{c}'")
    if c in _SYNTAX_CHARACTERS:
        return f"\\{c}", i + 2
    if c in _CONTROL_ESCAPES:
        return f"\\{c}", i + 2
    raise RegexTranslationError(pattern, f"escape '\\{c}'")


def _class(pattern: str, start: int) -> tuple[str, int]:
    """Translate the class that starts at ``pattern[start]``."""
    out = ["["]
    i = start + 1
    if i < len(pattern) and pattern[i] == "^":
        out.append("^")
        i += 1
    members = 0
    while i < len(pattern):
        c = pattern[i]
        if c == "]":
            if members == 0:
                raise RegexTranslationError(pattern, "empty class")
            out.append("]")
            return "".join(out), i + 1
        if c == "\\":
            token, i = _escape(pattern, i, in_class=True)
            out.append(token)
        elif c == "[":
            raise RegexTranslationError(pattern, f"unescaped '[' in a class at {i}")
        else:
            out.append(_RAW_ESCAPES.get(c, c))
            i += 1
        members += 1
    raise RegexTranslationError(pattern, "unterminated class")
