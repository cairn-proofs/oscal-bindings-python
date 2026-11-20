"""Tests for element-level validation."""

import pytest

from oscal_bindings import (
    get_supported_element_types,
    validate_element,
)
from oscal_bindings.parser import OscalParseError
from oscal_bindings.v1 import OscalLimitExceededError, OscalUnknownElementTypeError

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
    """The binding has no limit on the number of failures (ELV-004)."""

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


CATALOG_METADATA = {
    "title": "Test Catalog",
    "last-modified": "2026-01-01T00:00:00+00:00",
    "version": "1.0",
    "oscal-version": "1.2.3",
}


def _nested_group(levels: int) -> dict:
    """A group with ``levels`` levels of groups in its ``groups`` list."""
    group: dict = {"title": "leaf"}
    for i in range(levels):
        group = {"title": f"group {i}", "groups": [group]}
    return group


def _nested_catalog(levels: int) -> dict:
    return {
        "catalog": {
            "uuid": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
            "metadata": CATALOG_METADATA,
            "groups": [_nested_group(levels)],
        }
    }


# The element types of the three forms of a recursive type: a model, a union, a
# document. Each form has its own entry in the element map.
_DEEP_ELEMENTS = [
    pytest.param("catalog-group-with-groups", _nested_group, id="model"),
    pytest.param("catalog-group", _nested_group, id="union"),
    pytest.param("catalog-document", _nested_catalog, id="document"),
]


class TestElementDepthLimit:
    """An element over the depth limit is a limit-exceeded error (ELV-004, ERR-011)."""

    def test_error_keeps_its_limit(self):
        error = OscalLimitExceededError("message", limit="element_depth")
        assert error.limit == "element_depth"
        assert str(error) == "message"

    @pytest.mark.spec("ERR-011.02")
    def test_error_is_not_a_parse_error(self):
        with pytest.raises(OscalLimitExceededError) as excinfo:
            validate_element(_nested_group(1_000), "catalog-group-with-groups")
        assert not isinstance(excinfo.value, OscalParseError)
        assert not issubclass(OscalLimitExceededError, OscalParseError)

    @pytest.mark.spec("ELV-004.02", "ERR-011.01")
    @pytest.mark.parametrize(("element_type", "build"), _DEEP_ELEMENTS)
    def test_element_over_the_limit_raises(self, element_type, build):
        with pytest.raises(OscalLimitExceededError) as excinfo:
            validate_element(build(1_000), element_type)
        error = excinfo.value
        assert error.limit == "element_depth"
        # The ValidationError holds the element as input; the error keeps no link to it.
        assert error.__cause__ is None
        assert error.__context__ is None

    @pytest.mark.parametrize(("element_type", "build"), _DEEP_ELEMENTS)
    def test_element_within_the_limit_is_valid(self, element_type, build):
        result = validate_element(build(20), element_type)
        assert result.valid is True
        assert result.errors is None

    def test_failure_within_the_limit_is_an_invalid_result(self):
        group = _nested_group(20)
        group["props"] = [{}]  # a prop without its required name and value
        result = validate_element(group, "catalog-group-with-groups")
        assert result.valid is False
        assert result.errors

    @pytest.mark.parametrize("copies", [1, 2])
    def test_group_that_holds_itself_raises_and_ends(self, copies):
        group: dict = {"title": "self"}
        group["groups"] = [group] * copies
        with pytest.raises(OscalLimitExceededError) as excinfo:
            validate_element(group, "catalog-group-with-groups")
        assert excinfo.value.limit == "element_depth"
