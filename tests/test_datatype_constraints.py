"""Scenarios of the datatype-constraints spec delta.

One test for each scenario of
``openspec/changes/enforce-oscal-datatype-constraints/specs/datatype-constraints/spec.md``.
Each test reads like its scenario: a document, a parse or a call, and the
accept or reject result. A document is built as a dict and sent as JSON, so
control characters travel as escapes.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from oscal_bindings import (
    OscalBuilderError,
    OscalParseError,
    make_resource,
    parse_oscal,
    serialize_oscal,
    validate_element,
)
from oscal_bindings.models import BackMatterResource, DocumentId, Metadata

CR = "\r"
LF = "\n"
LINE_SEPARATOR = "\u2028"
NBSP = "\u00a0"
BAD_UUID = "not a uuid"
UUID = "2f6e5c2a-6b0e-4b8e-9a3e-1c7d0b5f4a10"
OTHER_UUID = "0c6b8f1e-4a2d-4b7e-9c3f-5d6e7f8a9b0c"


def _metadata(**extra: Any) -> dict[str, Any]:
    return {
        "title": "T",
        "last-modified": "2024-01-02T03:04:05Z",
        "version": "1.0",
        "oscal-version": "1.2.3",
        **extra,
    }


def _catalog(metadata: dict[str, Any] | None = None, **body: Any) -> dict[str, Any]:
    return {"catalog": {"uuid": UUID, "metadata": metadata or _metadata(), **body}}


def _with_prop(**prop: Any) -> dict[str, Any]:
    return _catalog(_metadata(props=[{"name": "n", "value": "v", **prop}]))


def _with_link(href: str) -> dict[str, Any]:
    return _catalog(_metadata(links=[{"href": href}]))


def _with_email(address: str) -> dict[str, Any]:
    party = {"uuid": OTHER_UUID, "type": "person", "email-addresses": [address]}
    return _catalog(_metadata(parties=[party]))


def _with_last_modified(value: Any) -> dict[str, Any]:
    return _catalog(_metadata(**{"last-modified": value}))


def _parse(document: dict[str, Any]) -> Any:
    return parse_oscal(json.dumps(document))


def _assert_rejected(document: dict[str, Any], key: str) -> None:
    """Parsing reports a parse error whose location names ``key``."""
    with pytest.raises(OscalParseError) as info:
        _parse(document)
    assert info.value.errors
    assert any(key in error["loc"] for error in info.value.errors), info.value.errors


def _round_trip(document: dict[str, Any]) -> dict[str, Any]:
    return json.loads(serialize_oscal(_parse(document)))


# --- Each string pattern of the schema constrains its field -----------------


def test_empty_document_identifier_is_rejected() -> None:
    document = _catalog(_metadata(**{"document-ids": [{"identifier": ""}]}))
    _assert_rejected(document, "identifier")


def test_malformed_uuid_is_rejected() -> None:
    document = _catalog(**{"back-matter": {"resources": [{"uuid": BAD_UUID}]}})
    _assert_rejected(document, "uuid")


def test_both_patterns_of_an_all_of_apply() -> None:
    _assert_rejected(_with_email(f"{NBSP}a@example.com"), "email-addresses")


# --- A pattern matches as ECMA-262 matches it -------------------------------


def test_carriage_return_inside_a_string_is_rejected() -> None:
    _assert_rejected(_with_prop(value=f"a{CR}b"), "value")


def test_line_separator_inside_a_string_is_rejected() -> None:
    _assert_rejected(_with_prop(value=f"a{LINE_SEPARATOR}b"), "value")


def test_carriage_return_inside_a_markup_line_is_accepted() -> None:
    _parse(_catalog(_metadata(title=f"a{CR}b")))


def test_unicode_letter_matches_a_letter_class() -> None:
    _parse(_with_prop(name="é1"))


# --- The generation fails on a pattern that it cannot place -----------------


def test_decimal_is_not_checked_against_its_pattern() -> None:
    document = {
        "mapping-collection": {
            "uuid": UUID,
            "metadata": _metadata(),
            "provenance": {
                "method": "human",
                "matching-rationale": "semantic",
                "status": "complete",
                "coverage": {"target-coverage": 0.5},
                "mapping-description": "d",
            },
            "mappings": [
                {
                    "uuid": OTHER_UUID,
                    "source-resource": {"type": "catalog", "href": "https://x.org/s"},
                    "target-resource": {"type": "catalog", "href": "https://x.org/t"},
                    "maps": [
                        {
                            "uuid": "7e0a4d3c-1f5b-4c9a-b8e2-4a6b0c3f5d60",
                            "relationship": "equivalent-to",
                            "sources": [{"type": "control", "id-ref": "ac-1"}],
                            "targets": [{"type": "control", "id-ref": "pr.aa-01"}],
                        }
                    ],
                }
            ],
        }
    }
    _parse(document)


# --- A datatype value is kept as the input gives it -------------------------


@pytest.mark.parametrize(
    "ns", ["http://a", "https://example.com/a/../b"], ids=["no-path", "dot-segment"]
)
def test_uri_keeps_its_form(ns: str) -> None:
    output = _round_trip(_with_prop(ns=ns))
    assert output["catalog"]["metadata"]["props"][0]["ns"] == ns


def test_email_address_keeps_its_case() -> None:
    output = _round_trip(_with_email("A@Example.COM"))
    assert output["catalog"]["metadata"]["parties"][0]["email-addresses"] == [
        "A@Example.COM"
    ]


# --- A date-time-with-timezone value matches its pattern --------------------


@pytest.mark.parametrize(
    "value",
    [
        "1850-01-01T00:00:00Z",
        "2024-01-02T03:04:05+05:17",
        "2024-01-02T03:04:05z",
        1700000000,
    ],
    ids=["year-before-1900", "offset-outside-pattern", "lowercase-z", "json-number"],
)
def test_datetime_outside_the_pattern_is_rejected(value: Any) -> None:
    _assert_rejected(_with_last_modified(value), "last-modified")


def test_datetime_given_by_name_is_checked() -> None:
    with pytest.raises(ValidationError) as info:
        Metadata(
            title="T",
            last_modified=datetime(1850, 1, 1, tzinfo=UTC),
            version="1.0",
            oscal_version="1.2.3",
        )
    # A construction by name maps the name to its alias before it validates, so
    # the location of an error is the OSCAL key.
    assert [error["loc"] for error in info.value.errors()] == [("last-modified",)]


def test_valid_datetime_is_accepted() -> None:
    _parse(_with_last_modified("2024-01-02T03:04:05.123-05:00"))


# --- A uri value is a URI ---------------------------------------------------


def test_uri_fragment_is_accepted() -> None:
    _parse(_with_prop(ns="https://example.com/ns#x"))


@pytest.mark.parametrize(
    "ns",
    [f"http://a{CR}{LF}b", "https://x.org/a b", "x://"],
    ids=["line-break", "space", "one-letter-scheme"],
)
def test_malformed_uri_is_rejected(ns: str) -> None:
    _assert_rejected(_with_prop(ns=ns), "ns")


@pytest.mark.parametrize(
    "ns",
    ["urn:ietf:rfc:3986", "javascript:alert(1)", "file:///etc/passwd"],
)
def test_each_scheme_is_accepted(ns: str) -> None:
    _parse(_with_prop(ns=ns))


# --- A uri-reference value is a URI reference -------------------------------


@pytest.mark.parametrize("href", ["#ac-1", "../a.json", "https://example.com/x"])
def test_relative_reference_is_accepted(href: str) -> None:
    _parse(_with_link(href))


@pytest.mark.parametrize("href", ["a b", f"a{LF}b"], ids=["space", "line-break"])
def test_malformed_uri_reference_is_rejected(href: str) -> None:
    _assert_rejected(_with_link(href), "href")


# --- An email-address value is a mailbox ------------------------------------


@pytest.mark.parametrize("address", ["a@b", "x@localhost", "ü@例え.jp"])
def test_mailbox_is_accepted(address: str) -> None:
    _parse(_with_email(address))


@pytest.mark.parametrize(
    "address", ["Name <a@example.com>", "a@@b"], ids=["display-name", "two-at-signs"]
)
def test_malformed_mailbox_is_rejected(address: str) -> None:
    _assert_rejected(_with_email(address), "email-addresses")


# --- Each validation path applies the constraints ---------------------------


def test_element_validation_rejects_a_malformed_uuid() -> None:
    result = validate_element({"uuid": BAD_UUID}, "back-matter-resource")
    assert result.valid is False


def test_construction_rejects_a_malformed_uuid() -> None:
    with pytest.raises(ValidationError):
        BackMatterResource(uuid=BAD_UUID)


def test_builder_rejects_an_empty_document_identifier() -> None:
    # model_construct skips the check of DocumentId, so the builder is the
    # path under test. The builder validates each item again.
    empty = DocumentId.model_construct(identifier="")
    with pytest.raises(OscalBuilderError):
        make_resource(uuid=OTHER_UUID, document_ids=[empty])
