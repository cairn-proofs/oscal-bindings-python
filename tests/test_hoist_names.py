"""Tests for ``scripts/hoist_names.py``: the hoisted copy of the artifact schema.

The released manifest of the pinned spec artifact is hoisted into the artifact
schema. The tests check that each site becomes a ``$ref`` to a definition with
its manifest name, that no old site key stays, that the output is the same on
each run, that the guards fail on a changed copy, and that the hoisted copy
accepts and rejects the same documents as the artifact schema.
"""

from __future__ import annotations

import copy
import enum
import importlib
import json
import types
from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)

import jsonschema_rs
import pytest
from pydantic import BaseModel
from pydantic.fields import FieldInfo
from support.corpus import AWS_CORPUS, NIST_CORPUS, load_corpus_docs
from support.scripts import load_script
from support.spec_artifact import ensure_spec_artifact

from oscal_bindings.v1 import models

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator
    from pathlib import Path

hoist_mod = load_script("hoist_names")
manifest_mod = load_script("manifest")
pin = load_script("spec_artifact")
translate = load_script("regex_translation").translate

HoistError = hoist_mod.HoistError

HOW_MANY = "#/definitions/oscal-complete-oscal-control-common:parameter-selection"
HOW_MANY_SITE = f"{HOW_MANY}/properties/how-many/allOf/1"
HASH_KEY = "oscal-complete-oscal-metadata:hash"
# The size limit of a remote corpus document that the mutation test changes.
MUTATED_REMOTE_MAX_BYTES = 64 * 1024


@pytest.fixture(scope="module")
def paths() -> Any:
    return pin.artifact_paths(ensure_spec_artifact())


@pytest.fixture(scope="module")
def released_manifest(paths: Any) -> dict[str, Any]:
    manifest: dict[str, Any] = manifest_mod.load_validated_manifest(paths)
    return manifest


@pytest.fixture(scope="module")
def artifact_schema(paths: Any) -> dict[str, Any]:
    schema: dict[str, Any] = json.loads(paths.schema.read_bytes())
    return schema


@pytest.fixture(scope="module")
def hoisted(
    artifact_schema: dict[str, Any], released_manifest: dict[str, Any]
) -> dict[str, Any]:
    result: dict[str, Any] = hoist_mod.hoist(artifact_schema, released_manifest)
    return result


@pytest.fixture
def schema(artifact_schema: dict[str, Any]) -> dict[str, Any]:
    """A deep copy of the artifact schema that a test can change."""
    return copy.deepcopy(artifact_schema)


@pytest.fixture
def manifest(released_manifest: dict[str, Any]) -> dict[str, Any]:
    """A deep copy of the released manifest that a test can change."""
    return copy.deepcopy(released_manifest)


def _entries(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [t for t in manifest["types"] if t["kind"] != "document-union"]


def _entry(manifest: dict[str, Any], name: str) -> dict[str, Any]:
    entry: dict[str, Any] = next(t for t in manifest["types"] if t["name"] == name)
    return entry


def _tokens(pointer: str) -> list[str]:
    tokens: list[str] | None = manifest_mod.parse_pointer(pointer)
    assert tokens is not None, pointer
    return tokens


def _definition_key(pointer: str) -> str | None:
    tokens = _tokens(pointer)
    return tokens[1] if len(tokens) == 2 and tokens[0] == "definitions" else None


def _old_site_keys(manifest: dict[str, Any]) -> dict[str, str]:
    """Map each old definition key that is a site to the name of its entry."""
    return {
        key: entry["name"]
        for entry in _entries(manifest)
        for site in entry["sites"]
        if (key := _definition_key(site)) is not None
    }


def _refs(node: object) -> Iterator[str]:
    if isinstance(node, list):
        for item in node:
            yield from _refs(item)
    elif isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str):
            yield ref
        for value in node.values():
            yield from _refs(value)


def _follow(root: dict[str, Any], tokens: list[str], renamed: dict[str, str]) -> Any:
    """Walk ``tokens`` through ``root`` as a reader of the original pointer would.

    A node that is a ``$ref`` and has no key for the next token is followed to
    its definition. An old site key of ``definitions`` is read under its new
    name.
    """
    node: Any = root
    for depth, token in enumerate(tokens):
        if depth == 1 and tokens[0] == "definitions":
            token = renamed.get(token, token)  # noqa: PLW2901
        while isinstance(node, dict) and token not in node and "$ref" in node:
            node = _follow(root, _tokens(node["$ref"]), renamed)
        node = node[int(token)] if isinstance(node, list) else node[token]
    return node


