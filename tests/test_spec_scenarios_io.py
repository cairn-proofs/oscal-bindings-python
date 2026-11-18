"""Tests for scenarios of the error-model, document-parsing, and serialization
capabilities that no other test module verifies (issue #49).

Each test cites its scenarios with ``@pytest.mark.spec``.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Annotated

import pytest
from pydantic import Field, TypeAdapter, ValidationError
from support.canonical_json import canonicalize

from oscal_bindings.v1 import (
    OscalDocument,
    OscalParseError,
    parse_oscal,
    parse_oscal_file,
    serialize_oscal,
)

if TYPE_CHECKING:
    from pathlib import Path

UUID = "f47ac10b-58cc-4372-a567-0e02b2c3d479"


def _catalog(**catalog_extra: object) -> dict[str, object]:
    return {
        "catalog": {
            "uuid": UUID,
            "metadata": {
                "title": "Catalog",
                "last-modified": "2026-01-01T00:00:00Z",
                "version": "1.0",
                "oscal-version": "1.2.3",
            },
            **catalog_extra,
        }
    }


@pytest.mark.spec("PRS-005.01")
def test_the_oscal_key_media_type_is_accepted() -> None:
    document = _catalog(
        **{
            "back-matter": {
                "resources": [
                    {
                        "uuid": UUID,
                        "rlinks": [
                            {"href": "https://example.com/a", "media-type": "x/y"}
                        ],
                    }
                ]
            }
        }
    )
    parsed = parse_oscal(json.dumps(document))
    rlink = parsed.root.catalog.back_matter.resources[0].rlinks[0]  # type: ignore[union-attr]
    assert rlink.media_type == "x/y"


@pytest.mark.spec("PRS-010.04")
def test_a_valid_document_of_fifty_mebibytes_parses() -> None:
    """The binding documents no limit on the bytes of an input."""
    remarks = "x" * (50 * 1024 * 1024)
    # Put the large value in metadata.remarks, a markup-multiline string.
    document = _catalog()
    document["catalog"]["metadata"]["remarks"] = remarks  # type: ignore[index]
    data = json.dumps(document, separators=(",", ":")).encode("utf-8")
    assert len(data) > 50 * 1024 * 1024
    parsed = parse_oscal(data)
    assert isinstance(parsed, OscalDocument)
    assert len(parsed.root.catalog.metadata.remarks) == len(remarks)  # type: ignore[union-attr]


@pytest.mark.spec("ERR-004.04")
def test_invalid_utf8_inside_a_document_is_a_parse_error() -> None:
    data = (
        json.dumps(_catalog()).encode("utf-8").replace(b"Catalog", b"Cat\xff\xfealog")
    )
    with pytest.raises(OscalParseError) as info:
        parse_oscal(data)
    assert not isinstance(info.value, UnicodeDecodeError)


@pytest.mark.spec("ERR-006.02")
def test_a_missing_file_is_not_a_parse_error(tmp_path: Path) -> None:
    path = tmp_path / "absent.json"
    with pytest.raises(FileNotFoundError) as info:
        parse_oscal_file(path)
    assert not isinstance(info.value, OscalParseError)
    assert str(path) in str(info.value)


@pytest.mark.spec("PRS-007.03")
def test_the_unicode_property_class_needs_no_flag() -> None:
    """The regex engine of pydantic-core reads ``\\p{L}`` in Unicode mode as is."""
    adapter = TypeAdapter(Annotated[str, Field(pattern=r"^\p{L}+$")])
    assert adapter.validate_python("aé中") == "aé中"
    for rejected in ("a1", "a b", ""):
        with pytest.raises(ValidationError):
            adapter.validate_python(rejected)


@pytest.mark.spec("SER-003.01")
def test_default_serialization_is_indented() -> None:
    model = parse_oscal(json.dumps(_catalog()))
    text = serialize_oscal(model)
    lines = text.splitlines()
    assert len(lines) > 1
    assert lines[1].startswith("  ")
    assert not lines[1].startswith("   ")
    assert all((len(x) - len(x.lstrip(" "))) % 2 == 0 for x in lines)
    assert json.loads(text) == json.loads(serialize_oscal(model, indent=None))


@pytest.mark.spec("SER-003.02")
def test_compact_serialization_has_no_insignificant_whitespace() -> None:
    document = _catalog(params=[{"id": "p1"}])
    model = parse_oscal(json.dumps(document))
    compact = serialize_oscal(model, indent=None)
    assert "\n" not in compact
    loaded = json.loads(compact)
    assert compact == json.dumps(loaded, separators=(",", ":"), ensure_ascii=False)
    assert loaded == json.loads(serialize_oscal(model))


@pytest.mark.spec("SER-004.02")
def test_a_different_key_order_is_equivalent_after_canonical_ordering() -> None:
    model = parse_oscal(json.dumps(_catalog(params=[{"id": "p1", "label": "L"}])))
    text = serialize_oscal(model)
    reordered = json.dumps(json.loads(text), sort_keys=True)
    reversed_order = json.dumps(_reverse_keys(json.loads(text)))
    assert reordered != reversed_order
    assert canonicalize(reordered) == canonicalize(reversed_order) == canonicalize(text)


@pytest.mark.spec("SER-004.03")
def test_whitespace_differences_are_equivalent_in_the_canonical_form() -> None:
    model = parse_oscal(json.dumps(_catalog(params=[{"id": "p1", "label": "L"}])))
    pretty = serialize_oscal(model)
    compact = serialize_oscal(model, indent=None)
    assert pretty != compact
    assert canonicalize(pretty) == canonicalize(compact)


def _reverse_keys(value: object) -> object:
    if isinstance(value, dict):
        return {k: _reverse_keys(value[k]) for k in reversed(list(value))}
    if isinstance(value, list):
        return [_reverse_keys(v) for v in value]
    return value
