"""Tests for ``scripts/manifest.py``: validation of the naming manifest.

The released manifest of the pinned spec artifact must pass against the
vendored schema. Each changed copy must fail with a failure that names the
problem. Test names carry the scenario id of the naming-manifest capability
where one exists.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import TYPE_CHECKING, Any

import pytest
from support.scripts import load_script
from support.spec_artifact import ensure_spec_artifact

if TYPE_CHECKING:
    from pathlib import Path

manifest_mod = load_script("manifest")
pin = load_script("spec_artifact")

RELEASE: str = pin.OSCAL_RELEASE


@pytest.fixture(scope="module")
def released() -> dict[str, Any]:
    """The parsed names.json, names.schema.json, and the vendored schema bytes."""
    paths = pin.artifact_paths(ensure_spec_artifact())
    return {
        "manifest": json.loads(paths.names.read_bytes()),
        "names_schema": json.loads(paths.names_schema.read_bytes()),
        "schema_bytes": manifest_mod.VENDORED_SCHEMA.read_bytes(),
    }


@pytest.fixture
def manifest(released: dict[str, Any]) -> dict[str, Any]:
    """A deep copy of the released manifest that a test can change."""
    return copy.deepcopy(released["manifest"])


def _validate(
    released: dict[str, Any],
    manifest: object,
    *,
    names_schema: dict[str, Any] | None = None,
    schema_bytes: bytes | None = None,
    release: str = RELEASE,
) -> list[str]:
    failures: list[str] = manifest_mod.validate_manifest(
        manifest,
        released["names_schema"] if names_schema is None else names_schema,
        released["schema_bytes"] if schema_bytes is None else schema_bytes,
        release,
    )
    return failures


def _entry(manifest: dict[str, Any], kind: str) -> dict[str, Any]:
    entry: dict[str, Any] = next(t for t in manifest["types"] if t["kind"] == kind)
    return entry


def _assert_fails(failures: list[str], *fragments: str) -> None:
    assert failures, "the manifest is valid, but a failure was expected"
    for fragment in fragments:
        assert any(fragment in f for f in failures), (fragment, failures)


# ---------------------------------------------------------------------------
# The released manifest


def test_released_manifest_is_valid(released: dict[str, Any]) -> None:
    assert _validate(released, released["manifest"]) == []


def test_released_manifest_has_every_kind(released: dict[str, Any]) -> None:
    kinds = {t["kind"] for t in released["manifest"]["types"]}
    assert kinds == {
        "object",
        "document",
        "document-union",
        "union",
        "enum",
        "single-or-many",
    }


def test_load_validated_manifest_returns_released_manifest() -> None:
    paths = pin.artifact_paths(ensure_spec_artifact())
    loaded = manifest_mod.load_validated_manifest(paths)
    assert loaded == json.loads(paths.names.read_bytes())


# ---------------------------------------------------------------------------
# NAM-003: names, references, format, and release


def test_nam_003_01_name_with_non_identifier_character_is_invalid(
    released: dict[str, Any], manifest: dict[str, Any]
) -> None:
    manifest["types"][0]["name"] = "Bad-Name"
    _assert_fails(
        _validate(released, manifest),
        "[names.schema.json] names.json/types/0",
        "Bad-Name",
    )


@pytest.mark.parametrize("name", ["Bad Name", 'Bad"Name'])
def test_nam_003_01_name_with_space_or_quote_is_invalid(
    released: dict[str, Any], manifest: dict[str, Any], name: str
) -> None:
    manifest["types"][0]["name"] = name
    _assert_fails(_validate(released, manifest), "names.json/types/0")


def test_nam_003_03_name_with_final_newline_is_invalid(
    released: dict[str, Any], manifest: dict[str, Any]
) -> None:
    index, entry = next(
        (i, t) for i, t in enumerate(manifest["types"]) if t["name"] == "Hash"
    )
    entry["name"] = "Hash\n"
    _assert_fails(
        _validate(released, manifest),
        f"[names.schema.json] names.json/types/{index}",
    )


def test_name_check_uses_full_string_without_json_schema(
    released: dict[str, Any], manifest: dict[str, Any]
) -> None:
    """The cross check rejects a final newline also when the JSON Schema allows it."""
    manifest["types"][0]["name"] += "\n"
    _assert_fails(
        _validate(released, manifest, names_schema={}),
        "is not a PascalCase identifier",
    )


def test_nam_003_02_duplicate_name_is_invalid(
    released: dict[str, Any], manifest: dict[str, Any]
) -> None:
    duplicate = manifest["types"][0]["name"]
    manifest["types"][1]["name"] = duplicate
    _assert_fails(
        _validate(released, manifest),
        f"the name {duplicate} occurs more than once",
    )


def test_nam_003_04_reference_to_missing_entry_is_invalid(
    released: dict[str, Any], manifest: dict[str, Any]
) -> None:
    union = _entry(manifest, "union")
    union["variants"][0]["type"] = "NoSuchType"
    _assert_fails(
        _validate(released, manifest),
        f"{union['name']}: the reference NoSuchType names no entry",
    )


@pytest.mark.parametrize(
    ("kind", "field"), [("single-or-many", "item"), ("document-union", "members")]
)
def test_nam_003_04_item_and_member_references_must_name_an_entry(
    released: dict[str, Any], manifest: dict[str, Any], kind: str, field: str
) -> None:
    entry = _entry(manifest, kind)
    if field == "members":
        entry["members"][0] = "NoSuchType"
    else:
        entry["item"] = "NoSuchType"
    _assert_fails(
        _validate(released, manifest),
        f"{entry['name']}: the reference NoSuchType names no entry",
    )


def test_nam_003_05_unknown_format_version_is_rejected(
    released: dict[str, Any], manifest: dict[str, Any]
) -> None:
    manifest["format"] = 2
    _assert_fails(
        _validate(released, manifest), "[names.schema.json] names.json/format"
    )


def test_nam_003_05_unknown_format_version_is_rejected_without_json_schema(
    released: dict[str, Any], manifest: dict[str, Any]
) -> None:
    manifest["format"] = 2
    _assert_fails(
        _validate(released, manifest, names_schema={}),
        "format 2 is not supported",
    )


def test_other_oscal_release_is_rejected(
    released: dict[str, Any], manifest: dict[str, Any]
) -> None:
    manifest["oscal-release"] = "1.2.4"
    _assert_fails(
        _validate(released, manifest),
        f"oscal-release '1.2.4' is not {RELEASE}",
    )


def test_consumer_of_other_release_rejects_manifest(
    released: dict[str, Any],
) -> None:
    _assert_fails(
        _validate(released, released["manifest"], release="1.2.4"),
        "is not 1.2.4",
    )


# ---------------------------------------------------------------------------
# NAM-002: the schema hash


def test_nam_002_03_schema_hash_mismatch_is_detected(
    released: dict[str, Any],
) -> None:
    _assert_fails(
        _validate(
            released,
            released["manifest"],
            schema_bytes=released["schema_bytes"] + b"\n",
        ),
        "schema.sha256",
        "does not match the schema",
    )


def test_wrong_recorded_schema_hash_is_detected(
    released: dict[str, Any], manifest: dict[str, Any]
) -> None:
    manifest["schema"]["sha256"] = "0" * 64
    _assert_fails(_validate(released, manifest), "does not match the schema")


# ---------------------------------------------------------------------------
# NAM-001: pointers


def test_nam_001_03_unresolvable_pointer_is_invalid(
    released: dict[str, Any], manifest: dict[str, Any]
) -> None:
    entry = manifest["types"][0]
    entry["sites"] = ["#/definitions/missing"]
    _assert_fails(
        _validate(released, manifest),
        f"{entry['name']}: the pointer #/definitions/missing does not resolve",
    )


@pytest.mark.parametrize("token", ["__proto__", "constructor"])
def test_nam_001_03_inherited_member_pointer_does_not_resolve(
    released: dict[str, Any], manifest: dict[str, Any], token: str
) -> None:
    entry = manifest["types"][0]
    entry["sites"] = [f"#/definitions/{token}"]
    _assert_fails(
        _validate(released, manifest),
        f"the pointer #/definitions/{token} does not resolve",
    )


def test_pointer_in_two_entries_is_invalid(
    released: dict[str, Any], manifest: dict[str, Any]
) -> None:
    site = manifest["types"][0]["sites"][0]
    manifest["types"][1]["sites"] = [site]
    _assert_fails(
        _validate(released, manifest),
        f"the pointer {site} occurs in more than one entry",
    )


# ---------------------------------------------------------------------------
# NAM-004: the JSON Schema and the store checks


def test_nam_004_01_entry_without_kind_fails_and_names_entry(
    released: dict[str, Any], manifest: dict[str, Any]
) -> None:
    entry = manifest["types"][0]
    del entry["kind"]
    _assert_fails(
        _validate(released, manifest),
        f"names.json/types/0 (entry {entry['name']!r})",
    )


def test_nam_004_02_schema_file_name_with_path_fails(
    released: dict[str, Any], manifest: dict[str, Any]
) -> None:
    manifest["schema"]["file"] = "../schema.json"
    _assert_fails(
        _validate(released, manifest), "[names.schema.json] names.json/schema/file"
    )


def test_nam_004_03_variant_property_not_a_key_fails_and_names_entry(
    released: dict[str, Any], manifest: dict[str, Any]
) -> None:
    union = _entry(manifest, "union")
    variant = union["variants"][0]
    variant["property"] = "no-such-property"
    _assert_fails(
        _validate(released, manifest),
        f"{union['name']}: no-such-property is not a property of the branch "
        f"{variant['type']}",
    )


def test_variant_property_of_other_branch_fails(
    released: dict[str, Any], manifest: dict[str, Any]
) -> None:
    """A property of the other branch only is not a key of this branch."""
    union = next(
        t
        for t in manifest["types"]
        if t["kind"] == "union" and t["name"] == "CatalogGroup"
    )
    first, second = union["variants"][0], union["variants"][1]
    first["property"] = second["property"]
    _assert_fails(
        _validate(released, manifest),
        f"{second['property']} is not a property of the branch {first['type']}",
    )


def test_document_body_field_not_a_key_fails(
    released: dict[str, Any], manifest: dict[str, Any]
) -> None:
    document = _entry(manifest, "document")
    document["body-field"] = "no-such-field"
    _assert_fails(
        _validate(released, manifest),
        f"{document['name']}: no-such-field is not a property of the wrapper",
    )


def test_json_schema_failure_stops_validation(
    released: dict[str, Any], manifest: dict[str, Any]
) -> None:
    manifest["types"][0]["name"] = "Bad-Name"
    manifest["oscal-release"] = "1.2.4"
    failures = _validate(
        released, manifest, schema_bytes=released["schema_bytes"] + b"\n"
    )
    assert failures
    assert all(f.startswith("[names.schema.json]") for f in failures)


def test_every_failure_is_reported(
    released: dict[str, Any], manifest: dict[str, Any]
) -> None:
    manifest["oscal-release"] = "1.2.4"
    manifest["types"][0]["sites"] = ["#/definitions/missing"]
    manifest["types"][2]["name"] = manifest["types"][1]["name"]
    failures = _validate(released, manifest)
    _assert_fails(
        failures, "oscal-release", "does not resolve", "occurs more than once"
    )


def test_schema_that_is_not_json_is_reported(
    released: dict[str, Any], manifest: dict[str, Any]
) -> None:
    bad = b"{not json"
    manifest["schema"]["sha256"] = hashlib.sha256(bad).hexdigest()
    _assert_fails(
        _validate(released, manifest, schema_bytes=bad), "the schema is not valid JSON"
    )


# ---------------------------------------------------------------------------
# parse_pointer and resolve_pointer


@pytest.mark.parametrize(
    ("pointer", "tokens"),
    [
        ("#", []),
        ("#/", [""]),
        ("#/a~1b/c~0d", ["a/b", "c~d"]),
        ("#/a~01", ["a~1"]),
        (
            "#/definitions/oscal-complete-oscal-metadata:hash",
            [
                "definitions",
                "oscal-complete-oscal-metadata:hash",
            ],
        ),
    ],
)
def test_parse_pointer_decodes_tokens(pointer: str, tokens: list[str]) -> None:
    assert manifest_mod.parse_pointer(pointer) == tokens


@pytest.mark.parametrize("pointer", ["", "/a", "#a", "#/a%20b", "#/~2", "#/a~"])
def test_parse_pointer_rejects_malformed_pointer(pointer: str) -> None:
    assert manifest_mod.parse_pointer(pointer) is None


@pytest.mark.parametrize(
    "pointer",
    ["#/constructor", "#/__proto__", "#/__class__", "#/a/keys", "#/a/__dict__"],
)
def test_resolve_pointer_does_not_resolve_inherited_members(pointer: str) -> None:
    assert manifest_mod.resolve_pointer({"a": {}}, pointer) is None


def test_resolve_pointer_resolves_own_proto_and_constructor_keys() -> None:
    root = {"__proto__": {"x": 1}, "constructor": True}
    assert manifest_mod.resolve_pointer(root, "#/__proto__") == {"x": 1}
    assert manifest_mod.resolve_pointer(root, "#/constructor") is True


def test_resolve_pointer_resolves_escaped_keys() -> None:
    root = {"a~b": {}, "a/b": {}}
    assert manifest_mod.resolve_pointer(root, "#/a~0b") == {}
    assert manifest_mod.resolve_pointer(root, "#/a~1b") == {}


@pytest.mark.parametrize(
    ("pointer", "resolves"),
    [("#/a/1", True), ("#/a/01", False), ("#/a/2", False), ("#/a/-1", False)],
)
def test_resolve_pointer_array_index_rules(pointer: str, resolves: bool) -> None:
    root = {"a": [{}, {}]}
    assert (manifest_mod.resolve_pointer(root, pointer) is not None) is resolves


@pytest.mark.parametrize("target", [1, "s", None, []])
def test_resolve_pointer_rejects_non_schema_target(target: object) -> None:
    assert manifest_mod.resolve_pointer({"a": target}, "#/a") is None


def test_resolve_pointer_root_and_malformed() -> None:
    root = {"a": {}}
    assert manifest_mod.resolve_pointer(root, "#") == root
    assert manifest_mod.resolve_pointer(root, "#a") is None
    assert manifest_mod.resolve_pointer(root, "#/a/b") is None


# ---------------------------------------------------------------------------
# load_validated_manifest


def _write_artifact(root: Path, manifest: object, names_schema: object) -> Any:
    """Write an artifact layout under ``root`` and return its ``ArtifactPaths``."""
    paths = pin.artifact_paths(root)
    paths.names.parent.mkdir(parents=True)
    paths.names.write_text(json.dumps(manifest), encoding="utf-8")
    paths.names_schema.write_text(json.dumps(names_schema), encoding="utf-8")
    return paths


def test_load_validated_manifest_raises_with_every_failure(
    tmp_path: Path, released: dict[str, Any], manifest: dict[str, Any]
) -> None:
    manifest["oscal-release"] = "1.2.4"
    manifest["types"][0]["sites"] = ["#/definitions/missing"]
    paths = _write_artifact(tmp_path, manifest, released["names_schema"])
    with pytest.raises(manifest_mod.ManifestError) as info:
        manifest_mod.load_validated_manifest(paths)
    assert len(info.value.failures) == 2
    message = str(info.value)
    assert str(paths.names) in message
    assert "oscal-release" in message
    assert "does not resolve" in message


def test_load_validated_manifest_rejects_unreadable_manifest(
    tmp_path: Path, released: dict[str, Any]
) -> None:
    paths = _write_artifact(tmp_path, {}, released["names_schema"])
    paths.names.write_bytes(b"{not json")
    with pytest.raises(
        manifest_mod.ManifestError, match=re.escape("cannot read names.json")
    ):
        manifest_mod.load_validated_manifest(paths)


def test_load_validated_manifest_rejects_missing_schema(
    tmp_path: Path, released: dict[str, Any], manifest: dict[str, Any]
) -> None:
    paths = _write_artifact(tmp_path, manifest, released["names_schema"])
    with pytest.raises(manifest_mod.ManifestError, match="cannot read the schema"):
        manifest_mod.load_validated_manifest(
            paths, schema_path=tmp_path / "missing.json"
        )


def test_load_validated_manifest_rejects_non_object_names_schema(
    tmp_path: Path, manifest: dict[str, Any]
) -> None:
    paths = _write_artifact(tmp_path, manifest, [])
    with pytest.raises(manifest_mod.ManifestError, match="is not a JSON object"):
        manifest_mod.load_validated_manifest(paths)


def test_manifest_error_is_value_error() -> None:
    error = manifest_mod.ManifestError("names.json", ["a", "b"])
    assert isinstance(error, ValueError)
    assert error.failures == ["a", "b"]
    assert "(2 failures)" in str(error)
