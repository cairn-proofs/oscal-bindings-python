"""Tests for ``scripts/hoist_names.py``: the hoisted copy of the vendored schema.

The released manifest of the pinned spec artifact is hoisted into the vendored
schema. The tests check that each site becomes a ``$ref`` to a definition with
its manifest name, that no old site key stays, that the output is the same on
each run, that the guards fail on a changed copy, and that the hoisted copy
accepts and rejects the same documents as the vendored schema.
"""

from __future__ import annotations

import copy
import json
from typing import TYPE_CHECKING, Any

import jsonschema_rs
import pytest
from support.corpus import AWS_CORPUS, NIST_CORPUS, load_corpus_docs
from support.scripts import load_script
from support.spec_artifact import ensure_spec_artifact

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

hoist_mod = load_script("hoist_names")
manifest_mod = load_script("manifest")
pin = load_script("spec_artifact")

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
def vendored() -> dict[str, Any]:
    schema: dict[str, Any] = json.loads(manifest_mod.VENDORED_SCHEMA.read_bytes())
    return schema


@pytest.fixture(scope="module")
def hoisted(
    vendored: dict[str, Any], released_manifest: dict[str, Any]
) -> dict[str, Any]:
    result: dict[str, Any] = hoist_mod.hoist(vendored, released_manifest)
    return result


@pytest.fixture
def schema(vendored: dict[str, Any]) -> dict[str, Any]:
    """A deep copy of the vendored schema that a test can change."""
    return copy.deepcopy(vendored)


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
    """Walk ``tokens`` through ``root`` as a reader of the vendored pointer would.

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
    hoisted: dict[str, Any], vendored: dict[str, Any], released_manifest: dict[str, Any]
) -> None:
    old = _old_site_keys(released_manifest)
    kept = [key for key in vendored["definitions"] if key not in old]
    for key in kept:
        assert key in hoisted["definitions"], key
    assert (
        hoisted["definitions"]["TokenDatatype"]
        == vendored["definitions"]["TokenDatatype"]
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
    hoisted: dict[str, Any], vendored: dict[str, Any]
) -> None:
    """D6: the closed enum becomes a ``$ref`` with the property docs beside it."""
    original = vendored["definitions"][HOW_MANY.rsplit("/", maxsplit=1)[-1]][
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
    hoisted: dict[str, Any], vendored: dict[str, Any]
) -> None:
    """An inline object property keeps its ``title`` and ``description``."""
    original = vendored["definitions"]["oscal-complete-oscal-ap:assessment-plan"][
        "properties"
    ]["local-definitions"]
    prop = hoisted["definitions"]["AssessmentPlan"]["properties"]["local-definitions"]
    assert prop == {
        "$ref": "#/definitions/AssessmentPlanLocalDefinitions",
        "title": original["title"],
        "description": original["description"],
    }
    definition = hoisted["definitions"]["AssessmentPlanLocalDefinitions"]
    assert definition["description"] == original["description"]


def test_union_variant_takes_the_union_description(
    hoisted: dict[str, Any], vendored: dict[str, Any]
) -> None:
    original = vendored["definitions"]["oscal-complete-oscal-catalog:group"]
    assert "description" not in original["anyOf"][0]
    for variant in ("CatalogGroupWithControls", "CatalogGroupWithGroups"):
        definition = hoisted["definitions"][variant]
        assert definition["description"] == original["description"], variant
        assert "title" not in definition, variant


def test_document_wrapper_takes_no_root_docs(
    hoisted: dict[str, Any], vendored: dict[str, Any]
) -> None:
    """A branch of the root ``oneOf`` keeps only its own annotations."""
    for i, branch in enumerate(hoisted["oneOf"]):
        name = branch["$ref"].rsplit("/", maxsplit=1)[-1]
        original = vendored["oneOf"][i]
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
    vendored: dict[str, Any], released_manifest: dict[str, Any]
) -> None:
    first = hoist_mod.hoist(copy.deepcopy(vendored), copy.deepcopy(released_manifest))
    second = hoist_mod.hoist(copy.deepcopy(vendored), copy.deepcopy(released_manifest))
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


def test_merge_of_different_bodies_fails_and_names_both_sites(
    schema: dict[str, Any], manifest: dict[str, Any]
) -> None:
    """MDL-007.06: two merged places with different fields abort the hoist."""
    first, second = _entry(manifest, "MetadataPartyExternalId")["sites"]
    node = manifest_mod.resolve_pointer(schema, second)
    node["properties"]["extra"] = {"$ref": "#/definitions/StringDatatype"}
    with pytest.raises(HoistError) as info:
        hoist_mod.hoist(schema, manifest)
    (failure,) = info.value.failures
    assert first in failure
    assert second in failure
    assert "/properties/extra" in failure


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
    with pytest.raises(HoistError, match="no-such-definition does not resolve"):
        hoist_mod.hoist(schema, manifest)


def test_name_equal_to_a_scalar_key_fails(
    schema: dict[str, Any], manifest: dict[str, Any]
) -> None:
    _entry(manifest, "HashAlgorithm")["name"] = "TokenDatatype"
    with pytest.raises(HoistError, match="TokenDatatype occurs more than once"):
        hoist_mod.hoist(schema, manifest)


def test_schema_without_definitions_fails(manifest: dict[str, Any]) -> None:
    with pytest.raises(HoistError, match="no definitions"):
        hoist_mod.hoist({"oneOf": []}, manifest)


# ---------------------------------------------------------------------------
# 2.3 The hoisted copy accepts and rejects the same documents


def _validators(
    vendored: dict[str, Any], hoisted: dict[str, Any], *, formats: bool
) -> tuple[Any, Any]:
    return (
        jsonschema_rs.Draft7Validator(vendored, validate_formats=formats),
        jsonschema_rs.Draft7Validator(hoisted, validate_formats=formats),
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
    paths: Any, vendored: dict[str, Any], hoisted: dict[str, Any], *, formats: bool
) -> None:
    documents, skipped = _artifact_documents(paths)
    # The two files that a JSON Schema cannot read.
    assert sorted(skipped) == ["invalid/invalid-utf8.json", "invalid/not-json.json"]
    before, after = _validators(vendored, hoisted, formats=formats)
    results = {name: before.is_valid(doc) for name, doc in documents.items()}
    differ = [
        name for name, doc in documents.items() if after.is_valid(doc) != results[name]
    ]
    assert differ == []
    assert all(results[n] for n in documents if n.startswith("valid/"))
    assert any(not results[n] for n in documents if n.startswith("invalid/"))


def test_remote_corpora_validate_the_same(
    vendored: dict[str, Any], hoisted: dict[str, Any]
) -> None:
    """Every NIST and AWS corpus document gets the same result from both schemas."""
    docs = [*load_corpus_docs(NIST_CORPUS), *load_corpus_docs(AWS_CORPUS)]
    assert docs
    before, after = _validators(vendored, hoisted, formats=False)
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
    paths: Any, vendored: dict[str, Any], hoisted: dict[str, Any]
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
    before, after = _validators(vendored, hoisted, formats=False)
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
    vendored: dict[str, Any],
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
    before, after = _validators(vendored, hoisted, formats=False)
    assert before.is_valid(catalog) is valid
    assert after.is_valid(catalog) is valid
