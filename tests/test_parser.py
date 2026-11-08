"""Tests for OSCAL parsing, serialization, and validation utilities."""

import copy
import gc
import json
import pickle  # nosec B403 - the test pickles its own error entries
import tempfile
import tracemalloc
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from support.spec_artifact import corpus_root

from oscal_bindings import OscalDoc
from oscal_bindings.parser import (
    OscalDocument,
    OscalParseError,
    parse_catalog,
    parse_component_definition,
    parse_oscal,
    parse_oscal_file,
    parse_profile,
    serialize_oscal,
    validate_oscal,
)
from oscal_bindings.v1 import models
from oscal_bindings.v1.extensions.yaml_io import DEPTH_LIMIT
from oscal_bindings.v1.parser import (
    JSON_DEPTH_LIMIT,
    JSON_DEPTH_LIMIT_MSG,
    JSON_DIGIT_LIMIT,
    JSON_DIGIT_LIMIT_MSG,
)

# Minimal valid OSCAL catalog document
MINIMAL_CATALOG = json.dumps(
    {
        "catalog": {
            "uuid": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
            "metadata": {
                "title": "Test Catalog",
                "last-modified": "2026-01-01T00:00:00Z",
                "version": "1.0",
                "oscal-version": "1.2.1",
            },
        }
    }
)

# Minimal valid OSCAL profile document
MINIMAL_PROFILE = json.dumps(
    {
        "profile": {
            "uuid": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
            "metadata": {
                "title": "Test Profile",
                "last-modified": "2026-01-01T00:00:00Z",
                "version": "1.0",
                "oscal-version": "1.2.1",
            },
            "imports": [
                {
                    "href": "https://example.com/catalog.json",
                    "include-all": {},
                }
            ],
        }
    }
)

# Catalog with all optional fields populated
CATALOG_ALL_FIELDS = json.dumps(
    {
        "catalog": {
            "uuid": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
            "metadata": {
                "title": "Full Catalog",
                "last-modified": "2026-01-01T00:00:00Z",
                "version": "1.0",
                "oscal-version": "1.2.1",
            },
            "params": [{"id": "p1"}],
            "controls": [{"id": "c1", "title": "Control 1"}],
            "groups": [{"id": "g1", "title": "Group 1"}],
        }
    }
)


class TestParseOscal:
    """Tests for the parse_oscal function."""

    def test_parse_valid_catalog(self):
        result = parse_oscal(MINIMAL_CATALOG)
        assert result is not None
        assert isinstance(result, OscalDocument)

    def test_parse_valid_profile(self):
        result = parse_oscal(MINIMAL_PROFILE)
        assert result is not None
        assert isinstance(result, OscalDocument)

    def test_parse_invalid_json(self):
        with pytest.raises(OscalParseError):
            parse_oscal("not valid json {{{")

    def test_parse_invalid_oscal(self):
        with pytest.raises(OscalParseError, match="validation error"):
            parse_oscal('{"invalid": "document"}')

    def test_parse_empty_object(self):
        with pytest.raises(OscalParseError):
            parse_oscal("{}")

    def test_parse_error_contains_details(self):
        with pytest.raises(OscalParseError) as exc_info:
            parse_oscal('{"catalog": {}}')
        assert exc_info.value.errors


class TestParseOscalBytes:
    """parse_oscal accepts bytes directly."""

    def test_parse_valid_catalog_bytes(self):
        result = parse_oscal(MINIMAL_CATALOG.encode("utf-8"))
        assert isinstance(result, OscalDocument)
        assert result.root.catalog.uuid == "f47ac10b-58cc-4372-a567-0e02b2c3d479"

    def test_parse_valid_profile_bytes(self):
        result = parse_oscal(MINIMAL_PROFILE.encode("utf-8"))
        assert isinstance(result, OscalDocument)

    def test_str_and_bytes_produce_equal_models(self):
        from_str = parse_oscal(MINIMAL_CATALOG)
        from_bytes = parse_oscal(MINIMAL_CATALOG.encode("utf-8"))
        assert from_str == from_bytes

    def test_invalid_utf8_raises_oscal_parse_error(self):
        # Lone continuation byte; invalid UTF-8.
        with pytest.raises(OscalParseError):
            parse_oscal(b"\xff\xfe not utf-8")

    def test_invalid_json_bytes_raises_oscal_parse_error(self):
        with pytest.raises(OscalParseError):
            parse_oscal(b"not valid json {{{")


