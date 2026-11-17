"""The four OSCAL datatypes that a pattern does not define alone.

The OSCAL schema gives the datatypes ``date-time-with-timezone``, ``uri``,
``uri-reference``, and ``email-address`` a ``format`` or an ``allOf``, not only
a ``pattern``. Codegen cannot place such a constraint in a field, and the
Pydantic types that it picks for them change the value (``AnyUrl``,
``EmailStr``) or accept too much (``AwareDatetime``, ``str``). The hoist of the
generation names each of the four definitions with ``customTypePath``, so the
models use the types of this module (design D3 of the
enforce-oscal-datatype-constraints change).

Each type checks in pydantic-core with the Rust ``regex`` engine, so a JSON
parse calls no Python function for the check. The one exception is a
``datetime`` that the caller gives in Python input (``OscalDateTimeWithTimezone``).

- ``OscalUri``: a ``str``. The input must match the pattern of the schema and be
  a URI of RFC 3986. Each scheme is valid. The value is the input text.
- ``OscalUriReference``: a ``str``. The input must be a URI reference of
  RFC 3986. The value is the input text.
- ``OscalEmailAddress``: a ``str``. The input must match the two patterns of
  the schema and be a mailbox of RFC 5321 as RFC 6531 extends it. The value is
  the input text. A U-label of a domain is a run of non-ASCII characters,
  letters, digits, and hyphens, with no hyphen at its start or end. The tables
  of IDNA2008 would need a dependency, so the type does not check them.
- ``OscalDateTimeWithTimezone``: an ``AwareDatetime``. The input must be a
  string that matches the pattern of the schema, or in Python input a
  ``datetime`` with a timezone whose serialization matches it.

The pattern literals are the output of ``translate`` of
``scripts/regex_translation.py`` for the patterns of the schema. A test reads
the pinned schema and fails when a literal drifts (design D6). The runtime
package holds no schema and no translator.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any, Final

import pydantic_core
from pydantic import AwareDatetime, GetPydanticSchema
from pydantic_core import PydanticCustomError, SchemaValidator, core_schema

if TYPE_CHECKING:
    from datetime import datetime

    from pydantic import GetCoreSchemaHandler

__all__ = [
    "OscalDateTimeWithTimezone",
    "OscalEmailAddress",
    "OscalUri",
    "OscalUriReference",
]

# --- Patterns of the schema, translated to Rust (design D6) -----------------

_DOT: Final = r"[^\n\r\u{2028}\u{2029}]"
_NOT_SPACE: Final = (
    r"[^\t\n\x0b\x0c\r \u{a0}\u{1680}\u{2000}-\u{200a}"
    r"\u{2028}\u{2029}\u{202f}\u{205f}\u{3000}\u{feff}]"
)

# `uri`: `^[a-zA-Z][a-zA-Z0-9+\-.]+:.+$`
_URI_PATTERN: Final = rf"^[a-zA-Z][a-zA-Z0-9+\-.]+:{_DOT}+$"
# `string`: `^\S(.*\S)?$`
_STRING_PATTERN: Final = rf"^{_NOT_SPACE}({_DOT}*{_NOT_SPACE})?$"
# `email-address`, second member of its `allOf`: `^.+@.+$`
_EMAIL_PATTERN: Final = rf"^{_DOT}+@{_DOT}+$"
# `date-time-with-timezone`
_DATE_TIME_PATTERN: Final = (
    r"^("
    r"((2000|2400|2800|(19|2[0-9](0[48]|[2468][048]|[13579][26])))-02-29)"
    r"|(((19|2[0-9])[0-9]{2})-02-(0[1-9]|1[0-9]|2[0-8]))"
    r"|(((19|2[0-9])[0-9]{2})-(0[13578]|10|12)-(0[1-9]|[12][0-9]|3[01]))"
    r"|(((19|2[0-9])[0-9]{2})-(0[469]|11)-(0[1-9]|[12][0-9]|30))"
    r")T(2[0-3]|[01][0-9]):([0-5][0-9]):([0-5][0-9])(\.[0-9]+)?"
    r"(Z|(-((0[0-9]|1[0-2]):00|0[39]:30)"
    r"|\+((0[0-9]|1[0-4]):00|(0[34569]|10):30|(0[58]|12):45)))$"
)

# --- RFC 3986 -----------------------------------------------------------------
# The ABNF of each rule, written as a Rust pattern. The comment of a name is the
# rule that it writes.

_HEX2 = r"%[0-9A-Fa-f]{2}"
_UNRESERVED_SUB_DELIMS = r"A-Za-z0-9\-._~!$&'()*+,;="
_PCHAR = rf"(?:[{_UNRESERVED_SUB_DELIMS}:@]|{_HEX2})"  # pchar
_SEGMENT = rf"{_PCHAR}*"  # segment
_SEGMENT_NZ = rf"{_PCHAR}+"  # segment-nz
_SEGMENT_NZ_NC = rf"(?:[{_UNRESERVED_SUB_DELIMS}@]|{_HEX2})+"  # segment-nz-nc
_PATH_ABEMPTY = rf"(?:/{_SEGMENT})*"  # path-abempty
_PATH_ABSOLUTE = rf"/(?:{_SEGMENT_NZ}(?:/{_SEGMENT})*)?"  # path-absolute
_PATH_ROOTLESS = rf"{_SEGMENT_NZ}(?:/{_SEGMENT})*"  # path-rootless
_PATH_NOSCHEME = rf"{_SEGMENT_NZ_NC}(?:/{_SEGMENT})*"  # path-noscheme
_H16 = r"[0-9A-Fa-f]{1,4}"  # h16
_DEC_OCTET = r"(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])"  # dec-octet
_IPV4 = rf"(?:{_DEC_OCTET}\.){{3}}{_DEC_OCTET}"  # IPv4address
_LS32 = rf"(?:{_H16}:{_H16}|{_IPV4})"  # ls32
_IPV6 = (  # IPv6address
    r"(?:"
    rf"(?:{_H16}:){{6}}{_LS32}"
    rf"|::(?:{_H16}:){{5}}{_LS32}"
    rf"|(?:{_H16})?::(?:{_H16}:){{4}}{_LS32}"
    rf"|(?:(?:{_H16}:){{0,1}}{_H16})?::(?:{_H16}:){{3}}{_LS32}"
    rf"|(?:(?:{_H16}:){{0,2}}{_H16})?::(?:{_H16}:){{2}}{_LS32}"
    rf"|(?:(?:{_H16}:){{0,3}}{_H16})?::{_H16}:{_LS32}"
    rf"|(?:(?:{_H16}:){{0,4}}{_H16})?::{_LS32}"
    rf"|(?:(?:{_H16}:){{0,5}}{_H16})?::{_H16}"
    r"|(?:(?:" + _H16 + r":){0,6}" + _H16 + r")?::"
    r")"
)
_IPVFUTURE = rf"v[0-9A-Fa-f]+\.[{_UNRESERVED_SUB_DELIMS}:]+"  # IPvFuture
_HOST = (  # host: IP-literal / IPv4address / reg-name
    rf"(?:\[(?:{_IPV6}|{_IPVFUTURE})\]|(?:[{_UNRESERVED_SUB_DELIMS}]|{_HEX2})*)"
)
_AUTHORITY = (  # authority
    rf"(?:(?:[{_UNRESERVED_SUB_DELIMS}:]|{_HEX2})*@)?{_HOST}(?::[0-9]*)?"
)
_QUERY_OR_FRAGMENT = rf"(?:{_PCHAR}|[/?])*"  # query, fragment
_TAIL = rf"(?:\?{_QUERY_OR_FRAGMENT})?(?:#{_QUERY_OR_FRAGMENT})?"
_SCHEME = r"[A-Za-z][A-Za-z0-9+\-.]*"  # scheme
# hier-part, with its empty alternative
_HIER_PART = rf"(?://{_AUTHORITY}{_PATH_ABEMPTY}|{_PATH_ABSOLUTE}|{_PATH_ROOTLESS}|)"
# relative-part, with its empty alternative
_RELATIVE_PART = (
    rf"(?://{_AUTHORITY}{_PATH_ABEMPTY}|{_PATH_ABSOLUTE}|{_PATH_NOSCHEME}|)"
)
_URI_GRAMMAR: Final = rf"^{_SCHEME}:{_HIER_PART}{_TAIL}$"  # URI
# URI-reference: URI / relative-ref
_URI_REFERENCE_GRAMMAR: Final = rf"^(?:{_SCHEME}:{_HIER_PART}|{_RELATIVE_PART}){_TAIL}$"

# --- RFC 5321 Mailbox with RFC 6531 --------------------------------------------

_NON_ASCII = r"\u{80}-\u{10ffff}"  # UTF8-non-ascii
_ATEXT = rf"[A-Za-z0-9!#$%&'*+\-/=?\^_`{{|}}~{_NON_ASCII}]"  # atext
_DOT_STRING = rf"{_ATEXT}+(?:\.{_ATEXT}+)*"  # Dot-string
_QUOTED_STRING = (  # Quoted-string
    rf'"(?:[\x20\x21\x23-\x5b\x5d-\x7e{_NON_ASCII}]|\\[\x20-\x7e])*"'
)
_LET_DIG = rf"[A-Za-z0-9{_NON_ASCII}]"  # Let-dig, or a character of a U-label
_SUB_DOMAIN = rf"{_LET_DIG}(?:[A-Za-z0-9\-{_NON_ASCII}]*{_LET_DIG})?"  # sub-domain
_DOMAIN = rf"{_SUB_DOMAIN}(?:\.{_SUB_DOMAIN})*"  # Domain
_ADDRESS_LITERAL = (  # address-literal
    rf"\[(?:{_IPV4}|IPv6:{_IPV6}"
    r"|[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?:[\x21-\x5a\x5e-\x7e]+)\]"
)
_MAILBOX: Final = (  # Mailbox
    rf"^(?:{_DOT_STRING}|{_QUOTED_STRING})@(?:{_DOMAIN}|{_ADDRESS_LITERAL})$"
)

# --- The types ----------------------------------------------------------------


def _chain(*patterns: str) -> core_schema.CoreSchema:
    """A schema that matches the whole input against each pattern, in order."""
    return core_schema.chain_schema(
        [core_schema.str_schema(pattern=pattern) for pattern in patterns]
    )


def _string_type(*patterns: str) -> GetPydanticSchema:
    def get_schema(_source: Any, _handler: GetCoreSchemaHandler) -> Any:
        return _chain(*patterns)

    return GetPydanticSchema(get_schema)


OscalUri = Annotated[str, _string_type(_URI_PATTERN, _URI_GRAMMAR)]
"""The datatype ``uri``: the pattern of the schema, then RFC 3986 ``URI``."""

OscalUriReference = Annotated[str, _string_type(_URI_REFERENCE_GRAMMAR)]
"""The datatype ``uri-reference``: RFC 3986 ``URI-reference``."""

OscalEmailAddress = Annotated[
    str, _string_type(_STRING_PATTERN, _EMAIL_PATTERN, _MAILBOX)
]
"""The datatype ``email-address``: the two patterns of the schema, then ``Mailbox``."""

_DATE_TIME_ERROR_TYPE: Final = "oscal_date_time_with_timezone"
_DATE_TIME_ERROR_MESSAGE: Final = (
    "Input should be a date-time with a timezone that matches the OSCAL pattern"
)
_DATE_TIME_TEXT: Final = SchemaValidator(
    core_schema.str_schema(pattern=_DATE_TIME_PATTERN)
)


def _check_serialization(value: datetime) -> datetime:
    """Match the text that a serialization writes with the pattern of the schema."""
    text = pydantic_core.to_json(value).decode()[1:-1]
    try:
        _DATE_TIME_TEXT.validate_python(text)
    except pydantic_core.ValidationError as error:
        raise PydanticCustomError(
            _DATE_TIME_ERROR_TYPE, _DATE_TIME_ERROR_MESSAGE
        ) from error
    return value


def _date_time_schema(_source: Any, _handler: GetCoreSchemaHandler) -> Any:
    # JSON input: the string must match the pattern, then it is a datetime.
    from_text = core_schema.chain_schema(
        [
            core_schema.str_schema(pattern=_DATE_TIME_PATTERN),
            core_schema.datetime_schema(tz_constraint="aware"),
        ]
    )
    # Python input: the same chain, or a datetime instance (never a number)
    # whose serialization matches the pattern. The union gives one error at the
    # field, not one for each member.
    from_datetime = core_schema.no_info_after_validator_function(
        _check_serialization,
        core_schema.datetime_schema(strict=True, tz_constraint="aware"),
    )
    return core_schema.json_or_python_schema(
        json_schema=from_text,
        python_schema=core_schema.union_schema(
            [from_text, from_datetime],
            custom_error_type=_DATE_TIME_ERROR_TYPE,
            custom_error_message=_DATE_TIME_ERROR_MESSAGE,
        ),
    )


OscalDateTimeWithTimezone = Annotated[
    AwareDatetime, GetPydanticSchema(_date_time_schema)
]
"""The datatype ``date-time-with-timezone``: a ``datetime`` that has a timezone."""