# ---------------------------------------------------------------------------
# 2.1 Every site becomes a $ref; no old site key stays; stable output


def test_every_entry_is_a_definition(
    hoisted: dict[str, Any], released_manifest: dict[str, Any]
) -> None:
    definitions = hoisted["definitions"]
    missing = [
        e["name"] for e in _entries(released_manifest) if e["name"] not in definitions
    ]
    assert missing == []
    assert "OscalDocument" not in definitions


def test_every_site_becomes_a_ref(
    hoisted: dict[str, Any], released_manifest: dict[str, Any]
) -> None:
    """Each inline site, read through the hoisted copy, is a ``$ref`` to its name.

    A closed-enum site is the enum branch, and its ``allOf`` object holds the
    ``$ref``. A definition site is checked through the rename of its key.
    """
    renamed = _old_site_keys(released_manifest)
    wrong: list[str] = []
    checked = 0
    for entry in _entries(released_manifest):
        expected = f"#/definitions/{entry['name']}"
        for site in entry["sites"]:
            if _definition_key(site) is not None:
                continue
            tokens = _tokens(site)
            if entry.get("closed") is True:
                tokens = tokens[:-2]
            node = _follow(hoisted, tokens, renamed)
            checked += 1
            if not isinstance(node, dict) or node.get("$ref") != expected:
                wrong.append(f"{site}: {node!r:.120}")
    assert wrong == []
    assert checked > 0


def test_definition_sites_are_renamed(
    hoisted: dict[str, Any], released_manifest: dict[str, Any]
) -> None:
    renamed = _old_site_keys(released_manifest)
    assert renamed[HASH_KEY] == "Hash"
    left = [key for key in renamed if key in hoisted["definitions"]]
    assert left == []
    for key, name in renamed.items():
        definition = hoisted["definitions"][name]
        if "$id" in definition:
            assert definition["$id"] == f"#/definitions/{name}", key


def test_no_ref_targets_an_old_site_key(
    hoisted: dict[str, Any], released_manifest: dict[str, Any]
) -> None:
    old = {f"#/definitions/{key}" for key in _old_site_keys(released_manifest)}
    refs = list(_refs(hoisted))
    assert [ref for ref in refs if ref in old] == []
    unresolved = [r for r in refs if manifest_mod.resolve_pointer(hoisted, r) is None]
    assert unresolved == []


def test_scalar_definitions_keep_their_keys(
    hoisted: dict[str, Any],
    artifact_schema: dict[str, Any],
    released_manifest: dict[str, Any],
) -> None:
    old = _old_site_keys(released_manifest)
    kept = [key for key in artifact_schema["definitions"] if key not in old]
    for key in kept:
        assert key in hoisted["definitions"], key
    assert (
        hoisted["definitions"]["TokenDatatype"]
        == artifact_schema["definitions"]["TokenDatatype"]
    )


def test_root_one_of_is_document_refs(
    hoisted: dict[str, Any], released_manifest: dict[str, Any]
) -> None:
    by_site = {
        e["sites"][0]: e["name"]
        for e in released_manifest["types"]
        if e["kind"] == "document"
    }
    expected = [
        {"$ref": f"#/definitions/{by_site[f'#/oneOf/{i}']}"}
        for i in range(len(hoisted["oneOf"]))
    ]
    assert hoisted["oneOf"] == expected
    assert len(expected) == 8


def test_union_definition_is_any_of_refs(hoisted: dict[str, Any]) -> None:
    group = hoisted["definitions"]["CatalogGroup"]
    assert {b["$ref"] for b in group["anyOf"]} == {
        "#/definitions/CatalogGroupWithControls",
        "#/definitions/CatalogGroupWithGroups",
    }
    assert group["title"] == "Control Group"


def test_single_or_many_is_hoisted(hoisted: dict[str, Any]) -> None:
    mapping_collection = hoisted["definitions"]["MappingCollection"]
    assert mapping_collection["properties"]["mappings"] == {
        "$ref": "#/definitions/MappingCollectionMappings"
    }
    assert "anyOf" in hoisted["definitions"]["MappingCollectionMappings"]


def test_closed_enum_replaces_the_all_of(
    hoisted: dict[str, Any], artifact_schema: dict[str, Any]
) -> None:
    """D6: the closed enum becomes a ``$ref`` with the property docs beside it."""
    original = artifact_schema["definitions"][HOW_MANY.rsplit("/", maxsplit=1)[-1]][
        "properties"
    ]["how-many"]
    prop = hoisted["definitions"]["ParameterSelection"]["properties"]["how-many"]
    assert prop == {
        "$ref": "#/definitions/ParameterSelectionHowMany",
        "title": original["title"],
        "description": original["description"],
    }
    assert hoisted["definitions"]["ParameterSelectionHowMany"] == {
        "title": original["title"],
        "description": original["description"],
        "enum": ["one", "one-or-more"],
    }


