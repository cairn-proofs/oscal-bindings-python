"""Tests for ``scripts/regex_translation.py`` (PRS-007).

``translate`` maps a pattern of the OSCAL schema, written for ECMA-262 with the
``u`` flag, to the Rust ``regex`` dialect of pydantic-core. The tests check each
of the 10 patterns of the pinned schema against a table of expected results, and
that each construct that the mapping does not know is an error.

The expected results in ``PROBES`` are the results of ECMA-262: a ``RegExp``
with the ``u`` flag in Node.js gave them, and the comments say why. The
untranslated pattern gives a different result in pydantic for the probes that
``test_untranslated_patterns_differ`` lists.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

import pytest
from pydantic import Field, TypeAdapter, ValidationError
from support.scripts import load_script
from support.spec_artifact import ensure_spec_artifact

translation = load_script("regex_translation")
pin = load_script("spec_artifact")

RegexTranslationError = translation.RegexTranslationError
translate = translation.translate

LF, CR, NEL, LS, PS = "\n", "\r", "\u0085", "\u2028", "\u2029"
NBSP, BOM = "\u00a0", "\ufeff"
UUID = "0c6b8f1e-4a2d-4b7e-9c3f-5d6e7f8a9b0c"

# Definition key of the schema -> (probe, ECMA-262 result).
PROBES: dict[str, list[tuple[str, bool]]] = {
    "Base64Datatype": [("AA==", True), ("AAA===", False), ("", False)],
    "DateDatatype": [
        ("2024-01-02", True),
        ("2024-01-02Z", True),
        ("2024-02-30", False),
        ("2024-01-02+05:17", False),
    ],
    "DateTimeWithTimezoneDatatype": [
        ("2024-01-02T03:04:05Z", True),
        ("2024-01-02T03:04:05.5-05:00", True),
        ("1850-01-01T00:00:00Z", False),
        ("2024-01-02T03:04:05z", False),
        ("2024-01-02T03:04:05+05:17", False),
    ],
    "DecimalDatatype": [
        ("0.5", True),
        (".5", True),
        ("5.", True),
        ("1e3", False),
        (f"0.5{LF}", False),
    ],
    # `.` matches no line terminator.
    "EmailAddressDatatype": [
        ("a@b", True),
        (f"a{CR}@b", False),
        (f"a@b{PS}", False),
        (f"a{NEL}@b", True),
    ],
    # Only LF is excluded.
    "MarkupLineDatatype": [
        (f"a{CR}b", True),
        (f"a{LS}b", True),
        (f"a{LF}b", False),
        ("", False),
    ],
    # `.` excludes CR, U+2028, U+2029. `\s` has U+FEFF and no U+0085.
    "StringDatatype": [
        ("ab", True),
        ("a b", True),
        (f"a{CR}b", False),
        (f"a{LS}b", False),
        (f"a{PS}b", False),
        (f"a{LF}b", False),
        (f"{NEL}a", True),
        (f"{BOM}a", False),
        (f"a{BOM}", False),
        (f"{NBSP}a", False),
    ],
    "TokenDatatype": [
        ("é1", True),
        ("_a", True),
        ("ǅ", True),
        ("1a", False),
        (f"a{LF}", False),
    ],
    "URIDatatype": [
        ("ab:c", True),
        ("a:b", False),
        (f"ab:c{CR}d", False),
        (f"ab:{LS}", False),
    ],
    "UUIDDatatype": [
        (UUID, True),
        (UUID.replace("-4b7e", "-3b7e"), False),
        (f"{UUID}{LF}", False),
    ],
}


@pytest.fixture(scope="module")
def schema_patterns() -> dict[str, str]:
    """Definition key -> the pattern of the pinned schema."""
    paths = pin.artifact_paths(ensure_spec_artifact())
    definitions = json.loads(paths.schema.read_bytes())["definitions"]
    found: dict[str, str] = {}
    for key, definition in definitions.items():
        for node in [definition, *definition.get("allOf", [])]:
            if "pattern" in node:
                found[key] = node["pattern"]
    return found


def _accepts(pattern: str, value: str) -> bool:
    try:
        TypeAdapter(Annotated[str, Field(pattern=pattern)]).validate_python(value)
    except ValidationError:
        return False
    return True


def _cases() -> list[Any]:
    return [
        pytest.param(key, value, expected, id=f"{key}-{value!r}")
        for key, probes in PROBES.items()
        for value, expected in probes
    ]


def test_the_table_has_each_pattern_of_the_schema(
    schema_patterns: dict[str, str],
) -> None:
    """A new pattern in a moved pin fails here until a row covers it."""
    assert set(schema_patterns) == set(PROBES)
    assert len(schema_patterns) == 10


@pytest.mark.parametrize(("key", "value", "expected"), _cases())
def test_translated_pattern_gives_the_ecma_262_result(
    schema_patterns: dict[str, str], key: str, value: str, *, expected: bool
) -> None:
    assert _accepts(translate(schema_patterns[key]), value) is expected


def test_untranslated_patterns_differ(schema_patterns: dict[str, str]) -> None:
    """The probes show the gap: pydantic reads each pattern as Rust, as written."""
    differ = {
        (key, value)
        for key, probes in PROBES.items()
        for value, expected in probes
        if _accepts(schema_patterns[key], value) is not expected
    }
    assert differ == {
        ("EmailAddressDatatype", f"a{CR}@b"),
        ("EmailAddressDatatype", f"a@b{PS}"),
        ("StringDatatype", f"a{CR}b"),
        ("StringDatatype", f"a{LS}b"),
        ("StringDatatype", f"a{PS}b"),
        ("StringDatatype", f"{NEL}a"),
        ("StringDatatype", f"{BOM}a"),
        ("StringDatatype", f"a{BOM}"),
        ("URIDatatype", f"ab:c{CR}d"),
        ("URIDatatype", f"ab:{LS}"),
    }


# --- D2 item 3: the tokens that stay ---------------------------------------


@pytest.mark.parametrize(
    "pattern",
    [
        "^a$",
        "^[a-zA-Z0-9+\\-.]+$",
        "^[^<]+$",
        "^(a|b)*$",
        "^(?:a|b){2,3}$",
        "^a{0,2}$",
        "^\\p{L}\\P{N}[\\p{L}_]$",
        "^\\.\\+\\(\\)\\[\\]\\{\\}\\|\\\\\\/$",
        "^a+?b*?c??$",
        "^\\x0b\\u00a0\\u{2028}[\\u{2000}-\\u{200a}\\x41]$",
    ],
)
def test_a_token_that_both_dialects_read_alike_stays(pattern: str) -> None:
    assert translate(pattern) == pattern


def test_translation_is_its_own_fixed_point(schema_patterns: dict[str, str]) -> None:
    """The post-processor can run on its own output without a second translation."""
    for pattern in schema_patterns.values():
        once = translate(pattern)
        assert translate(once) == once


def test_a_literal_line_feed_is_written_as_an_escape() -> None:
    assert translate("^[^\n]+$") == "^[^\\n]+$"


def test_dot_excludes_the_line_terminators() -> None:
    assert translate(".") == "[^\\n\\r\\u{2028}\\u{2029}]"


def test_space_class_and_its_complement() -> None:
    space, not_space = translate("\\s"), translate("\\S")
    assert not_space == "[^" + space[1:]
    for terminator in (LF, CR, LS, PS, BOM, NBSP, "\t", " ", "\u3000", "\u2009"):
        assert _accepts(f"^{space}$", terminator)
    for member in (NEL, "a", "\u180e", "\u200b"):
        assert not _accepts(f"^{space}$", member)


# --- D2 item 4: each other construct is an error ----------------------------


@pytest.mark.parametrize(
    "pattern",
    [
        "(?=a)b",
        "(?!a)b",
        "(?<=a)b",
        "(?<!a)b",
        "(a)\\1",
        "(?<n>a)\\k<n>",
        "\\d",
        "\\D",
        "\\w",
        "\\W",
        "\\b",
        "\\B",
        "[\\s]",
        "[^\\S]",
        "(?i)a",
        "(?<n>a)",
    ],
)
@pytest.mark.spec("PRS-007.02")
def test_an_unknown_construct_is_an_error_that_names_the_pattern(
    pattern: str,
) -> None:
    with pytest.raises(RegexTranslationError) as info:
        translate(pattern)
    assert repr(pattern) in str(info.value)
    assert info.value.pattern == pattern


@pytest.mark.parametrize(
    "pattern",
    ["a\\", "[a", "(a", "a)", "a]", "a}", "a{", "a{x}", "[]", "[a[b]]", "\\q", "\\p"],
)
def test_a_pattern_that_is_not_well_formed_is_an_error(pattern: str) -> None:
    with pytest.raises(RegexTranslationError):
        translate(pattern)
