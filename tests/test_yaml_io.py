"""Tests for the optional YAML parse and serialize operations.

Covers the ``yaml-documents`` contract behavior (YML-002 to YML-011) and the
binding-local resource limits (spec ``yaml-resource-limit``). The YAML corpus
cases run from :mod:`tests.test_conformance`. These tests check the scenarios at
the unit level, including the schema-type resolver that the corpus does not
exercise in isolation.

Every test in this module runs once with libyaml's parser and once with
PyYAML's pure-Python parser (design Decision 2). The base-install and
import-path tests are in :mod:`tests.test_yaml_base_install`.
"""

from __future__ import annotations

import json
import re
import textwrap
import tracemalloc
from typing import TYPE_CHECKING, Any

import pytest
import yaml

import oscal_bindings as ob
from oscal_bindings import OscalParseError
from oscal_bindings.v1.extensions import _yaml_loader
from oscal_bindings.v1.extensions._yaml_loader import _SCHEMA, to_json_text
from oscal_bindings.v1.extensions.yaml_io import (
    ALIAS_CHAR_LIMIT,
    ALIAS_NODE_LIMIT,
    DEPTH_LIMIT,
    parse_oscal_yaml,
    parse_oscal_yaml_file,
    serialize_oscal_yaml,
)

if TYPE_CHECKING:
    from support.corpus import CorpusDoc

PARSERS = {"libyaml": yaml.CSafeLoader, "python": yaml.SafeLoader}


