"""Tests for element-level validation."""

import pytest

from oscal_bindings import (
    get_supported_element_types,
    validate_element,
)
from oscal_bindings.parser import OscalParseError

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


class TestValidateElementErrors:
    """Tests for error handling."""

    def test_unknown_element_type_raises(self):
        with pytest.raises(OscalParseError, match="Unknown element type"):
            validate_element({}, "nonexistent-type")

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
