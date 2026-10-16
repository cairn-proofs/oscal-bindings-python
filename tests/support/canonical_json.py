"""The canonical JSON form of the OSCAL bindings contract, for conformance tests.

Implements ``docs/canonical-json.md`` of the spec artifact:

1. Parse the JSON. A duplicate object key is not valid input.
2. Normalize each datetime value: a string under one of ``DATETIME_KEYS``. A
   zero offset becomes ``Z``, and trailing zeros of the fraction are removed.
3. Serialize with RFC 8785 (JCS): keys sorted by UTF-16 code units, no
   whitespace, JCS string escapes, and the ECMAScript number format.
"""

from __future__ import annotations

import json
import math
import re
from decimal import Decimal
from typing import Any

DATETIME_KEYS = frozenset(
    {
        "collected",
        "date",
        "deadline",
        "end",
        "expires",
        "last-modified",
        "published",
        "start",
    }
)

_DATETIME = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:\d{2})?$"
)
# ECMAScript writes an integer-valued number below this in plain digits.
_PLAIN_LIMIT = 21
# ECMAScript uses an exponent at this many leading fraction zeros or more.
_SMALL_LIMIT = -6


class DuplicateKeyError(ValueError):
    """Raised when a JSON object has the same key twice."""


def normalize_datetime(value: str) -> str:
    """Write a zero offset as Z and remove trailing fraction zeros.

    A string that is not a datetime stays as it is.
    """
    match = _DATETIME.match(value)
    if not match:
        return value
    base, fraction, offset = match.groups()
    fraction = (fraction or "").rstrip("0")
    if offset in {"+00:00", "-00:00"}:
        offset = "Z"
    return f"{base}{'.' + fraction if fraction else ''}{offset or ''}"


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            msg = f"duplicate key {key!r}"
            raise DuplicateKeyError(msg)
        out[key] = value
    return out


def parse_strict(text: str | bytes) -> Any:
    """Parse JSON text and reject duplicate keys (canonical-json.md, step 1)."""
    return json.loads(text, object_pairs_hook=_reject_duplicates)


def format_number(value: float) -> str:  # noqa: PLR0911 -- one case per ECMAScript branch
    """Return the ECMAScript number-to-string form of ``value``, as JCS requires."""
    number = float(value)
    if not math.isfinite(number):
        msg = f"number {value!r} has no JSON form"
        raise ValueError(msg)
    if number == 0:
        return "0"  # also -0
    if number < 0:
        return "-" + format_number(-number)
    # repr gives the shortest digits that round-trip, as ECMAScript does.
    _, digit_tuple, exponent = Decimal(repr(number)).as_tuple()
    if not isinstance(exponent, int):  # pragma: no cover -- number is finite
        msg = f"number {value!r} has no exponent"
        raise TypeError(msg)
    all_digits = "".join(map(str, digit_tuple))
    digits = all_digits.rstrip("0") or "0"
    k = len(digits)
    n = len(all_digits) + exponent  # value = 0.digits * 10**n
    if k <= n <= _PLAIN_LIMIT:
        return digits + "0" * (n - k)
    if 0 < n <= _PLAIN_LIMIT:
        return f"{digits[:n]}.{digits[n:]}"
    if _SMALL_LIMIT < n <= 0:
        return f"0.{'0' * -n}{digits}"
    power = n - 1
    exp = f"e{'+' if power >= 0 else '-'}{abs(power)}"
    if k == 1:
        return digits + exp
    return f"{digits[0]}.{digits[1:]}{exp}"


def _serialize(value: Any, key: str | None) -> str:
    if value is None or isinstance(value, bool):
        return json.dumps(value)
    if isinstance(value, int | float):
        return format_number(value)
    if isinstance(value, str):
        if key in DATETIME_KEYS:
            value = normalize_datetime(value)
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ",".join(_serialize(item, None) for item in value) + "]"
    if isinstance(value, dict):
        # UTF-16 big-endian bytes compare in the order of UTF-16 code units.
        keys = sorted(value, key=lambda k: k.encode("utf-16-be"))
        members = (
            f"{json.dumps(k, ensure_ascii=False)}:{_serialize(value[k], k)}"
            for k in keys
        )
        return "{" + ",".join(members) + "}"
    msg = f"value of type {type(value).__name__} has no JSON form"
    raise TypeError(msg)


def canonicalize(text: str | bytes) -> bytes:
    """Return the canonical form of a JSON text, as UTF-8 bytes."""
    return _serialize(parse_strict(text), None).encode("utf-8")