def test_open_enum_keeps_its_base(hoisted: dict[str, Any]) -> None:
    prop = hoisted["definitions"]["Hash"]["properties"]["algorithm"]
    assert prop["anyOf"] == [
        {"$ref": "#/definitions/StringDatatype"},
        {"$ref": "#/definitions/HashAlgorithm"},
    ]
    algorithm = hoisted["definitions"]["HashAlgorithm"]
    assert algorithm["description"] == prop["description"]
    assert "SHA-256" in algorithm["enum"]


def test_property_site_keeps_its_docs_beside_the_ref(
    hoisted: dict[str, Any], artifact_schema: dict[str, Any]
) -> None:
    """An inline object property keeps its ``title`` and ``description``."""
    original = artifact_schema["definitions"][
        "oscal-complete-oscal-ap:assessment-plan"
    ]["properties"]["local-definitions"]
    prop = hoisted["definitions"]["AssessmentPlan"]["properties"]["local-definitions"]
    assert prop == {
        "$ref": "#/definitions/AssessmentPlanLocalDefinitions",
        "title": original["title"],
        "description": original["description"],
    }
    definition = hoisted["definitions"]["AssessmentPlanLocalDefinitions"]
    assert definition["description"] == original["description"]


def test_union_variant_takes_the_union_description(
    hoisted: dict[str, Any], artifact_schema: dict[str, Any]
) -> None:
    original = artifact_schema["definitions"]["oscal-complete-oscal-catalog:group"]
    assert "description" not in original["anyOf"][0]
    for variant in ("CatalogGroupWithControls", "CatalogGroupWithGroups"):
        definition = hoisted["definitions"][variant]
        assert definition["description"] == original["description"], variant
        assert "title" not in definition, variant


def test_document_wrapper_takes_no_root_docs(
    hoisted: dict[str, Any], artifact_schema: dict[str, Any]
) -> None:
    """A branch of the root ``oneOf`` keeps only its own annotations."""
    for i, branch in enumerate(hoisted["oneOf"]):
        name = branch["$ref"].rsplit("/", maxsplit=1)[-1]
        original = artifact_schema["oneOf"][i]
        definition = hoisted["definitions"][name]
        assert definition.get("description") == original.get("description"), name


def test_hoist_does_not_change_its_inputs(
    schema: dict[str, Any], manifest: dict[str, Any]
) -> None:
    schema_before = json.dumps(schema)
    manifest_before = json.dumps(manifest)
    hoist_mod.hoist(schema, manifest)
    assert json.dumps(schema) == schema_before
    assert json.dumps(manifest) == manifest_before


def test_two_hoists_are_identical(
    artifact_schema: dict[str, Any], released_manifest: dict[str, Any]
) -> None:
    first = hoist_mod.hoist(
        copy.deepcopy(artifact_schema), copy.deepcopy(released_manifest)
    )
    second = hoist_mod.hoist(
        copy.deepcopy(artifact_schema), copy.deepcopy(released_manifest)
    )
    assert hoist_mod.dumps(first) == hoist_mod.dumps(second)
    assert hoist_mod.dumps(first).endswith("}\n")


def test_main_writes_byte_identical_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(hoist_mod, "ensure_spec_artifact", ensure_spec_artifact)
    output = tmp_path / "nested" / "oscal_complete_schema.json"
    assert hoist_mod.main(["--output", str(output)]) == 0
    first = output.read_bytes()
    assert hoist_mod.main(["--output", str(output)]) == 0
    assert output.read_bytes() == first
    assert "hoisted definitions" in capsys.readouterr().out


def _copy_artifact(paths: Any, root: Path, schema_bytes: bytes) -> None:
    """Write the manifest files of ``paths`` and ``schema_bytes`` under ``root``."""
    copied = pin.artifact_paths(root)
    for source, target in (
        (paths.names, copied.names),
        (paths.names_schema, copied.names_schema),
    ):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    copied.schema.parent.mkdir(parents=True)
    copied.schema.write_bytes(schema_bytes)