class TestParseOscalFile:
    """Tests for the parse_oscal_file function."""

    def test_parse_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write(MINIMAL_CATALOG)
            f.flush()
            result = parse_oscal_file(Path(f.name))
            assert result is not None
            assert isinstance(result, OscalDocument)

    def test_parse_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            parse_oscal_file(Path("/nonexistent/path/oscal.json"))

    def test_parse_file_with_string_path(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write(MINIMAL_CATALOG)
            f.flush()
            result = parse_oscal_file(f.name)
            assert result is not None

    def test_parse_file_reads_as_bytes(self):
        # Round-trip a UTF-8-encoded document through the file path to
        # exercise the read_bytes branch.
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".json", delete=False) as f:
            f.write(MINIMAL_CATALOG.encode("utf-8"))
            f.flush()
            result = parse_oscal_file(f.name)
            assert result.root.catalog.uuid == ("f47ac10b-58cc-4372-a567-0e02b2c3d479")


class TestSerializeOscal:
    """Tests for the serialize_oscal function."""

    def test_roundtrip_catalog(self):
        model = parse_oscal(MINIMAL_CATALOG)
        json_output = serialize_oscal(model)
        reparsed = parse_oscal(json_output)
        assert reparsed is not None

    def test_roundtrip_profile(self):
        model = parse_oscal(MINIMAL_PROFILE)
        json_output = serialize_oscal(model)
        reparsed = parse_oscal(json_output)
        assert reparsed is not None

    def test_serialize_compact(self):
        model = parse_oscal(MINIMAL_CATALOG)
        json_output = serialize_oscal(model, indent=None)
        assert "\n" not in json_output

    def test_serialize_pretty(self):
        model = parse_oscal(MINIMAL_CATALOG)
        json_output = serialize_oscal(model, indent=2)
        assert "\n" in json_output

    def test_serialize_uses_aliases(self):
        """Verify serialization uses JSON field names (hyphenated), not Python names."""
        model = parse_oscal(MINIMAL_CATALOG)
        json_output = serialize_oscal(model)
        parsed = json.loads(json_output)
        assert "catalog" in parsed
        metadata = parsed["catalog"]["metadata"]
        assert "last-modified" in metadata
        assert "oscal-version" in metadata


class TestValidateOscal:
    """Tests for the validate_oscal function."""

    def test_valid_document(self):
        assert validate_oscal(MINIMAL_CATALOG) is True

    def test_invalid_json(self):
        assert validate_oscal("not json") is False

    def test_invalid_oscal(self):
        assert validate_oscal('{"invalid": "document"}') is False

    def test_empty_object(self):
        assert validate_oscal("{}") is False

    def test_valid_bytes(self):
        assert validate_oscal(MINIMAL_CATALOG.encode("utf-8")) is True

    def test_invalid_utf8_bytes(self):
        assert validate_oscal(b"\xff\xfe not utf-8") is False


class TestTypedDeserialization:
    """Tests for strongly-typed field access on parsed models."""

    def test_catalog_typed_fields(self):
        result = parse_oscal(MINIMAL_CATALOG)
        catalog = result.root.catalog
        assert catalog.uuid == "f47ac10b-58cc-4372-a567-0e02b2c3d479"
        assert catalog.metadata.title == "Test Catalog"
        assert catalog.metadata.oscal_version == "1.2.1"

    def test_profile_typed_fields(self):
        result = parse_oscal(MINIMAL_PROFILE)
        profile = result.root.profile
        assert profile.uuid == "f47ac10b-58cc-4372-a567-0e02b2c3d479"
        assert profile.metadata.title == "Test Profile"
        assert len(profile.imports) == 1

    def test_roundtrip_catalog_preserves_typed_fields(self):
        model = parse_oscal(MINIMAL_CATALOG)
        json_output = serialize_oscal(model)
        reparsed = parse_oscal(json_output)
        assert reparsed.root.catalog.uuid == model.root.catalog.uuid
        assert reparsed.root.catalog.metadata.title == model.root.catalog.metadata.title

    def test_roundtrip_profile_preserves_typed_fields(self):
        model = parse_oscal(MINIMAL_PROFILE)
        json_output = serialize_oscal(model)
        reparsed = parse_oscal(json_output)
        assert reparsed.root.profile.uuid == model.root.profile.uuid
        assert reparsed.root.profile.metadata.title == model.root.profile.metadata.title


