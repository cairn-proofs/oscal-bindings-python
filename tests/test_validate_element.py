"""Tests for element-level validation."""

import pytest

from oscal_bindings import (
    get_supported_element_types,
    validate_element,
)
from oscal_bindings.parser import OscalParseError
from oscal_bindings.v1 import OscalUnknownElementTypeError

# Minimal valid observation
VALID_OBSERVATION = {
    "uuid": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "description": "Test observation",
    "methods": ["EXAMINE"],
    "collected": "2026-01-01T00:00:00Z",
}

# Minimal valid metadata
VALID_METADATA = {
    "title": "Test Document",
    "last-modified": "2026-01-01T00:00:00+00:00",
    "version": "1.0",
    "oscal-version": "1.2.1",
}


class TestValidateElementValid:
    """Tests for valid elements."""

    def test_valid_observation(self):
        result = validate_element(VALID_OBSERVATION, "observation")
        assert result.valid is True
        assert result.errors is None

    def test_valid_metadata(self):
        result = validate_element(VALID_METADATA, "metadata")
        assert result.valid is True

    def test_valid_back_matter_empty(self):
        result = validate_element({}, "back-matter")
        assert result.valid is True


class TestValidateElementInvalid:
    """Tests for invalid elements."""

    def test_empty_dict_for_observation(self):
        result = validate_element({}, "observation")
        assert result.valid is False
        assert result.errors is not None
        assert len(result.errors) > 0

    def test_none_element(self):
        result = validate_element(None, "observation")
        assert result.valid is False
        assert result.errors is not None

    def test_missing_required_field(self):
        incomplete = {"uuid": "f47ac10b-58cc-4372-a567-0e02b2c3d479"}
        result = validate_element(incomplete, "observation")
        assert result.valid is False
        assert any(
            "description" in e.path or "description" in e.message for e in result.errors
        )


class TestValidateElementEnumAndUnion:
    """Tests for the enum and union element types."""

    def test_enum_accepts_its_string_value(self):
        assert validate_element("SHA-256", "hash-algorithm").valid is True

    def test_enum_rejects_another_string(self):
        result = validate_element("sha-256", "hash-algorithm")
        assert result.valid is False
        assert result.errors

    def test_union_accepts_a_valid_variant(self):
        parameter = {"id": "p1", "values": ["a"]}
        assert validate_element(parameter, "parameter").valid is True

    def test_union_rejects_an_unknown_key(self):
        parameter = {"id": "p1", "values": ["a"], "unknown-key": 1}
        result = validate_element(parameter, "parameter")
        assert result.valid is False
        assert result.errors

    def test_root_model_is_not_an_element_type(self):
        with pytest.raises(OscalUnknownElementTypeError, match="Unknown element type"):
            validate_element({}, "root-model")


class TestValidateElementErrors:
    """Tests for error handling."""

    def test_unknown_element_type_raises(self):
        with pytest.raises(OscalUnknownElementTypeError, match="Unknown element type"):
            validate_element({}, "nonexistent-type")

    def test_unknown_element_type_is_not_a_parse_error(self):
        with pytest.raises(OscalUnknownElementTypeError) as excinfo:
            validate_element({}, "nonexistent-type")
        assert not isinstance(excinfo.value, OscalParseError)

    def test_error_path_populated(self):
        result = validate_element({}, "observation")
        assert result.valid is False
        for error in result.errors:
            assert error.path is not None
            assert error.message is not None


class TestGetSupportedElementTypes:
    """Tests for get_supported_element_types."""

    def test_returns_non_empty_list(self):
        types = get_supported_element_types()
        assert len(types) > 0

    def test_returns_sorted_list(self):
        types = get_supported_element_types()
        assert types == sorted(types)

    def test_contains_observation(self):
        types = get_supported_element_types()
        assert "observation" in types

    def test_contains_metadata(self):
        types = get_supported_element_types()
        assert "metadata" in types

    def test_contains_catalog(self):
        types = get_supported_element_types()
        assert "catalog" in types


class TestNoUndocumentedLimit:
    """The binding documents no limit for element validation (ELV-004)."""

    @pytest.mark.spec("ELV-004.03")
    def test_ten_thousand_failures_are_all_listed(self):
        resources = [{} for _ in range(10_000)]
        result = validate_element({"resources": resources}, "back-matter")
        assert result.valid is False
        assert result.errors is not None
        paths = {e.path for e in result.errors}
        for i in range(10_000):
            assert f"resources.{i}.uuid" in paths
        assert len(result.errors) >= 10_000