def test_main_reads_the_artifact_schema_one_time(
    paths: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The manifest check hashes the bytes that the hoist parses: one read."""
    reads: list[Path] = []
    read = hoist_mod.read_schema_bytes

    def counting_read(path: Path) -> bytes:
        reads.append(path)
        data: bytes = read(path)
        return data

    parsed: list[object] = []
    hoist = hoist_mod.hoist

    def recording_hoist(schema: dict[str, Any], manifest: dict[str, Any]) -> Any:
        parsed.append(copy.deepcopy(schema))
        return hoist(schema, manifest)

    monkeypatch.setattr(hoist_mod, "ensure_spec_artifact", ensure_spec_artifact)
    monkeypatch.setattr(hoist_mod, "read_schema_bytes", counting_read)
    monkeypatch.setattr(hoist_mod, "hoist", recording_hoist)
    assert hoist_mod.main(["--output", str(tmp_path / "out.json")]) == 0
    assert reads == [paths.schema]
    assert parsed == [json.loads(paths.schema.read_bytes())]


def test_main_checks_the_bytes_that_it_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D1 item 2: the manifest check gets the one bytes object that main read."""
    read_bytes: list[bytes] = []
    read = hoist_mod.read_schema_bytes

    def recording_read(path: Path) -> bytes:
        data: bytes = read(path)
        read_bytes.append(data)
        return data

    checked: list[object] = []
    load = hoist_mod.load_validated_manifest

    def recording_load(paths: Any, **kwargs: Any) -> Any:
        checked.append(kwargs.get("schema_bytes"))
        return load(paths, **kwargs)

    monkeypatch.setattr(hoist_mod, "ensure_spec_artifact", ensure_spec_artifact)
    monkeypatch.setattr(hoist_mod, "read_schema_bytes", recording_read)
    monkeypatch.setattr(hoist_mod, "load_validated_manifest", recording_load)
    assert hoist_mod.main(["--output", str(tmp_path / "out.json")]) == 0
    assert len(read_bytes) == 1
    assert len(checked) == 1
    assert checked[0] is read_bytes[0]


def test_main_rejects_an_artifact_schema_with_another_hash(
    paths: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """NAM-002.03: a schema whose sha256 differs from ``schema.sha256`` fails."""
    root = tmp_path / "artifact"
    _copy_artifact(paths, root, paths.schema.read_bytes() + b"\n")
    monkeypatch.setattr(hoist_mod, "ensure_spec_artifact", lambda: root)
    output = tmp_path / "out.json"
    assert hoist_mod.main(["--output", str(output)]) == 1
    assert not output.exists()
    assert "schema.sha256" in capsys.readouterr().out


def test_main_rejects_a_missing_artifact_schema(
    paths: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "artifact"
    _copy_artifact(paths, root, b"{}")
    pin.artifact_paths(root).schema.unlink()
    monkeypatch.setattr(hoist_mod, "ensure_spec_artifact", lambda: root)
    output = tmp_path / "out.json"
    assert hoist_mod.main(["--output", str(output)]) == 1
    assert not output.exists()
    assert "cannot read the schema" in capsys.readouterr().out


def test_main_reports_an_artifact_failure_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    corpus_error = load_script("pinned_archive").CorpusError

    def fail() -> None:
        msg = "Example: the artifact could not be fetched"
        raise corpus_error(msg)

    monkeypatch.setattr(hoist_mod, "ensure_spec_artifact", fail)
    output = tmp_path / "out.json"
    assert hoist_mod.main(["--output", str(output)]) == 1
    assert not output.exists()
    assert "could not be fetched" in capsys.readouterr().out


def test_main_reports_a_failure_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail(_schema: object, _manifest: object) -> None:
        raise HoistError(["Example: the body at #/a differs from the body at #/b"])

    monkeypatch.setattr(hoist_mod, "ensure_spec_artifact", ensure_spec_artifact)
    monkeypatch.setattr(hoist_mod, "hoist", fail)
    output = tmp_path / "out.json"
    assert hoist_mod.main(["--output", str(output)]) == 1
    assert not output.exists()
    assert "Example: the body at #/a" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# 2.1 Merge comparison: annotations do not count


def test_merge_ignores_title_and_description(
    schema: dict[str, Any], manifest: dict[str, Any]
) -> None:
    entry = _entry(manifest, "MetadataPartyExternalId")
    first, second = entry["sites"]
    node = manifest_mod.resolve_pointer(schema, second)
    node["description"] = "A different description."
    node["title"] = "A different title"
    result = hoist_mod.hoist(schema, manifest)
    original = manifest_mod.resolve_pointer(schema, first)
    assert (
        result["definitions"]["MetadataPartyExternalId"]["description"]
        == (original["description"])
    )


# ---------------------------------------------------------------------------
# 2.2 Guards


@pytest.mark.spec("MDL-021.03")
def test_merge_of_different_bodies_fails_and_names_both_sites(
    schema: dict[str, Any], manifest: dict[str, Any]
) -> None:
    """MDL-021.03: two merged places with different fields abort the hoist."""
    first, second = _entry(manifest, "MetadataPartyExternalId")["sites"]
    node = manifest_mod.resolve_pointer(schema, second)
    node["properties"]["extra"] = {"$ref": "#/definitions/StringDatatype"}
    with pytest.raises(HoistError) as info:
        hoist_mod.hoist(schema, manifest)
    (failure,) = info.value.failures
    assert first in failure
    assert second in failure
    assert "/properties/extra" in failure


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ({"a/b": {"x": 1}}, {"a/b": {"x": 2}}, "/a~1b/x"),
        ({"a~b": [1, {"c/d": 1}]}, {"a~b": [1, {"c/d": 2}]}, "/a~0b/1/c~1d"),
        ({"a/b": 1}, {}, "/a~1b"),
        ({}, {"a/b": 1}, "/a~1b"),
    ],
)
def test_first_difference_escapes_each_key(
    left: dict[str, Any], right: dict[str, Any], expected: str
) -> None:
    assert hoist_mod._first_difference(left, right) == expected  # noqa: SLF001


def test_explicit_merge_of_unrelated_sites_reports_every_failure(
    schema: dict[str, Any], manifest: dict[str, Any]
) -> None:
    """A manifest that merges unrelated types fails once per offending site."""
    hash_entry = _entry(manifest, "Hash")
    link = _entry(manifest, "Link")
    prop = _entry(manifest, "Property")
    hash_entry["sites"] += link["sites"] + prop["sites"]
    manifest["types"] = [t for t in manifest["types"] if t not in (link, prop)]
    with pytest.raises(HoistError) as info:
        hoist_mod.hoist(schema, manifest)
    failures = info.value.failures
    assert len(failures) == 2
    for site in (*link["sites"], *prop["sites"]):
        assert any(site in f and hash_entry["sites"][0] in f for f in failures), site


def test_closed_enum_value_rejected_by_base_fails_and_names_the_site(
    schema: dict[str, Any], manifest: dict[str, Any]
) -> None:
    """A value with a space is not a token, so the closed enum would widen it."""
    branch = manifest_mod.resolve_pointer(schema, HOW_MANY_SITE)
    branch["enum"].append("one or more")
    with pytest.raises(HoistError) as info:
        hoist_mod.hoist(schema, manifest)
    (failure,) = info.value.failures
    assert HOW_MANY_SITE in failure
    assert "'one or more'" in failure
    assert "ParameterSelectionHowMany" in failure


def test_closed_enum_with_extra_constraint_fails(
    schema: dict[str, Any], manifest: dict[str, Any]
) -> None:
    holder = manifest_mod.resolve_pointer(schema, HOW_MANY_SITE.rsplit("/", 2)[0])
    holder["maxLength"] = 3
    with pytest.raises(HoistError, match="holds other constraints"):
        hoist_mod.hoist(schema, manifest)


def test_enum_site_with_wrong_combinator_fails(
    schema: dict[str, Any], manifest: dict[str, Any]
) -> None:
    """An open-enum site marked closed is not an allOf branch."""
    entry = _entry(manifest, "HashAlgorithm")
    entry["closed"] = True
    with pytest.raises(HoistError) as info:
        hoist_mod.hoist(schema, manifest)
    (failure,) = info.value.failures
    assert entry["sites"][0] in failure
    assert "allOf" in failure


def test_unresolvable_site_fails(
    schema: dict[str, Any], manifest: dict[str, Any]
) -> None:
    entry = _entry(manifest, "Hash")
    entry["sites"] = ["#/definitions/no-such-definition"]
    with pytest.raises(HoistError, match="no-such-definition' does not resolve"):
        hoist_mod.hoist(schema, manifest)


def test_name_equal_to_a_scalar_key_fails(
    schema: dict[str, Any], manifest: dict[str, Any]
) -> None:
    _entry(manifest, "HashAlgorithm")["name"] = "TokenDatatype"
    with pytest.raises(HoistError, match="'TokenDatatype' occurs more than once"):
        hoist_mod.hoist(schema, manifest)


def test_schema_without_definitions_fails(manifest: dict[str, Any]) -> None:
    with pytest.raises(HoistError, match="no definitions"):
        hoist_mod.hoist({"oneOf": []}, manifest)


# ---------------------------------------------------------------------------
# 2.3 The hoisted copy accepts and rejects the same documents


def _validators(
    artifact_schema: dict[str, Any], hoisted: dict[str, Any], *, formats: bool
) -> tuple[Any, Any]:
    """Validators of the artifact schema and of the hoisted copy.

    The hoist replaces the four hand-written datatypes with custom types that no
    schema validator reads, so the copy here gets their original definitions
    back. The comparison then covers all the other changes of the hoist.
    """
    restored = copy.deepcopy(hoisted)
    for key in hoist_mod.HAND_WRITTEN_DATATYPES:
        restored["definitions"][key] = artifact_schema["definitions"][key]
    return (
        jsonschema_rs.Draft7Validator(artifact_schema, validate_formats=formats),
        jsonschema_rs.Draft7Validator(restored, validate_formats=formats),
    )


def _artifact_documents(paths: Any) -> tuple[dict[str, object], list[str]]:
    """Return the parsed corpus documents and the names of the skipped files."""
    documents: dict[str, object] = {}
    skipped: list[str] = []
    for group in ("valid", "invalid"):
        for path in sorted((paths.corpus / "documents" / group).glob("*.json")):
            name = f"{group}/{path.name}"
            try:
                documents[name] = json.loads(path.read_bytes())
            except (UnicodeDecodeError, ValueError):
                skipped.append(name)
    return documents, skipped


@pytest.mark.parametrize("formats", [False, True], ids=["no-formats", "formats"])
def test_artifact_corpus_validates_the_same(
    paths: Any,
    artifact_schema: dict[str, Any],
    hoisted: dict[str, Any],
    *,
    formats: bool,
) -> None:
    documents, skipped = _artifact_documents(paths)
    # The two files that a JSON Schema cannot read.
    assert sorted(skipped) == ["invalid/invalid-utf8.json", "invalid/not-json.json"]
    before, after = _validators(artifact_schema, hoisted, formats=formats)
    results = {name: before.is_valid(doc) for name, doc in documents.items()}
    differ = [
        name for name, doc in documents.items() if after.is_valid(doc) != results[name]
    ]
    assert differ == []
    assert all(results[n] for n in documents if n.startswith("valid/"))
    assert any(not results[n] for n in documents if n.startswith("invalid/"))


def test_remote_corpora_validate_the_same(
    artifact_schema: dict[str, Any], hoisted: dict[str, Any]
) -> None:
    """Every NIST and AWS corpus document gets the same result from both schemas."""
    docs = [*load_corpus_docs(NIST_CORPUS), *load_corpus_docs(AWS_CORPUS)]
    assert docs
    before, after = _validators(artifact_schema, hoisted, formats=False)
    differ = []
    for doc in docs:
        instance = json.loads(doc.raw_bytes)
        if before.is_valid(instance) != after.is_valid(instance):
            differ.append(f"{doc.corpus_name}:{doc.rel_path}")
    assert differ == []


def _mutations(node: object) -> Iterator[None]:
    """Change ``node`` in place at each object and string, one at a time.

    Each object gets an unknown key, and each string becomes the empty string.
    The caller validates the document at each ``yield``. Each change is undone
    before the next one.
    """
    if isinstance(node, dict):
        node["x-unknown"] = 1
        yield
        del node["x-unknown"]
        items: list[tuple[Any, Any]] = list(node.items())
    elif isinstance(node, list):
        items = list(enumerate(node))
    else:
        return
    for key, value in items:
        if isinstance(value, str):
            node[key] = ""  # type: ignore[index]
            yield
            node[key] = value  # type: ignore[index]
        else:
            yield from _mutations(value)


def test_mutated_documents_validate_the_same(
    paths: Any, artifact_schema: dict[str, Any], hoisted: dict[str, Any]
) -> None:
    """Each one-place change of each valid document gets the same result.

    The corpus documents are all valid, so this test checks the reject side at
    each object and each string of the documents.
    """
    artifact, _ = _artifact_documents(paths)
    documents = {n: d for n, d in artifact.items() if n.startswith("valid/")}
    # The small remote documents add the shapes that the artifact corpus lacks.
    for doc in [*load_corpus_docs(NIST_CORPUS), *load_corpus_docs(AWS_CORPUS)]:
        if len(doc.raw_bytes) <= MUTATED_REMOTE_MAX_BYTES:
            documents[f"{doc.corpus_name}:{doc.rel_path}"] = json.loads(doc.raw_bytes)
    before, after = _validators(artifact_schema, hoisted, formats=False)
    checked = rejected = 0
    differ: list[str] = []
    for name, doc in documents.items():
        for _ in _mutations(doc):
            result = before.is_valid(doc)
            checked += 1
            rejected += not result
            if after.is_valid(doc) != result:
                differ.append(f"{name}: {json.dumps(doc)[:200]}")
    assert differ == []
    assert rejected > 100
    assert checked > rejected


@pytest.mark.parametrize(
    ("how_many", "valid"),
    [("one", True), ("one-or-more", True), ("many", False), ("ONE", False)],
)
def test_closed_enum_values_validate_the_same(
    paths: Any,
    artifact_schema: dict[str, Any],
    hoisted: dict[str, Any],
    how_many: str,
    *,
    valid: bool,
) -> None:
    """A parameter ``how-many`` value gets the same result from both schemas."""
    catalog = json.loads((paths.corpus / "documents/valid/catalog.json").read_bytes())
    catalog["catalog"]["params"] = [
        {
            "id": "param-1",
            "select": {"how-many": how_many, "choice": ["a", "b"]},
        }
    ]
    before, after = _validators(artifact_schema, hoisted, formats=False)
    assert before.is_valid(catalog) is valid
    assert after.is_valid(catalog) is valid


# ---------------------------------------------------------------------------
# Completeness: each string pattern and datatype of the schema reaches a model

DATATYPES = {
    "URIDatatype": "OscalUri",
    "URIReferenceDatatype": "OscalUriReference",
    "EmailAddressDatatype": "OscalEmailAddress",
    "DateTimeWithTimezoneDatatype": "OscalDateTimeWithTimezone",
}


@dataclass(frozen=True)
class Site:
    """A string value that a property of an object definition reaches.

    ``datatype`` is the definition key of one of the four datatypes when the
    ``$ref`` chain of the site reaches it. ``patterns`` holds each pattern of
    the chain, in schema form. ``is_enum`` is true when the chain holds an
    ``enum``.
    """

    owner: str
    prop: str
    datatype: str | None
    patterns: tuple[str, ...]
    is_enum: bool

    def __str__(self) -> str:
        what = self.datatype or ("enum" if self.is_enum else "pattern")
        return f"{self.owner}.{self.prop} ({what}) {list(self.patterns)}"


def _sites_of(
    definitions: dict[str, Any], node: Any, owner: str, prop: str
) -> Iterator[Site]:
    """Yield each string site of ``node``: an ``allOf`` is one, an ``anyOf`` many."""
    if not isinstance(node, dict):
        return
    for member in node.get("anyOf", node.get("oneOf", [])):
        yield from _sites_of(definitions, member, owner, prop)
    if "anyOf" in node or "oneOf" in node:
        return
    if node.get("type") == "array":
        yield from _sites_of(definitions, node.get("items"), owner, prop)
        return
    datatype: str | None = None
    patterns: list[str] = []
    is_enum = False
    is_string = False
    pending: list[Any] = [node]
    while pending:
        current = pending.pop()
        if not isinstance(current, dict):
            continue
        ref = current.get("$ref")
        if isinstance(ref, str):
            key = ref.removeprefix("#/definitions/")
            if key in DATATYPES:
                datatype = key
                is_string = True
                continue
            pending.append(definitions[key])
        is_string = is_string or current.get("type") == "string"
        is_enum = is_enum or "enum" in current
        if "pattern" in current:
            patterns.append(current["pattern"])
        pending.extend(current.get("allOf", []))
        # A member of an anyOf below an allOf is its own site.
        for alternative in current.get("anyOf", []):
            yield from _sites_of(definitions, alternative, owner, prop)
    if is_string:
        yield Site(owner, prop, datatype, tuple(patterns), is_enum)


def _schema_sites(hoisted: dict[str, Any]) -> list[Site]:
    definitions = hoisted["definitions"]
    sites: list[Site] = []
    for key, definition in definitions.items():
        # An object definition has `properties`. Some have no `type` keyword.
        if not isinstance(definition, dict) or "properties" not in definition:
            continue
        for prop, node in definition["properties"].items():
            sites.extend(_sites_of(definitions, node, key, prop))
    return sites


@dataclass(frozen=True)
class Leaf:
    """A leaf type of a model field, with the constraints that apply to it."""

    base: Any
    markers: tuple[Any, ...]
    patterns: tuple[str, ...]


def _flatten(metadata: Iterable[Any]) -> Iterator[Any]:
    for item in metadata:
        if isinstance(item, FieldInfo):
            yield from _flatten(item.metadata)
        else:
            yield item


def _leaves(annotation: Any, metadata: tuple[Any, ...] = ()) -> Iterator[Leaf]:
    """Open ``Annotated``, unions, and lists down to the leaf types.

    The metadata of an ``Annotated`` union applies to each arm, as pydantic
    applies a ``pattern`` of ``Annotated[str | None, Field(pattern=...)]`` to
    the ``str``. The metadata of a list applies to the list, not to its items.
    """
    origin = get_origin(annotation)
    if origin is Annotated:
        base, *extra = get_args(annotation)
        yield from _leaves(base, (*metadata, *extra))
    elif origin is Union or origin is types.UnionType:
        for arm in get_args(annotation):
            yield from _leaves(arm, metadata)
    elif origin is list:
        yield from _leaves(get_args(annotation)[0])
    elif annotation is not type(None):
        flat = tuple(_flatten(metadata))
        patterns = tuple(
            m.pattern for m in flat if isinstance(getattr(m, "pattern", None), str)
        )
        yield Leaf(annotation, flat, patterns)


def _is_datatype(leaf: Leaf, name: str) -> bool:
    """Whether ``leaf`` is the hand-written type ``name`` of ``_datatypes``."""
    try:
        module = importlib.import_module("oscal_bindings.v1._datatypes")
    except ImportError:
        return False
    declared = getattr(module, name, None)
    if declared is None:
        return False
    markers = get_args(declared)[1:]
    return get_args(declared)[0] is leaf.base and all(
        any(m is marker for m in leaf.markers) for marker in markers
    )


def _model_leaves(owner: str, prop: str) -> list[Leaf] | None:
    """The leaves of the field of ``owner`` with the alias ``prop``, or ``None``."""
    cls = getattr(models, owner, None)
    if not (isinstance(cls, type) and issubclass(cls, BaseModel)):
        return None
    hints = get_type_hints(cls, vars(models), include_extras=True)
    for name, info in cls.model_fields.items():
        if (info.alias or name) == prop:
            return list(_leaves(hints[name]))
    return None


def _site_is_covered(site: Site, leaves: list[Leaf]) -> bool:
    if site.datatype is not None:
        return any(_is_datatype(leaf, DATATYPES[site.datatype]) for leaf in leaves)
    if site.is_enum:
        return any(
            isinstance(leaf.base, type) and issubclass(leaf.base, enum.Enum)
            for leaf in leaves
        )
    if not site.patterns:
        return True
    expected = sorted(translate(p) for p in site.patterns)
    return any(sorted(leaf.patterns) == expected for leaf in leaves)


def test_each_string_site_of_the_schema_reaches_a_model(
    hoisted: dict[str, Any],
) -> None:
    """Design D7: a datatype site has its type, a pattern site its pattern."""
    sites = _schema_sites(hoisted)
    assert {s.datatype for s in sites} >= set(DATATYPES), "a datatype has no site"
    assert sum(1 for s in sites if s.patterns) > 100
    missing: list[str] = []
    uncovered: list[str] = []
    for site in sites:
        leaves = _model_leaves(site.owner, site.prop)
        if leaves is None:
            missing.append(str(site))
        elif not _site_is_covered(site, leaves):
            uncovered.append(str(site))
    assert missing == []
    assert sorted(set(uncovered)) == []


# ---------------------------------------------------------------------------
# 5.1 The four hand-written datatypes get a custom type


@pytest.mark.parametrize("key", sorted(hoist_mod.HAND_WRITTEN_DATATYPES))
def test_hand_written_datatype_has_its_custom_type(
    hoisted: dict[str, Any], artifact_schema: dict[str, Any], key: str
) -> None:
    original = artifact_schema["definitions"][key]
    definition = hoisted["definitions"][key]
    assert definition["customTypePath"] == hoist_mod.HAND_WRITTEN_DATATYPES[key]
    assert definition["type"] == "string"
    assert definition["description"] == original["description"]
    assert definition.get("title") == original.get("title")
    assert not {"pattern", "format", "allOf"} & set(definition)


def test_hand_written_datatypes_are_the_four_with_a_format(
    artifact_schema: dict[str, Any],
) -> None:
    assert set(hoist_mod.HAND_WRITTEN_DATATYPES) == {
        "DateTimeWithTimezoneDatatype",
        "EmailAddressDatatype",
        "URIDatatype",
        "URIReferenceDatatype",
    }
    assert all(
        "customTypePath" not in definition
        for definition in artifact_schema["definitions"].values()
    )


def test_a_schema_without_a_hand_written_datatype_fails(
    schema: dict[str, Any], manifest: dict[str, Any]
) -> None:
    del schema["definitions"]["URIDatatype"]
    with pytest.raises(HoistError) as info:
        hoist_mod.hoist(schema, manifest)
    assert any("URIDatatype" in failure for failure in info.value.failures)