class TestOptionalFields:
    """Tests for documents with optional fields missing or populated."""

    def test_catalog_optional_fields_missing(self):
        result = parse_oscal(MINIMAL_CATALOG)
        catalog = result.root.catalog
        assert catalog.groups is None
        assert catalog.controls is None
        assert catalog.params is None
        assert catalog.back_matter is None

    def test_catalog_all_fields_populated(self):
        result = parse_oscal(CATALOG_ALL_FIELDS)
        catalog = result.root.catalog
        assert catalog.groups is not None
        assert len(catalog.groups) == 1
        assert catalog.controls is not None
        assert len(catalog.controls) == 1
        assert catalog.params is not None
        assert len(catalog.params) == 1


class TestErrorMessages:
    """Tests verifying error messages are descriptive."""

    def test_invalid_json_error_message(self):
        with pytest.raises(OscalParseError) as exc_info:
            parse_oscal("not valid json {{{")
        assert "validation error" in str(exc_info.value) or "Invalid JSON" in str(
            exc_info.value
        )

    def test_validation_error_includes_count(self):
        with pytest.raises(OscalParseError) as exc_info:
            parse_oscal('{"catalog": {}}')
        assert "validation error" in str(exc_info.value)

    def test_validation_error_has_error_list(self):
        with pytest.raises(OscalParseError) as exc_info:
            parse_oscal('{"catalog": {}}')
        assert len(exc_info.value.errors) > 0

    def test_file_not_found_includes_path(self):
        with pytest.raises(FileNotFoundError) as exc_info:
            parse_oscal_file(Path("/nonexistent/specific/path.json"))
        assert "/nonexistent/specific/path.json" in str(exc_info.value)


class TestTypedParsers:
    """Tests for typed convenience parser functions."""

    def test_parse_catalog_valid(self):
        result = parse_catalog(MINIMAL_CATALOG)
        assert result.catalog.uuid == "f47ac10b-58cc-4372-a567-0e02b2c3d479"
        assert result.catalog.metadata.title == "Test Catalog"

    def test_parse_catalog_wrong_type(self):
        with pytest.raises(OscalParseError, match="not a Catalog"):
            parse_catalog(MINIMAL_PROFILE)

    def test_parse_profile_valid(self):
        result = parse_profile(MINIMAL_PROFILE)
        assert result.profile.uuid == "f47ac10b-58cc-4372-a567-0e02b2c3d479"
        assert result.profile.metadata.title == "Test Profile"

    def test_parse_profile_wrong_type(self):
        with pytest.raises(OscalParseError, match="not a Profile"):
            parse_profile(MINIMAL_CATALOG)

    def test_parse_catalog_accepts_bytes(self):
        result = parse_catalog(MINIMAL_CATALOG.encode("utf-8"))
        assert result.catalog.uuid == "f47ac10b-58cc-4372-a567-0e02b2c3d479"

    def test_parse_profile_accepts_bytes(self):
        result = parse_profile(MINIMAL_PROFILE.encode("utf-8"))
        assert result.profile.uuid == "f47ac10b-58cc-4372-a567-0e02b2c3d479"


# --- JSON resource limits (PRS-010, local spec json-resource-limit) ---------
#
# These tests run against the installed pydantic-core, with no mock. A lock
# update that moves a limit or changes its error text fails them (design D4).


def _deep_catalog(levels: int) -> str:
    """A conformant catalog whose groups nest ``levels`` levels deep.

    The root object, the catalog object, and two containers for each level
    (the `groups` array and the group object) hold the innermost title. So the
    title of the deepest group sits at depth ``2 + 2 * levels``, and the group
    object at one level less.
    """
    group: dict[str, object] = {"title": "g"}
    for _ in range(levels - 1):
        group = {"title": "g", "groups": [group]}
    doc = json.loads(MINIMAL_CATALOG)
    doc["catalog"]["groups"] = [group]
    return json.dumps(doc)


