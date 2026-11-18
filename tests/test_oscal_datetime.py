"""Tests for `OscalDateTime`, the ``datetime`` that keeps every fraction digit (#19)."""

from __future__ import annotations

import copy
import json
import pickle
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import TypeAdapter, ValidationError

import oscal_bindings
from oscal_bindings import OscalDateTime, parse_oscal, serialize_oscal
from oscal_bindings.v1 import models
from oscal_bindings.v1._datatypes import OscalDateTimeWithTimezone

ADAPTER: TypeAdapter[Any] = TypeAdapter(OscalDateTimeWithTimezone)
UUID = "74c8ba1e-5cd4-4ad1-bbfd-d888e2f6c724"


def _parse(text: str) -> OscalDateTime:
    value = ADAPTER.validate_json(json.dumps(text))
    assert isinstance(value, OscalDateTime)
    return value


def _catalog(last_modified: str) -> str:
    return json.dumps(
        {
            "catalog": {
                "uuid": UUID,
                "metadata": {
                    "title": "t",
                    "version": "1",
                    "oscal-version": "1.2.3",
                    "last-modified": last_modified,
                },
            }
        }
    )


class TestDigits:
    @pytest.mark.parametrize(
        "text",
        [
            "2024-01-02T03:04:05Z",
            "2024-01-02T03:04:05.1Z",
            "2024-01-02T03:04:05.120Z",
            "2024-01-02T03:04:05.123456Z",
            "2024-01-02T03:04:05.1234567Z",
            "2024-01-02T03:04:05.0000001+01:00",
            "2024-01-02T03:04:05.123456789012345678901234567890-05:00",
        ],
    )
    def test_the_text_survives_a_round_trip(self, text: str) -> None:
        doc = parse_oscal(_catalog(text))
        written = json.loads(serialize_oscal(doc))["catalog"]["metadata"]
        assert written["last-modified"] == text

    def test_the_value_is_a_datetime(self) -> None:
        value = _parse("2024-01-02T03:04:05.1234567Z")
        assert isinstance(value, datetime)
        assert value.microsecond == 123456
        assert value.fraction == "1234567"

    def test_a_field_holds_an_oscal_datetime(self) -> None:
        doc = parse_oscal(_catalog("2024-01-02T03:04:05.1234567Z"))
        last = doc.root.catalog.metadata.last_modified  # type: ignore[union-attr]
        assert isinstance(last, OscalDateTime)

    @given(
        digits=st.text("0123456789", min_size=0, max_size=40),
        zone=st.sampled_from(["Z", "+01:00", "-05:00", "+05:45"]),
    )
    def test_any_digit_string_round_trips(self, digits: str, zone: str) -> None:
        text = "2024-01-02T03:04:05" + ("." + digits if digits else "") + zone
        assert ADAPTER.dump_python(_parse(text), mode="json") == text
        assert json.loads(ADAPTER.dump_json(_parse(text))) == text

    def test_python_mode_dump_keeps_the_object(self) -> None:
        value = _parse("2024-01-02T03:04:05.1234567Z")
        assert ADAPTER.dump_python(value).fraction == "1234567"

    def test_a_plain_datetime_writes_its_microseconds(self) -> None:
        value = ADAPTER.validate_python(
            datetime(2024, 1, 2, 3, 4, 5, 120000, tzinfo=UTC)
        )
        assert isinstance(value, OscalDateTime)
        assert ADAPTER.dump_python(value, mode="json") == "2024-01-02T03:04:05.120000Z"
        whole = ADAPTER.validate_python(datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC))
        assert ADAPTER.dump_python(whole, mode="json") == "2024-01-02T03:04:05Z"

    def test_a_plain_datetime_set_without_validation_still_serializes(self) -> None:
        meta = models.Metadata.model_construct(
            last_modified=datetime(2024, 1, 2, 3, 4, 5, 7, tzinfo=UTC)
        )
        assert '"last-modified":"2024-01-02T03:04:05.000007Z"' in meta.model_dump_json()

    def test_a_datetime_without_a_timezone_is_still_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ADAPTER.validate_python(datetime(2024, 1, 2, 3, 4, 5))  # noqa: DTZ001

    def test_a_fraction_that_disagrees_with_the_microsecond_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="does not start with"):
            OscalDateTime(2024, 1, 2, 3, 4, 5, 1, tzinfo=UTC, fraction="2")
        with pytest.raises(ValueError, match="run of digits"):
            OscalDateTime(2024, 1, 2, 3, 4, 5, 0, tzinfo=UTC, fraction="1e")

    def test_a_constructed_value_writes_its_microseconds(self) -> None:
        value = OscalDateTime(2024, 1, 2, 3, 4, 5, 120000, tzinfo=UTC)
        assert value.fraction == "120000"
        assert value.to_string() == "2024-01-02T03:04:05.120000Z"


