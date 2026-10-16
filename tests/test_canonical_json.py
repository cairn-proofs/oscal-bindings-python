"""Tests for the canonical JSON form (``tests/support/canonical_json.py``).

The unit cases copy the store's ``scripts/check-canonical-json.ts`` self-test,
so both implementations agree on the same vectors. The corpus test checks that
each expected file in the pinned corpus is its own canonical form.
"""

from __future__ import annotations

import json

import pytest
from support.canonical_json import (
    DuplicateKeyError,
    canonicalize,
    format_number,
    normalize_datetime,
)
from support.spec_artifact import corpus_root


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # RFC 8785, section 3.2.2.3 and appendix B: ECMAScript number format.
        ("1E2", "100"),
        ("-0", "0"),
        ("1e21", "1e+21"),
        ("0.0000001", "1e-7"),
        ("0.50", "0.5"),
        ("0.1", "0.1"),
        ("0.000001", "0.000001"),
        ("123456789012345680000", "123456789012345680000"),
        ("1.5e300", "1.5e+300"),
        ("-2.5e-8", "-2.5e-8"),
        ("4.35", "4.35"),
        ("9007199254740993", "9007199254740992"),
        # RFC 8785, section 3.2.3: sort by UTF-16 code units, not code points.
        (
            '{"\\ud83d\\ude00":1,"\\ufb33":2,"a":3,"B":4}',
            '{"B":4,"a":3,"\U0001f600":1,"\ufb33":2}',
        ),
        ('{"b":[3,1,2],"a":{"d":1,"c":2}}', '{"a":{"c":2,"d":1},"b":[3,1,2]}'),
        ('{ "a" : [ 1 , 2 ] }', '{"a":[1,2]}'),
        ('"\\u0041\\u000a\\u001f\\""', '"A\\n\\u001f\\""'),
        ("[true,false,null]", "[true,false,null]"),
        # canonical-json.md, Datetimes.
        (
            '{"published":"2024-01-02T03:04:05.10+00:00"}',
            '{"published":"2024-01-02T03:04:05.1Z"}',
        ),
        (
            '{"value":"2024-01-02T03:04:05.10+00:00"}',
            '{"value":"2024-01-02T03:04:05.10+00:00"}',
        ),
        ('{"end":443}', '{"end":443}'),
    ],
)
def test_canonical_form(text: str, expected: str) -> None:
    assert canonicalize(text) == expected.encode("utf-8")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2024-01-02T03:04:05+00:00", "2024-01-02T03:04:05Z"),
        ("2024-01-02T03:04:05.00000-00:00", "2024-01-02T03:04:05Z"),
        ("2024-01-02T03:04:05.120000Z", "2024-01-02T03:04:05.12Z"),
        ("2024-01-02T03:04:05.000-05:00", "2024-01-02T03:04:05-05:00"),
        ("2024-01-02T03:04:05.1234567Z", "2024-01-02T03:04:05.1234567Z"),
        ("private-cloud", "private-cloud"),
    ],
)
def test_normalize_datetime(value: str, expected: str) -> None:
    assert normalize_datetime(value) == expected


@pytest.mark.parametrize("text", ['{"a":1,"a":2}', '{"a":{"b":1,"c":{"d":1,"d":2}}}'])
def test_duplicate_key_is_rejected(text: str) -> None:
    with pytest.raises(DuplicateKeyError):
        canonicalize(text)


@pytest.mark.parametrize(
    "text", ['[{"a":1},{"a":2}]', '{"a":"a","b":"a"}', '{"a\\"b":1,"a":2}']
)
def test_repeated_names_in_other_positions_are_accepted(text: str) -> None:
    canonicalize(text)


def test_not_json_is_rejected() -> None:
    with pytest.raises(json.JSONDecodeError):
        canonicalize('{"a":')


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_non_finite_number_is_rejected(value: float) -> None:
    with pytest.raises(ValueError, match="no JSON form"):
        format_number(value)


def test_each_corpus_expected_file_is_its_own_canonical_form() -> None:
    """Task 2.2: the store's canonicalizer and this one agree on the corpus."""
    expected_files = sorted((corpus_root() / "expected").glob("*.json"))
    assert expected_files, "the corpus has no expected files"
    for path in expected_files:
        data = path.read_bytes()
        assert canonicalize(data) == data, path.name