# Groups nested 99 levels put the deepest title at depth 200, the limit. A
# 100th level adds a group object at depth 201.
AT_DEPTH_LIMIT = (JSON_DEPTH_LIMIT - 2) // 2
PAST_DEPTH_LIMIT = AT_DEPTH_LIMIT + 1


def _component(start: str) -> str:
    """A conformant component definition whose port-range start is ``start``."""
    doc = {
        "component-definition": {
            "uuid": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
            "metadata": json.loads(MINIMAL_CATALOG)["catalog"]["metadata"],
            "components": [
                {
                    "uuid": "f47ac10b-58cc-4372-a567-0e02b2c3d480",
                    "type": "service",
                    "title": "S",
                    "description": "d",
                    "protocols": [
                        {"name": "https", "port-ranges": [{"start": 0, "end": 443}]}
                    ],
                }
            ],
        }
    }
    return json.dumps(doc).replace('"start": 0', f'"start": {start}')


def _unknown_key(value: str) -> str:
    """The minimal catalog with an unknown key ``x`` that holds ``value``.

    The root object and the catalog object hold ``value``, so it sits at
    depth 2.
    """
    return MINIMAL_CATALOG[:-2] + f', "x": {value}' + "}}"


AT_DIGIT_LIMIT = "9" * JSON_DIGIT_LIMIT
PAST_DIGIT_LIMIT = "9" * (JSON_DIGIT_LIMIT + 1)


def _json_parsers(tmp_path: Path) -> dict[str, Callable[[str], object]]:
    """Each JSON operation that the JSON limits apply to, on text."""

    def from_file(text: str) -> object:
        path = tmp_path / "doc.json"
        path.write_text(text, encoding="utf-8")
        return parse_oscal_file(path)

    def doc_from_file(text: str) -> object:
        path = tmp_path / "doc.json"
        path.write_text(text, encoding="utf-8")
        return OscalDoc.from_file(path)

    return {
        "parse_oscal": parse_oscal,
        "parse_oscal(bytes)": lambda text: parse_oscal(text.encode()),
        "parse_oscal_file": from_file,
        "OscalDoc.from_json": OscalDoc.from_json,
        "OscalDoc.from_file": doc_from_file,
    }


def _limit_error(parse: Callable[[str], object], text: str) -> dict[str, Any]:
    """Parse ``text``, require a JSON limit error, and return its one entry."""
    with pytest.raises(OscalParseError) as info:
        parse(text)
    errors = info.value.errors
    assert len(errors) == 1, errors
    entry: dict[str, Any] = errors[0]
    assert str(info.value) == entry["msg"]
    return entry


JSON_LIMIT_KINDS = {"json_depth_limit", "json_digit_limit", "json_invalid"}


def _kinds(error: OscalParseError) -> set[str]:
    return {e["type"] for e in error.errors}


class TestJsonDepthLimit:
    def test_limit_value(self) -> None:
        assert JSON_DEPTH_LIMIT == 200
        assert DEPTH_LIMIT < JSON_DEPTH_LIMIT

    def test_conformant_document_at_the_limit_parses_on_each_operation(
        self, tmp_path: Path
    ) -> None:
        text = _deep_catalog(AT_DEPTH_LIMIT)
        for name, parse in _json_parsers(tmp_path).items():
            assert parse(text) is not None, name
        assert parse_catalog(text).catalog.groups
        assert validate_oscal(text) is True

    def test_conformant_document_past_the_limit_is_rejected_on_each_operation(
        self, tmp_path: Path
    ) -> None:
        text = _deep_catalog(PAST_DEPTH_LIMIT)
        parsers = {**_json_parsers(tmp_path), "parse_catalog": parse_catalog}
        for name, parse in parsers.items():
            entry = _limit_error(parse, text)
            assert entry["type"] == "json_depth_limit", name
            assert entry["msg"] == JSON_DEPTH_LIMIT_MSG
        assert validate_oscal(text) is False

    @pytest.mark.parametrize(
        ("opener", "closer"), [("[", "]"), ('{"a":', "}")], ids=["arrays", "objects"]
    )
    def test_arrays_and_objects_count_the_same(self, opener: str, closer: str) -> None:
        # Two objects hold the value of `x`, so n containers put the scalar at
        # depth 2 + n.
        def nested(n: int) -> str:
            return _unknown_key(opener * n + "1" + closer * n)

        at = nested(JSON_DEPTH_LIMIT - 2)
        with pytest.raises(OscalParseError) as info:
            parse_oscal(at)
        assert "extra_forbidden" in _kinds(info.value)
        assert not _kinds(info.value) & JSON_LIMIT_KINDS
        entry = _limit_error(parse_oscal, nested(JSON_DEPTH_LIMIT - 1))
        assert entry["type"] == "json_depth_limit"
        assert (entry["loc"], entry["line"]) == ((), 1)
        assert isinstance(entry["column"], int)