class TestEqualityAndOrder:
    def test_digits_beyond_the_sixth_count(self) -> None:
        a = _parse("2024-01-02T03:04:05.1234567Z")
        b = _parse("2024-01-02T03:04:05.1234568Z")
        assert a != b
        assert a < b
        assert b > a
        assert a <= b
        assert b >= a
        assert not a >= b
        assert not b <= a

    def test_a_trailing_zero_is_not_a_difference(self) -> None:
        assert _parse("2024-01-02T03:04:05.120Z") == _parse("2024-01-02T03:04:05.12Z")
        assert _parse("2024-01-02T03:04:05.12000009Z") == _parse(
            "2024-01-02T03:04:05.120000090Z"
        )

    def test_the_same_instant_in_two_offsets_is_equal(self) -> None:
        a = _parse("2024-01-02T03:04:05.1234567Z")
        b = _parse("2024-01-02T04:04:05.1234567+01:00")
        assert a == b
        assert hash(a) == hash(b)

    def test_a_plain_datetime_counts_as_having_no_extra_digits(self) -> None:
        plain = datetime(2024, 1, 2, 3, 4, 5, 123456, tzinfo=UTC)
        assert _parse("2024-01-02T03:04:05.123456Z") == plain
        assert plain == _parse("2024-01-02T03:04:05.123456Z")
        assert hash(_parse("2024-01-02T03:04:05.123456Z")) == hash(plain)
        longer = _parse("2024-01-02T03:04:05.1234567Z")
        assert longer != plain
        assert plain != longer
        assert longer > plain
        assert plain < longer

    def test_equal_values_hash_alike(self) -> None:
        a = _parse("2024-01-02T03:04:05.1234567Z")
        b = _parse("2024-01-02T03:04:05.12345670Z")
        assert a == b
        assert hash(a) == hash(b)
        assert len({a, b}) == 1

    def test_values_sort_by_every_digit(self) -> None:
        texts = [
            "2024-01-02T03:04:05.1234569Z",
            "2024-01-02T03:04:05.1234567Z",
            "2024-01-02T03:04:05.123456Z",
            "2024-01-02T03:04:05.1234568Z",
        ]
        ordered = sorted(_parse(t) for t in texts)
        assert [v.fraction for v in ordered] == [
            "123456",
            "1234567",
            "1234568",
            "1234569",
        ]

    def test_something_that_is_not_a_datetime_is_not_equal(self) -> None:
        value = _parse("2024-01-02T03:04:05Z")
        assert value != "2024-01-02T03:04:05Z"
        assert (value == 1) is False
        with pytest.raises(TypeError):
            value < 1  # type: ignore[operator]  # noqa: B015

    @given(
        a=st.text("0123456789", max_size=12),
        b=st.text("0123456789", max_size=12),
    )
    def test_order_agrees_with_the_value_of_the_digits(self, a: str, b: str) -> None:
        def value(digits: str) -> Any:
            return _parse(
                "2024-01-02T03:04:05" + ("." + digits if digits else "") + "Z"
            )

        width = max(len(a), len(b), 1)
        x, y = int(a.ljust(width, "0") or 0), int(b.ljust(width, "0") or 0)
        assert (value(a) == value(b)) is (x == y)
        assert (value(a) < value(b)) is (x < y)
        assert (value(a) >= value(b)) is (x >= y)


