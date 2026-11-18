"""Tests for ``oscal_bindings.v1._datatypes``: the four hand-written datatypes.

Each test uses a ``TypeAdapter`` of one type, with JSON input and with Python
input. The values come from the scenarios of the spec delta of the
enforce-oscal-datatype-constraints change. The drift test (design D6) compares
each pattern literal of the module with ``translate`` of the pinned schema.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError
from support.scripts import load_script
from support.spec_artifact import ensure_spec_artifact

from oscal_bindings.v1 import _datatypes
from oscal_bindings.v1._datatypes import (
    OscalDateTimeWithTimezone,
    OscalEmailAddress,
    OscalUri,
    OscalUriReference,
)

pin = load_script("spec_artifact")
translate = load_script("regex_translation").translate

CR, LF, LS = "\r", "\n", "\u2028"
DATE_TIME_ERROR_TYPE = "oscal_date_time_with_timezone"

URI_CASES = [
    ("http://a", True),
    ("https://example.com/a/../b", True),
    ("https://example.com/ns#x", True),
    ("http://[::1]:8080/x?q=1#f", True),
    ("urn:ietf:rfc:3986", True),
    ("javascript:alert(1)", True),
    ("file:///etc/passwd", True),
    (f"http://a{CR}{LF}b", False),
    ("https://x.org/a b", False),
    ("x://", False),
    ("a:b", False),
    ("ab:", False),
    ("http://a/%zz", False),
    ("http://a/é", False),
    (f"ab:c{LS}", False),
]

URI_REFERENCE_CASES = [
    ("#ac-1", True),
    ("../a.json", True),
    ("https://example.com/x", True),
    ("a:b", True),
    ("//host/path?q#f", True),
    ("a b", False),
    (f"a{LF}b", False),
    (f"a{CR}b", False),
    ("%zz", False),
    ("a#b#c", False),
]

EMAIL_CASES = [
    ("a@b", True),
    ("x@localhost", True),
    ("ü@例え.jp", True),
    ("A@Example.COM", True),
    ('"a b"@example.com', True),
    ("a@[192.0.2.1]", True),
    ("a@[IPv6:2001:db8::1]", True),
    ("Name <a@example.com>", False),
    ("a@@b", False),
    ("\u00a0a@example.com", False),
    ("a..b@example.com", False),
    ("a@example-", False),
    ("a@-example", False),
    ("a@", False),
    ("@a", False),
    (f"a{CR}@b", False),
]


def _accepts_json(adapter: TypeAdapter[Any], value: Any) -> bool:
    try:
        adapter.validate_json(json.dumps(value))
    except ValidationError:
        return False
    return True


def _accepts_python(adapter: TypeAdapter[Any], value: Any) -> bool:
    try:
        adapter.validate_python(value)
    except ValidationError:
        return False
    return True


@pytest.mark.parametrize(
    ("datatype", "cases"),
    [
        pytest.param(OscalUri, URI_CASES, id="uri"),
        pytest.param(OscalUriReference, URI_REFERENCE_CASES, id="uri-reference"),
        pytest.param(OscalEmailAddress, EMAIL_CASES, id="email-address"),
    ],
)
class TestStringDatatypes:
    def test_json_input(self, datatype: Any, cases: list[tuple[str, bool]]) -> None:
        adapter = TypeAdapter(datatype)
        assert {v: _accepts_json(adapter, v) for v, _ in cases} == dict(cases)

    def test_python_input(self, datatype: Any, cases: list[tuple[str, bool]]) -> None:
        adapter = TypeAdapter(datatype)
        assert {v: _accepts_python(adapter, v) for v, _ in cases} == dict(cases)

    def test_an_accepted_value_serializes_to_the_input_text(
        self, datatype: Any, cases: list[tuple[str, bool]]
    ) -> None:
        adapter = TypeAdapter(datatype)
        for value in (v for v, accepted in cases if accepted):
            assert adapter.validate_json(json.dumps(value)) == value
            assert adapter.dump_python(adapter.validate_python(value)) == value
            assert (
                adapter.dump_json(value)
                == json.dumps(value, ensure_ascii=False).encode()
            )

    def test_a_number_and_a_null_are_rejected(
        self, datatype: Any, cases: list[tuple[str, bool]]
    ) -> None:
        del cases
        adapter = TypeAdapter(datatype)
        for value in (1700000000, None, True, ["a:b"]):
            assert not _accepts_python(adapter, value)
            assert not _accepts_json(adapter, value)


# --- date-time-with-timezone ------------------------------------------------

DATE_TIME_TEXT_CASES = [
    ("2024-01-02T03:04:05Z", True),
    ("2024-01-02T03:04:05.123-05:00", True),
    ("2024-01-02T03:04:05.1234567Z", True),
    ("2024-02-29T00:00:00+05:45", True),
    ("1850-01-01T00:00:00Z", False),
    ("2024-01-02T03:04:05+05:17", False),
    ("2024-01-02T03:04:05z", False),
    ("2024-01-02 03:04:05Z", False),
    ("2024-01-02T03:04Z", False),
    ("2024-01-02T03:04:05", False),
    ("2023-02-29T00:00:00Z", False),
    ("1700000000", False),
    ("", False),
]

DATE_TIME_ADAPTER = TypeAdapter(OscalDateTimeWithTimezone)


class TestDateTimeWithTimezone:
    @pytest.mark.parametrize(("text", "accepted"), DATE_TIME_TEXT_CASES)
    def test_text_in_json_input(self, text: str, *, accepted: bool) -> None:
        assert _accepts_json(DATE_TIME_ADAPTER, text) is accepted

    @pytest.mark.parametrize(("text", "accepted"), DATE_TIME_TEXT_CASES)
    def test_text_in_python_input(self, text: str, *, accepted: bool) -> None:
        assert _accepts_python(DATE_TIME_ADAPTER, text) is accepted

    def test_a_json_number_is_rejected(self) -> None:
        assert not _accepts_json(DATE_TIME_ADAPTER, 1700000000)
        with pytest.raises(ValidationError) as info:
            DATE_TIME_ADAPTER.validate_json("1700000000")
        assert [e["loc"] for e in info.value.errors()] == [()]

    def test_the_value_is_a_datetime_that_keeps_its_offset(self) -> None:
        value = DATE_TIME_ADAPTER.validate_json('"2024-01-02T03:04:05.5-05:00"')
        assert value == datetime(
            2024, 1, 2, 3, 4, 5, 500000, tzinfo=timezone(timedelta(hours=-5))
        )
        assert DATE_TIME_ADAPTER.dump_python(value, mode="json") == (
            "2024-01-02T03:04:05.5-05:00"
        )

    def test_an_aware_datetime_in_python_input_is_accepted(self) -> None:
        value = datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC)
        assert DATE_TIME_ADAPTER.validate_python(value) == value

    def test_an_int_in_python_input_fails(self) -> None:
        assert not _accepts_python(DATE_TIME_ADAPTER, 1700000000)

    def test_a_naive_datetime_in_python_input_fails(self) -> None:
        assert not _accepts_python(DATE_TIME_ADAPTER, datetime(2024, 1, 2, 3, 4, 5))  # noqa: DTZ001

    @pytest.mark.parametrize(
        "value",
        [
            datetime(1850, 1, 1, tzinfo=UTC),
            datetime(
                2024, 1, 2, 3, 4, 5, tzinfo=timezone(timedelta(hours=5, minutes=17))
            ),
            datetime(2024, 1, 2, 3, 4, 5, tzinfo=None),  # noqa: DTZ001
            1700000000,
        ],
        ids=["year-1850", "offset-+05:17", "naive", "number"],
    )
    def test_a_rejected_python_value_gives_one_error_of_the_datatype(
        self, value: Any
    ) -> None:
        with pytest.raises(ValidationError) as info:
            DATE_TIME_ADAPTER.validate_python(value)
        errors = info.value.errors()
        assert [(e["loc"], e["type"]) for e in errors] == [((), DATE_TIME_ERROR_TYPE)]
        # The message states the constraint, not the type of the input.
        assert "pattern" in errors[0]["msg"]
        assert errors[0]["type"] not in {"json_invalid", "oscal_document_type"}


# --- Drift of the pattern literals (design D6) ---------------------------------


@pytest.fixture(scope="module")
def schema_definitions() -> dict[str, Any]:
    paths = pin.artifact_paths(ensure_spec_artifact())
    definitions: dict[str, Any] = json.loads(paths.schema.read_bytes())["definitions"]
    return definitions


def test_each_pattern_literal_is_the_translation_of_its_schema_pattern(
    schema_definitions: dict[str, Any],
) -> None:
    uri = schema_definitions["URIDatatype"]
    email = schema_definitions["EmailAddressDatatype"]["allOf"]
    string = schema_definitions["StringDatatype"]
    date_time = schema_definitions["DateTimeWithTimezoneDatatype"]
    assert email[0] == {"$ref": "#/definitions/StringDatatype"}
    literals = {
        "_URI_PATTERN": _datatypes._URI_PATTERN,  # noqa: SLF001
        "_STRING_PATTERN": _datatypes._STRING_PATTERN,  # noqa: SLF001
        "_EMAIL_PATTERN": _datatypes._EMAIL_PATTERN,  # noqa: SLF001
        "_DATE_TIME_PATTERN": _datatypes._DATE_TIME_PATTERN,  # noqa: SLF001
    }
    assert literals == {
        "_URI_PATTERN": translate(uri["pattern"]),
        "_STRING_PATTERN": translate(string["pattern"]),
        "_EMAIL_PATTERN": translate(email[1]["pattern"]),
        "_DATE_TIME_PATTERN": translate(date_time["pattern"]),
    }
