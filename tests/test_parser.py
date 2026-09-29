"""Tests for OSCAL parsing, serialization, and validation utilities."""

import json
import tempfile
from pathlib import Path

import pytest

from oscal_bindings.parser import (
    OscalDocument,
    OscalParseError,
    parse_catalog,
    parse_oscal,
    parse_oscal_file,
    parse_profile,
    serialize_oscal,
    validate_oscal,
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