class TestJsonDigitLimit:
    def test_limit_value(self) -> None:
        assert JSON_DIGIT_LIMIT == 4300

    def test_number_at_the_limit_parses_on_each_operation(self, tmp_path: Path) -> None:
        text = _component(AT_DIGIT_LIMIT)
        for name, parse in _json_parsers(tmp_path).items():
            assert parse(text) is not None, name
        doc = parse_component_definition(text)
        start = doc.component_definition.components[0].protocols[0].port_ranges[0].start
        assert start == int(AT_DIGIT_LIMIT)
        assert validate_oscal(text) is True

    def test_number_past_the_limit_is_rejected_on_each_operation(
        self, tmp_path: Path
    ) -> None:
        text = _component(PAST_DIGIT_LIMIT)
        parsers = {
            **_json_parsers(tmp_path),
            "parse_component_definition": parse_component_definition,
        }
        for name, parse in parsers.items():
            entry = _limit_error(parse, text)
            assert entry["type"] == "json_digit_limit", name
            assert entry["msg"] == JSON_DIGIT_LIMIT_MSG
        assert validate_oscal(text) is False

    @pytest.mark.parametrize(
        "number",
        [
            "-" + AT_DIGIT_LIMIT,
            AT_DIGIT_LIMIT + "." + "9" * 20_000,
            AT_DIGIT_LIMIT + "e" + "9" * 10,
            "1e5000",
        ],
        ids=["sign", "fraction", "exponent", "large-exponent"],
    )
    def test_sign_fraction_and_exponent_do_not_count(self, number: str) -> None:
        with pytest.raises(OscalParseError) as info:
            parse_oscal(_unknown_key(number))
        assert "extra_forbidden" in _kinds(info.value)
        assert not _kinds(info.value) & JSON_LIMIT_KINDS

    def test_limit_applies_at_any_location(self) -> None:
        entry = _limit_error(parse_oscal, _unknown_key(PAST_DIGIT_LIMIT))
        assert entry["type"] == "json_digit_limit"

    def test_schema_invalid_document_over_the_limit_gets_one_limit_entry(
        self,
    ) -> None:
        doc = json.loads(_component("1"))
        component = doc["component-definition"]["components"][0]
        component["title"] = 5
        del component["description"]
        text = json.dumps(doc).replace('"start": 1', f'"start": {PAST_DIGIT_LIMIT}')
        entry = _limit_error(parse_oscal, text)
        assert entry["type"] == "json_digit_limit"


class TestJsonLimitErrorShape:
    @pytest.mark.parametrize(
        "text",
        [_deep_catalog(PAST_DEPTH_LIMIT), _component(PAST_DIGIT_LIMIT)],
        ids=["depth", "digits"],
    )
    def test_error_holds_no_input_text(self, text: str) -> None:
        assert len(text) > 1_000
        with pytest.raises(OscalParseError) as info:
            parse_oscal(text)
        error = info.value
        (entry,) = error.errors
        assert set(entry) == {"type", "loc", "msg", "input", "line", "column"}
        assert entry["input"] is None
        assert not any(isinstance(v, str) and len(v) > 200 for v in entry.values())
        # No exception in the chain keeps the ValidationError and its input.
        assert error.__cause__ is None
        assert error.__context__ is None

    def test_the_two_limits_have_different_types(self) -> None:
        depth = _limit_error(parse_oscal, _deep_catalog(PAST_DEPTH_LIMIT))
        digits = _limit_error(parse_oscal, _component(PAST_DIGIT_LIMIT))
        assert depth["type"] != digits["type"]

    def test_column_counts_bytes(self) -> None:
        # Each `é` is one character and two UTF-8 bytes. Five of them before
        # the number move the reported column by 10, not by 5.
        plain = _limit_error(parse_oscal, _unknown_key(PAST_DIGIT_LIMIT))
        accented = MINIMAL_CATALOG.replace("Test Catalog", "Test Catalog" + "é" * 5)
        text = accented[:-2] + f', "x": {PAST_DIGIT_LIMIT}' + "}}"
        entry = _limit_error(parse_oscal, text)
        assert entry["column"] == plain["column"] + 5 * 2