@pytest.fixture(autouse=True, params=sorted(PARSERS))
def yaml_parser(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> str:
    """Run each test with each event parser."""
    monkeypatch.setattr(_yaml_loader, "_LOADER", PARSERS[request.param])
    return str(request.param)


HEAD = textwrap.dedent(
    """\
    catalog:
      uuid: 7d2b6c1e-3f4a-4b5c-8d6e-9f0a1b2c3d41
      metadata:
        title: T
        last-modified: 2024-01-02T03:04:05Z
        version: "1.0"
        oscal-version: 1.2.3
    """
)

MINIMAL_CATALOG_YAML = HEAD

MINIMAL_CATALOG_JSON = json.dumps(
    {
        "catalog": {
            "uuid": "7d2b6c1e-3f4a-4b5c-8d6e-9f0a1b2c3d41",
            "metadata": {
                "title": "T",
                "last-modified": "2024-01-02T03:04:05Z",
                "version": "1.0",
                "oscal-version": "1.2.3",
            },
        }
    }
)


def _canon(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _json_value(doc: Any) -> Any:
    return json.loads(doc.model_dump_json(by_alias=True, exclude_none=True))


def _metadata(extra: str) -> Any:
    """Parse the minimal catalog with ``extra`` lines appended to its metadata."""
    doc = parse_oscal_yaml(HEAD + textwrap.indent(textwrap.dedent(extra), "    "))
    return _json_value(doc)["catalog"]["metadata"]


def _yaml_error(text: str | bytes) -> dict[str, Any]:
    """Parse ``text``, require a YAML-layer parse error, and return its entry."""
    with pytest.raises(OscalParseError) as info:
        parse_oscal_yaml(text)
    errors = info.value.errors
    assert len(errors) == 1, errors
    entry = errors[0]
    assert str(entry["type"]).startswith("yaml_"), entry
    return entry


# --- Task 2.1, 2.8: the schema-type resolver (design Decision 1) -----------


class TestSchemaResolver:
    def test_start_is_number_location(self) -> None:
        cd = _SCHEMA.field(_SCHEMA.root, "component-definition")
        components = _SCHEMA.items(_SCHEMA.field(cd, "components"))
        protocols = _SCHEMA.items(_SCHEMA.field(components, "protocols"))
        port_ranges = _SCHEMA.items(_SCHEMA.field(protocols, "port-ranges"))
        start = _SCHEMA.field(port_ranges, "start")
        assert _SCHEMA.base_type(start) in ("number", "integer")

    def test_last_modified_is_string_location(self) -> None:
        catalog = _SCHEMA.field(_SCHEMA.root, "catalog")
        metadata = _SCHEMA.field(catalog, "metadata")
        assert _SCHEMA.base_type(_SCHEMA.field(metadata, "last-modified")) == "string"

    def test_hash_algorithm_is_string_location(self) -> None:
        catalog = _SCHEMA.field(_SCHEMA.root, "catalog")
        bm = _SCHEMA.field(catalog, "back-matter")
        resources = _SCHEMA.items(_SCHEMA.field(bm, "resources"))
        rlinks = _SCHEMA.items(_SCHEMA.field(resources, "rlinks"))
        hashes = _SCHEMA.items(_SCHEMA.field(rlinks, "hashes"))
        assert _SCHEMA.base_type(_SCHEMA.field(hashes, "algorithm")) == "string"

    def test_as_is_is_boolean_location(self) -> None:
        profile = _SCHEMA.field(_SCHEMA.root, "profile")
        merge = _SCHEMA.field(profile, "merge")
        assert _SCHEMA.base_type(_SCHEMA.field(merge, "as-is")) == "boolean"

    def test_no_tie_break_decides_a_location(self) -> None:
        # The resolver takes the first union branch that declares a key, and
        # folds a multi-type location by priority. Against the pinned schema
        # neither rule may decide a result, so a pin move that makes one decide
        # fails here (design Decision 1).
        multi_type: list[str] = []
        split_key: list[str] = []
        pending: list[Any] = [_SCHEMA.root, *_SCHEMA.defs.values()]
        seen: set[int] = set()
        while pending:
            node = pending.pop()
            if isinstance(node, list):
                pending.extend(node)
                continue
            if not isinstance(node, dict) or id(node) in seen:
                continue
            seen.add(id(node))
            pending.extend(node.values())
            locations = list(node.get("properties", {}).items())
            if "items" in node:
                locations.append(("[]", node["items"]))
            for key, sub in locations:
                if len(_SCHEMA.scalar_types(sub)) > 1:
                    multi_type.append(key)
            if "anyOf" in node or "oneOf" in node:
                by_key: dict[str, set[str]] = {}
                for branch in _SCHEMA.branches(node):
                    props = _SCHEMA.deref(branch).get("properties", {})
                    for key, sub in props.items():
                        base = _SCHEMA.base_type(sub)
                        if base is not None:
                            by_key.setdefault(key, set()).add(base)
                split_key += [k for k, types in by_key.items() if len(types) > 1]
        assert not multi_type, f"locations with more than one scalar type: {multi_type}"
        assert not split_key, f"union keys with two scalar types: {split_key}"


# --- Task 2.2: scalar typing (YML-004.01 .. YML-004.10) --------------------


def _component_with_start(start: str) -> str:
    return textwrap.dedent(
        f"""\
        component-definition:
          uuid: 7d2b6c1e-3f4a-4b5c-8d6e-9f0a1b2c3d43
          metadata:
            title: T
            last-modified: 2024-01-02T03:04:05Z
            version: "1.0"
            oscal-version: 1.2.3
          components:
            - uuid: 7d2b6c1e-3f4a-4b5c-8d6e-9f0a1b2c3d44
              type: service
              title: S
              description: d
              protocols:
                - name: https
                  port-ranges:
                    - {{start: {start}, end: 443}}
        """
    )


def _profile_with_as_is(value: str) -> str:
    return textwrap.dedent(
        f"""\
        profile:
          uuid: 7d2b6c1e-3f4a-4b5c-8d6e-9f0a1b2c3d41
          metadata:
            title: T
            last-modified: 2024-01-02T03:04:05Z
            version: "1.0"
            oscal-version: 1.2.3
          imports:
            - href: https://example.com/c.json
              include-all: {{}}
          merge:
            as-is: {value}
        """
    )


START_LOC = (
    "component-definition",
    "components",
    0,
    "protocols",
    0,
    "port-ranges",
    0,
    "start",
)


class TestScalarTyping:
    def test_number_form_at_string_location_stays_string(self) -> None:
        # YML-004.01.
        assert _metadata("props: [{name: a, value: 1.0}]")["props"][0]["value"] == "1.0"

    def test_boolean_form_at_string_location_stays_string(self) -> None:
        # YML-004.03.
        assert _metadata("props: [{name: a, value: yes}]")["props"][0]["value"] == "yes"

    def test_null_forms_at_string_location(self) -> None:
        # YML-004.04: plain null, ~, and empty keep their text.
        md = _metadata(
            """\
            props:
              - {name: a, value: x, remarks: null}
              - {name: b, value: y, remarks: ~}
              - {name: c, value: z, remarks: }
            """
        )
        assert [p["remarks"] for p in md["props"]] == ["null", "~", ""]

    def test_scalar_tag_ignored_at_string_location(self) -> None:
        # YML-004.05: !!int 7 at a string location is the string "7".
        assert (
            _metadata("props: [{name: a, value: !!int 7}]")["props"][0]["value"] == "7"
        )

    def test_quoted_scalar_at_number_location_is_number(self) -> None:
        # YML-004.06.
        doc = parse_oscal_yaml(_component_with_start('"443"'))
        cd = _json_value(doc)["component-definition"]
        assert cd["components"][0]["protocols"][0]["port-ranges"][0]["start"] == 443

    @pytest.mark.parametrize("bad", ["0x1BB", "+443", "007", "1.", ".5", "1e"])
    def test_bad_number_form_is_a_located_grammar_error(self, bad: str) -> None:
        # YML-004.07, YML-004.10, YML-010.01.
        entry = _yaml_error(_component_with_start(bad))
        assert entry["type"] == "yaml_number_grammar"
        assert entry["loc"] == START_LOC
        assert entry["input"] == bad

    def test_boolean_location_rejects_non_boolean_text(self) -> None:
        # YML-004.08.
        entry = _yaml_error(_profile_with_as_is("yes"))
        assert entry["type"] == "yaml_boolean_grammar"
        assert entry["loc"] == ("profile", "merge", "as-is")

    def test_true_at_boolean_location_is_boolean(self) -> None:
        merge = _json_value(parse_oscal_yaml(_profile_with_as_is("true")))["profile"][
            "merge"
        ]
        assert merge["as-is"] is True

    def test_alias_is_read_at_its_own_location(self) -> None:
        # YML-009.01: one anchored scalar is a number at `start` and a string at
        # a property `value`.
        text = _component_with_start("&n 443") + "      props: [{name: p, value: *n}]\n"
        cd = _json_value(parse_oscal_yaml(text))["component-definition"]["components"][
            0
        ]
        assert cd["protocols"][0]["port-ranges"][0]["start"] == 443
        assert cd["props"][0]["value"] == "443"


class TestErrorEntryShape:
    def test_yaml_and_pydantic_entries_share_keys(self) -> None:
        # Task 2.7: one loop handles both kinds of entry.
        grammar = _yaml_error(_component_with_start("0x1BB"))
        with pytest.raises(OscalParseError) as info:
            parse_oscal_yaml(HEAD + "    colour: blue\n")
        pydantic_entry = info.value.errors[0]
        for entry in (grammar, pydantic_entry):
            assert isinstance(entry["type"], str)
            assert isinstance(entry["loc"], tuple)
            assert isinstance(entry["msg"], str)
            assert "input" in entry
        line = _component_with_start("0x1BB").splitlines()[15]
        assert (grammar["line"], grammar["column"]) == (16, line.index("0x1BB") + 1)


# --- Task 2.3: structure rules -----------------------------------------------


class TestStructureRules:
    def test_duplicate_key_is_parse_error(self) -> None:
        # YML-003.
        entry = _yaml_error(HEAD + "    title: B\n")
        assert entry["type"] == "yaml_duplicate_key"
        assert entry["loc"] == ("catalog", "metadata", "title")

    def test_same_text_keys_are_parse_error(self) -> None:
        # YML-003.03: a plain key and its quoted form share the same text.
        assert _yaml_error(HEAD + '    "title": B\n')["type"] == "yaml_duplicate_key"

    def test_aliased_key_with_same_text_is_parse_error(self) -> None:
        text = HEAD.replace("title: T", "title: &k title") + "    *k : B\n"
        assert _yaml_error(text)["type"] == "yaml_duplicate_key"

    def test_non_scalar_key_is_parse_error(self) -> None:
        # YML-003.02.
        assert (
            _yaml_error("catalog:\n  ? [a, b]\n  : c\n")["type"]
            == "yaml_key_not_scalar"
        )

    def test_merge_key_is_unknown_field(self) -> None:
        # YML-009.04: << is an ordinary key, so Pydantic rejects it as unknown.
        with pytest.raises(OscalParseError) as info:
            parse_oscal_yaml(HEAD + "    <<: {title: X}\n")
        assert any(e["loc"][-1] == "<<" for e in info.value.errors), info.value.errors

    def test_omap_tag_reads_as_array(self) -> None:
        # YML-009.03.
        doc = parse_oscal_yaml(
            HEAD + "  back-matter:\n    resources: !!omap\n"
            "      - uuid: 7d2b6c1e-3f4a-4b5c-8d6e-9f0a1b2c3d43\n"
        )
        assert isinstance(_json_value(doc)["catalog"]["back-matter"]["resources"], list)

    def test_alias_inside_own_anchored_node_is_parse_error(self) -> None:
        # YML-009.02.
        text = HEAD.replace("  metadata:", "  metadata: &m") + "    extra: *m\n"
        assert _yaml_error(text)["type"] == "yaml_alias_cycle"

    def test_undefined_alias_is_parse_error(self) -> None:
        assert (
            _yaml_error(HEAD + "    remarks: *nope\n")["type"] == "yaml_undefined_alias"
        )

    def test_later_anchor_redefines_an_earlier_one(self) -> None:
        # YAML 1.2: an alias refers to the most recent node with its anchor.
        md = _metadata("remarks: &r first\nprops: [{name: &r a, value: *r}]\n")
        assert md["props"][0]["value"] == "a"


# --- Task 2.4: input-stream rules (YML-002) --------------------------------


class TestStreamRules:
    def test_invalid_utf8_is_parse_error(self) -> None:
        entry = _yaml_error(b"catalog:\n  \xff\xfe\n")
        assert entry["type"] == "yaml_encoding"
        assert (entry["line"], entry["column"]) == (2, 3)

    def test_utf16_bytes_are_rejected(self) -> None:
        # YML-002.04.
        assert _yaml_error(HEAD.encode("utf-16"))["type"] == "yaml_encoding"

    def test_no_document_is_parse_error(self) -> None:
        # YML-002.03.
        assert (
            _yaml_error("# only a comment\n")["msg"] == "YAML input holds no document"
        )

    def test_two_documents_is_parse_error(self) -> None:
        # YML-002.02.
        entry = _yaml_error(HEAD + "---\n" + HEAD)
        assert entry["msg"] == "YAML input holds more than one document"

    def test_syntax_error_is_parse_error(self) -> None:
        # YML-002.01.
        assert _yaml_error("catalog: [a, b\n")["type"] == "yaml_syntax"


# --- Task 2.6: YAML 1.1 line-break characters are content -----------------

BREAKS = ["\x85", "\u2028", "\u2029"]


class TestYaml11LineBreaks:
    @pytest.mark.parametrize("ch", BREAKS)
    @pytest.mark.parametrize(
        "form",
        ["plain", "single", "double", "literal", "key"],
    )
    def test_character_is_content(self, ch: str, form: str) -> None:
        text = {
            "plain": f"a: x{ch}y\n",
            "single": f"a: 'x{ch}y'\n",
            "double": f'a: "x{ch}y"\n',
            "literal": f"a: |\n  x{ch}y\n",
            "key": f"x{ch}y: a\n",
        }[form]
        expected = {"key": {f"x{ch}y": "a"}, "literal": {"a": f"x{ch}y\n"}}.get(
            form, {"a": f"x{ch}y"}
        )
        assert json.loads(to_json_text(text)) == expected

    @pytest.mark.parametrize("ch", BREAKS)
    def test_parse_equals_the_json_path(self, ch: str) -> None:
        # YML-005: the YAML result equals the JSON result for the same value.
        text = HEAD.replace("title: T", f"title: 'a{ch}b'")
        json_text = MINIMAL_CATALOG_JSON.replace('"T"', json.dumps(f"a{ch}b"))
        assert _json_value(parse_oscal_yaml(text)) == _json_value(
            ob.parse_oscal(json_text)
        )

    def test_escape_that_names_a_private_use_character_keeps_it(self) -> None:
        text = 'a: "\\uE000"\nb: "x\x85y"\nc: "\\U0000E001"\n'
        assert json.loads(to_json_text(text)) == {
            "a": "\ue000",
            "b": "x\x85y",
            "c": "\ue001",
        }

    def test_raw_private_use_characters_survive(self) -> None:
        text = "a: \ue000\ue001\ue002\nb: x\u2028y\n"
        assert json.loads(to_json_text(text)) == {
            "a": "\ue000\ue001\ue002",
            "b": "x\u2028y",
        }

    def test_no_free_placeholder_is_parse_error(self) -> None:
        every = "".join(chr(cp) for cp in range(0xE000, 0xF900))
        entry = _yaml_error(f"a: {every}\nb: x\x85y\n")
        assert entry["type"] == "yaml_line_break_placeholder"


# --- Task 3.1, 3.2: parse operations ------------------------------------------


class TestParseOscalYaml:
    def test_parses_from_str(self) -> None:
        doc = parse_oscal_yaml(MINIMAL_CATALOG_YAML)
        assert _canon(_json_value(doc)) == _canon(json.loads(MINIMAL_CATALOG_JSON))

    def test_parses_from_bytes(self) -> None:
        doc = parse_oscal_yaml(MINIMAL_CATALOG_YAML.encode("utf-8"))
        assert _canon(_json_value(doc)) == _canon(json.loads(MINIMAL_CATALOG_JSON))

    def test_same_result_as_json_parse(self) -> None:
        # YML-005.02.
        yaml_doc = parse_oscal_yaml(MINIMAL_CATALOG_YAML)
        assert _json_value(yaml_doc) == _json_value(
            ob.parse_oscal(MINIMAL_CATALOG_JSON)
        )

    def test_unknown_field_is_parse_error(self) -> None:
        # YML-005.03 / PRS-004.
        with pytest.raises(OscalParseError):
            parse_oscal_yaml(HEAD + "    colour: blue\n")


class TestParseOscalYamlFile:
    def test_parses_existing_file(self, tmp_path) -> None:
        path = tmp_path / "catalog.yaml"
        path.write_text(MINIMAL_CATALOG_YAML, encoding="utf-8")
        assert _canon(_json_value(parse_oscal_yaml_file(path))) == _canon(
            json.loads(MINIMAL_CATALOG_JSON)
        )
        assert _json_value(parse_oscal_yaml_file(str(path)))["catalog"]

    def test_missing_file_reports_not_found(self, tmp_path) -> None:
        # YML-006 / PRS-002: not-found is distinct from the parse error.
        missing = tmp_path / "nope.yaml"
        with pytest.raises(FileNotFoundError) as info:
            parse_oscal_yaml_file(missing)
        assert str(missing) in str(info.value)
        assert not isinstance(info.value, OscalParseError)


# --- Task 3.3: serialize_oscal_yaml -------------------------------------------


def _values(value: Any) -> list[Any]:
    pending, out = [value], []
    while pending:
        v = pending.pop()
        out.append(v)
        if isinstance(v, dict):
            pending.extend(v.values())
        elif isinstance(v, list):
            pending.extend(v)
    return out


class TestSerializeOscalYaml:
    def test_version_string_survives_round_trip(self) -> None:
        # YML-008.02.
        out = serialize_oscal_yaml(
            parse_oscal_yaml(MINIMAL_CATALOG_YAML.replace('"1.0"', "1.0"))
        )
        assert (
            _json_value(parse_oscal_yaml(out))["catalog"]["metadata"]["version"]
            == "1.0"
        )

    def test_output_holds_no_null(self) -> None:
        # YML-008.03: the loaded output holds no None at any depth, including
        # for a document whose string values spell `null`.
        doc = parse_oscal_yaml(
            HEAD + "    props: [{name: a, value: null, remarks: ~}]\n"
        )
        loaded = yaml.safe_load(serialize_oscal_yaml(doc))
        assert None not in _values(loaded)

    @pytest.mark.parametrize("ch", BREAKS)
    def test_line_break_character_survives_round_trip(self, ch: str) -> None:
        doc = parse_oscal_yaml(HEAD.replace("title: T", f"title: 'a{ch}b'"))
        out = serialize_oscal_yaml(doc)
        assert ch not in out, "the character must be written as an escape"
        title = _json_value(parse_oscal_yaml(out))["catalog"]["metadata"]["title"]
        assert title == f"a{ch}b"
        assert yaml.safe_load(out)["catalog"]["metadata"]["title"] == f"a{ch}b"


# --- Tasks 4.1, 6.1, 8.1: resource limits -------------------------------------

NODE_LIMIT_MSG = re.escape(f"limit of {ALIAS_NODE_LIMIT:,} nodes")
CHAR_LIMIT_MSG = re.escape(f"limit of {ALIAS_CHAR_LIMIT:,} characters")
DEPTH_LIMIT_MSG = re.escape(f"depth limit of {DEPTH_LIMIT}")


def _wide_alias(width: int, copies: int) -> str:
    """Anchor a sequence of ``width`` scalars and repeat it ``copies`` times.

    Each copy charges ``width + 1`` nodes. The copies sit at string locations,
    so Pydantic reports one error per copy, not one per scalar.
    """
    items = ", ".join(["x"] * width)
    lines = [HEAD, f"    remarks: &w [{items}]\n", "    props:\n"]
    lines += ["      - {name: n, value: v, remarks: *w}\n" for _ in range(copies)]
    return "".join(lines)


def _scalar_alias(size: int, copies: int) -> str:
    """Anchor one scalar of ``size`` characters and repeat it ``copies`` times."""
    lines = [HEAD, f"    remarks: &s {'x' * size}\n", "    props:\n"]
    lines += ["      - {name: n, value: v, remarks: *s}\n" for _ in range(copies)]
    return "".join(lines)


def _nested_alias(levels: int, width: int = 10) -> str:
    """A billion-laughs input: each level repeats the level below ``width`` times."""
    lines = [HEAD, "    a0: &a0 [x]\n"]
    for i in range(1, levels + 1):
        refs = ", ".join([f"*a{i - 1}"] * width)
        lines.append(f"    a{i}: &a{i} [{refs}]\n")
    return "".join(lines)


def _nested(depth: int) -> str:
    """A catalog whose `remarks` holds sequences nested to node depth ``depth``.

    Three mappings hold the value of `remarks`: the root, the `catalog` value,
    and the `metadata` value. So the outermost sequence is at depth 3, and the
    innermost one is at depth ``depth``.
    """
    n = depth - 2
    return HEAD + "    remarks: " + "[" * n + "]" * n + "\n"


def _not_a_limit(text: str) -> None:
    """Parse ``text`` and require that no YAML-layer limit rejects it."""
    errors: list[Any] = []
    try:
        parse_oscal_yaml(text)
    except OscalParseError as exc:
        errors = exc.errors
    kinds = {e.get("type") for e in errors}
    assert not kinds & {"yaml_alias_budget", "yaml_depth_limit"}, errors


class TestAliasBudget:
    def test_scalar_alias_bomb_is_rejected_by_the_character_limit(self) -> None:
        # 14 KB of input repeats a 10,000-character scalar 101 times.
        text = _scalar_alias(10_000, 101)
        assert len(text) < 16_000
        with pytest.raises(OscalParseError, match=CHAR_LIMIT_MSG):
            parse_oscal_yaml(text)

    def test_large_scalar_alias_bomb_is_rejected(self) -> None:
        with pytest.raises(OscalParseError, match=CHAR_LIMIT_MSG):
            parse_oscal_yaml(_scalar_alias(10_000, 5_000))

    def test_scalar_aliases_within_the_character_limit_parse(self) -> None:
        md = _json_value(parse_oscal_yaml(_scalar_alias(10_000, 99)))["catalog"][
            "metadata"
        ]
        assert len(md["props"]) == 99
        assert md["props"][0]["remarks"] == "x" * 10_000

    def test_nested_collection_alias_bomb_is_rejected_by_the_node_limit(self) -> None:
        # 30 levels of 10 copies each: about 10**30 nodes from 3 KB of input.
        text = _nested_alias(30)
        assert len(text) < 4_000
        with pytest.raises(OscalParseError, match=NODE_LIMIT_MSG):
            parse_oscal_yaml(text)

    def test_collection_aliases_past_the_node_limit_are_rejected(self) -> None:
        # 101 copies of a 1,000-node sequence charge 101,000 nodes.
        with pytest.raises(OscalParseError, match=NODE_LIMIT_MSG) as info:
            parse_oscal_yaml(_wide_alias(999, 101))
        assert info.value.errors[0]["type"] == "yaml_alias_budget"

    def test_collection_aliases_within_the_node_limit_are_not_rejected(self) -> None:
        # 99 copies of a 1,000-node sequence charge 99,000 nodes.
        _not_a_limit(_wide_alias(999, 99))

    def test_alias_to_a_collection_of_about_one_hundred_entries_parses(self) -> None:
        items = "".join(f"      - {{name: n{i}, value: v}}\n" for i in range(100))
        resources = "".join(
            f"    - uuid: 7d2b6c1e-3f4a-4b5c-8d6e-9f0a1b2c3d5{i}\n      props: *p\n"
            for i in range(3)
        )
        text = (
            HEAD
            + "    props: &p\n"
            + items
            + "  back-matter:\n    resources:\n"
            + resources
        )
        bm = _json_value(parse_oscal_yaml(text))["catalog"]["back-matter"]
        assert [len(r["props"]) for r in bm["resources"]] == [100, 100, 100]

    def test_content_without_aliases_does_not_charge_the_budget(self) -> None:
        # 2,000 written props hold more nodes and characters than the alias
        # limits would admit through aliases, and they parse.
        filler = "y" * 600
        items = "".join(
            f"      - {{name: n{i}, value: '{filler}'}}\n" for i in range(2_000)
        )
        assert len(items) > ALIAS_CHAR_LIMIT
        md = _json_value(parse_oscal_yaml(HEAD + "    props:\n" + items))["catalog"][
            "metadata"
        ]
        assert len(md["props"]) == 2_000


class TestDepthLimit:
    def test_input_at_the_depth_limit_is_not_rejected_for_depth(self) -> None:
        assert json.loads(to_json_text(_nested(DEPTH_LIMIT)))
        _not_a_limit(_nested(DEPTH_LIMIT))

    def test_input_past_the_depth_limit_is_rejected(self) -> None:
        with pytest.raises(OscalParseError, match=DEPTH_LIMIT_MSG) as info:
            parse_oscal_yaml(_nested(DEPTH_LIMIT + 1))
        assert info.value.errors[0]["type"] == "yaml_depth_limit"

    def test_very_deep_input_is_rejected_by_the_documented_limit(self) -> None:
        # No stack limit of the runtime rejects it first (YML-011).
        with pytest.raises(OscalParseError, match=DEPTH_LIMIT_MSG):
            parse_oscal_yaml(_nested(100_000))

    def test_block_style_deep_input_is_rejected_by_the_documented_limit(self) -> None:
        text = "".join(f"{' ' * i}k:\n" for i in range(2_000)) + " " * 2_000 + "k: v\n"
        with pytest.raises(OscalParseError, match=DEPTH_LIMIT_MSG):
            parse_oscal_yaml(text)

    def test_aliases_that_nest_past_the_limit_are_rejected(self) -> None:
        # The anchored value nests 100 levels, and the alias sits 100 levels
        # deep. Each is within the limit, and the expanded value is not.
        inner = "[" * 100 + "]" * 100
        outer = "[" * 100 + "*d" + "]" * 100
        text = HEAD + f"    remarks: &d {inner}\n    x: {outer}\n"
        assert json.loads(to_json_text(HEAD + f"    remarks: &d {inner}\n"))
        with pytest.raises(OscalParseError, match=DEPTH_LIMIT_MSG):
            parse_oscal_yaml(text)


class TestNumberBoundary:
    def test_oversized_number_is_a_parse_error_on_both_paths(self) -> None:
        # Task 6.1: a token past CPython's integer-string digit limit.
        digits = "9" * 5_000
        with pytest.raises(OscalParseError):
            parse_oscal_yaml(_component_with_start(digits))
        json_text = to_json_text(_component_with_start("443"))
        assert '"start":443' in json_text
        json_text = json_text.replace('"start":443', f'"start":{digits}')
        with pytest.raises(OscalParseError):
            ob.parse_oscal(json_text)


class TestMemory:
    @pytest.mark.parametrize(
        "text",
        [
            pytest.param(_wide_alias(999, 99), id="node-limit"),
            pytest.param(_scalar_alias(10_000, 99), id="character-limit"),
            pytest.param(_nested_alias(4), id="nested"),
        ],
    )
    def test_input_just_under_a_limit_stays_small(self, text: str) -> None:
        # The design bound: below 100 MB of traced memory at a limit.
        tracemalloc.start()
        try:
            _not_a_limit(text)
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
        assert peak < 100_000_000, peak


def test_large_real_catalog_without_aliases_parses(
    nist_docs: list[CorpusDoc], yaml_parser: str
) -> None:
    # SP 800-53 rev5 has 322,628 nodes and 3,963,105 characters, both past the
    # alias limits, and holds no alias (design Decision 3).
    if yaml_parser != "libyaml":
        pytest.skip("one parser is enough for the size check")
    raw = next(
        d.raw_bytes
        for d in nist_docs
        if d.rel_path.endswith("NIST_SP-800-53_rev5_catalog.json")
    )
    text = yaml.dump(json.loads(raw), Dumper=yaml.CSafeDumper, sort_keys=False)
    events = yaml.parse(text, Loader=yaml.CSafeLoader)
    assert not any(isinstance(e, yaml.AliasEvent) for e in events)
    assert _json_value(parse_oscal_yaml(text)) == _json_value(ob.parse_oscal(raw))