class TestArithmetic:
    """The behaviours that the class docstring documents."""

    def test_adding_a_timedelta_keeps_the_extra_digits(self) -> None:
        value = _parse("2024-01-02T03:04:05.1234567Z")
        later = value + timedelta(seconds=1, microseconds=1)
        assert later.fraction == "1234577"
        assert later.to_string() == "2024-01-02T03:04:06.1234577Z"
        assert (timedelta(seconds=1) + value).fraction == "1234567"

    def test_subtracting_a_timedelta_keeps_the_extra_digits(self) -> None:
        value = _parse("2024-01-02T03:04:05.1234567Z")
        assert (value - timedelta(microseconds=123456)).fraction == "0000007"

    def test_a_carry_across_the_second_keeps_the_extra_digits(self) -> None:
        value = _parse("2024-01-02T03:04:05.9999999Z")
        later = value + timedelta(microseconds=1)
        assert later.to_string() == "2024-01-02T03:04:06.0000009Z"

    def test_a_value_with_no_extra_digits_stays_plain(self) -> None:
        value = _parse("2024-01-02T03:04:05.12Z")
        assert (value + timedelta(seconds=1)).fraction == "120000"

    def test_a_difference_is_a_timedelta_of_microseconds(self) -> None:
        a = _parse("2024-01-02T03:04:05.1234567Z")
        b = _parse("2024-01-02T03:04:05.1234568Z")
        assert b - a == timedelta(0)  # the documented limit
        assert a != b  # compare, do not subtract

    def test_replace_keeps_the_digits_unless_it_sets_the_microsecond(self) -> None:
        value = _parse("2024-01-02T03:04:05.1234567Z")
        assert value.replace(hour=9).fraction == "1234567"
        assert value.replace(tzinfo=timezone(timedelta(hours=2))).fraction == "1234567"
        assert value.replace(microsecond=5).fraction == "000005"
        assert value.replace(1999, 1, 1, 1, 1, 1, 7).fraction == "000007"

    def test_astimezone_keeps_the_digits(self) -> None:
        value = _parse("2024-01-02T03:04:05.1234567Z")
        moved = value.astimezone(timezone(timedelta(hours=5, minutes=30)))
        assert moved.to_string() == "2024-01-02T08:34:05.1234567+05:30"
        assert moved == value

    def test_the_standard_methods_use_the_microsecond_value(self) -> None:
        value = _parse("2024-01-02T03:04:05.1234567Z")
        assert value.isoformat(timespec="microseconds").endswith(".123456+00:00")
        assert value.isoformat(timespec="milliseconds").endswith(".123+00:00")
        assert (
            value.timestamp()
            == datetime(2024, 1, 2, 3, 4, 5, 123456, tzinfo=UTC).timestamp()
        )
        assert value.strftime("%f") == "123456"

    def test_isoformat_writes_every_digit(self) -> None:
        value = _parse("2024-01-02T03:04:05.1234567+01:00")
        assert value.isoformat() == "2024-01-02T03:04:05.1234567+01:00"
        assert value.isoformat(" ") == "2024-01-02 03:04:05.1234567+01:00"
        assert str(value) == "2024-01-02 03:04:05.1234567+01:00"

    def test_fromisoformat_keeps_the_digits(self) -> None:
        value = OscalDateTime.fromisoformat("2024-01-02T03:04:05.1234567+00:00")
        assert value.fraction == "1234567"
        whole = OscalDateTime.fromisoformat("2024-01-02T03:04:05+00:00")
        assert whole.fraction == ""

    def test_repr_shows_the_extra_digits_only_when_there_are_some(self) -> None:
        assert "fraction='1234567'" in repr(_parse("2024-01-02T03:04:05.1234567Z"))
        assert "fraction" not in repr(_parse("2024-01-02T03:04:05.123456Z"))

    def test_a_copy_and_a_pickle_keep_the_digits(self) -> None:
        value = _parse("2024-01-02T03:04:05.1234567+01:00")
        for clone in (
            copy.copy(value),
            copy.deepcopy(value),
            pickle.loads(pickle.dumps(value)),  # noqa: S301
        ):
            assert clone == value
            assert clone.fraction == "1234567"
            assert clone.utcoffset() == timedelta(hours=1)

    def test_a_naive_value_pickles(self) -> None:
        value = OscalDateTime(2024, 1, 2, 3, 4, 5, 6)
        clone = pickle.loads(pickle.dumps(value))  # noqa: S301
        assert clone == value
        assert clone.tzinfo is None


class TestDocumentation:
    """The limits of the arithmetic show in the API documentation."""

    def test_the_class_docstring_states_the_arithmetic_limits(self) -> None:
        doc = OscalDateTime.__doc__ or ""
        assert "Arithmetic and precision" in doc
        assert "value - other" in doc
        assert "timedelta" in doc
        assert "timestamp()" in doc
        assert "microsecond" in doc

    def test_the_class_is_public(self) -> None:
        assert "OscalDateTime" in oscal_bindings.__all__
        assert oscal_bindings.OscalDateTime is OscalDateTime

    def test_the_serialization_schema_is_a_date_time_string(self) -> None:
        schema = ADAPTER.json_schema(mode="serialization")
        assert schema == {"type": "string", "format": "date-time"}
        assert ADAPTER.json_schema(mode="validation")["type"] == "string"