# ---------------------------------------------------------------------------
# Document type selection (spec document-type-selection)
# ---------------------------------------------------------------------------


NO_ROOT_KEY = "Not an OSCAL document: no known root key"


def _catalog_with_control_id(control_id: object) -> str:
    data = json.loads(MINIMAL_CATALOG)
    data["catalog"]["controls"] = [{"id": control_id, "title": "C"}]
    return json.dumps(data)


def _parse_errors(text: str) -> list[dict[str, Any]]:
    with pytest.raises(OscalParseError) as info:
        parse_oscal(text)
    errors: list[dict[str, Any]] = info.value.errors
    return errors


class TestDocumentTypeSelection:
    @pytest.mark.parametrize(
        ("root_key", "cls"),
        [
            ("catalog", models.CatalogDocument),
            ("profile", models.ProfileDocument),
            ("component-definition", models.ComponentDefinitionDocument),
            ("system-security-plan", models.SystemSecurityPlanDocument),
            ("assessment-plan", models.AssessmentPlanDocument),
            ("assessment-results", models.AssessmentResultsDocument),
            ("plan-of-action-and-milestones", models.PlanOfActionAndMilestonesDocument),
            ("mapping-collection", models.MappingCollectionDocument),
        ],
    )
    def test_each_document_type_parses_to_its_type_and_round_trips(
        self, root_key: str, cls: type
    ) -> None:
        path = corpus_root() / "documents" / "valid" / f"{root_key}.json"
        parsed = parse_oscal(path.read_bytes())
        assert type(parsed.root) is cls
        assert parse_oscal(serialize_oscal(parsed)) == parsed

    def test_a_fault_reports_only_errors_of_the_selected_type(self) -> None:
        errors = _parse_errors(_catalog_with_control_id(5))
        assert [(e["type"], e["loc"]) for e in errors] == [
            ("string_type", ("CatalogDocument", "catalog", "controls", 0, "id"))
        ]

    def test_two_root_keys_select_the_first_one(self) -> None:
        data = json.loads(MINIMAL_CATALOG)
        data["profile"] = json.loads(MINIMAL_PROFILE)["profile"]
        errors = _parse_errors(json.dumps(data))
        assert [(e["type"], e["loc"]) for e in errors] == [
            ("extra_forbidden", ("CatalogDocument", "profile"))
        ]
        profile_first = {"profile": data["profile"], "catalog": data["catalog"]}
        errors = _parse_errors(json.dumps(profile_first))
        assert {e["loc"][0] for e in errors} == {"ProfileDocument"}

    @pytest.mark.parametrize(
        ("text", "msg"),
        [
            ("{}", NO_ROOT_KEY),
            ("[]", NO_ROOT_KEY),
            ('"catalog"', NO_ROOT_KEY),
            ("5", NO_ROOT_KEY),
            ("null", NO_ROOT_KEY),
            ('{"metadata": {}}', f"{NO_ROOT_KEY} (found: 'metadata')"),
            ('{"a": 1, "b": 2}', f"{NO_ROOT_KEY} (found: 'a', 'b')"),
        ],
        ids=["empty", "array", "string", "number", "null", "one-key", "two-keys"],
    )
    def test_no_root_key_reports_one_error(self, text: str, msg: str) -> None:
        (entry,) = _parse_errors(text)
        assert entry["type"] == "oscal_document_type"
        assert entry["loc"] == ()
        assert entry["msg"] == msg

    def test_name_keyed_root_key_is_named(self) -> None:
        path = corpus_root() / "documents" / "valid" / "assessment-plan.json"
        data = json.loads(path.read_bytes())
        data["assessment_plan"] = data.pop("assessment-plan")
        (entry,) = _parse_errors(json.dumps(data))
        assert entry["type"] == "oscal_document_type"
        assert entry["loc"] == ()
        assert entry["msg"] == f"{NO_ROOT_KEY} (found: 'assessment_plan')"

    def test_validity_check_returns_false_for_no_root_key(self) -> None:
        assert validate_oscal('{"metadata": {}}') is False

    def test_a_document_value_is_accepted_as_the_root(self) -> None:
        catalog = parse_oscal(MINIMAL_CATALOG).root
        assert models.OscalDocument(root=catalog).root is catalog
        assert models.OscalDocument.model_validate(catalog).root is catalog


# ---------------------------------------------------------------------------
# Parse error entries (spec parse-error-entries)
# ---------------------------------------------------------------------------

OMITTED = OscalParseError.OMITTED_INPUT


def _catalog_without_metadata() -> str:
    data = json.loads(MINIMAL_CATALOG)
    del data["catalog"]["metadata"]
    return json.dumps(data)


def _schema_error(text: str | bytes) -> OscalParseError:
    with pytest.raises(OscalParseError) as info:
        parse_oscal(text)
    return info.value


class TestParseErrorEntries:
    def test_a_missing_field_has_the_sentinel_input(self) -> None:
        (entry,) = _schema_error(_catalog_without_metadata()).errors
        assert entry["type"] == "missing"
        assert entry["loc"] == ("CatalogDocument", "catalog", "metadata")
        assert entry["input"] is OMITTED

    def test_a_scalar_input_is_kept(self) -> None:
        (entry,) = _schema_error(_catalog_with_control_id(5)).errors
        assert entry["input"] == 5

    def test_an_unknown_key_with_an_array_value_has_the_sentinel_input(self) -> None:
        data = json.loads(MINIMAL_CATALOG)
        data["catalog"]["bogus"] = [1, 2, 3]
        (entry,) = _schema_error(json.dumps(data)).errors
        assert entry["type"] == "extra_forbidden"
        assert entry["input"] is OMITTED

    def test_no_root_key_names_the_keys_and_has_the_sentinel_input(self) -> None:
        (entry,) = _schema_error('{"metadata": {}}').errors
        assert entry["type"] == "oscal_document_type"
        assert entry["msg"] == f"{NO_ROOT_KEY} (found: 'metadata')"
        assert entry["input"] is OMITTED

    def test_the_sentinel_survives_a_copy(self) -> None:
        errors = _schema_error(_catalog_without_metadata()).errors
        assert repr(OMITTED) == "<omitted input>"
        assert copy.copy(OMITTED) is OMITTED
        assert copy.deepcopy(errors)[0]["input"] is OMITTED
        # Pickling a module-level singleton from the binding is safe here.
        assert pickle.loads(pickle.dumps(errors))[0]["input"] is OMITTED  # noqa: S301

    def test_no_exception_in_the_chain(self) -> None:
        error = _schema_error(_catalog_without_metadata())
        assert error.__cause__ is None
        assert error.__context__ is None

    def test_the_error_holds_little_memory(self, nist_docs: list[Any]) -> None:
        (doc,) = [
            d
            for d in nist_docs
            if d.rel_path.endswith("NIST_SP-800-53_rev5_catalog.json")
        ]
        data = json.loads(doc.raw_bytes)
        del data["catalog"]["metadata"]
        text = json.dumps(data).encode()
        del data
        # Measure what dropping the error frees. pydantic-core's string cache
        # keeps memory of its own across parses, so the total grows without it.
        tracemalloc.start()
        try:
            try:
                parse_oscal(text)
            except OscalParseError as caught:
                error = caught
            gc.collect()
            with_error, _ = tracemalloc.get_traced_memory()
            count = len(error.errors)
            del error
            gc.collect()
            without_error, _ = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        held = with_error - without_error
        assert count == 1
        assert held < len(text) / 10, f"{held:,} B held for {len(text):,} B of input"
