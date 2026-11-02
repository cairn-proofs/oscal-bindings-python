"""Tests for the optional YAML parse and serialize operations.

Covers the ``yaml-documents`` contract behavior (YML-002 to YML-011) and the
binding-local resource limit (spec ``yaml-resource-limit``). The YAML corpus
cases run from :mod:`tests.test_conformance`; these tests check the individual
scenarios at the unit level, including the schema-type resolver that the corpus
does not exercise in isolation.
"""

import builtins
import json
import sys
import textwrap

import pytest

import oscal_bindings as ob
from oscal_bindings import OscalParseError
from oscal_bindings.v1.extensions import yaml_io
from oscal_bindings.v1.extensions.yaml_io import (
    _SCHEMA,
    COLLECTION_ALIAS_LIMIT,
    parse_oscal_yaml,
    parse_oscal_yaml_file,
    serialize_oscal_yaml,
)

# A minimal valid OSCAL catalog in YAML.
MINIMAL_CATALOG_YAML = textwrap.dedent(
    """\
    catalog:
      uuid: f47ac10b-58cc-4372-a567-0e02b2c3d479
      metadata:
        title: Test Catalog
        last-modified: 2026-01-01T00:00:00Z
        version: "1.0"
        oscal-version: 1.2.3
    """
)

MINIMAL_CATALOG_JSON = json.dumps(
    {
        "catalog": {
            "uuid": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
            "metadata": {
                "title": "Test Catalog",
                "last-modified": "2026-01-01T00:00:00Z",
                "version": "1.0",
                "oscal-version": "1.2.3",
            },
        }
    }
)


def _canon(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _json_value(doc: object) -> object:
    return json.loads(doc.model_dump_json(by_alias=True, exclude_none=True))


# --- Task 2.1: the schema-type resolver (design Decision 1) ----------------


class TestSchemaResolver:
    """``_SCHEMA`` maps a scalar location to its base JSON type."""

    def test_start_is_number_location(self) -> None:
        # port-range start lives under component-definition.
        cd = _SCHEMA.field(_SCHEMA.root, "component-definition")
        components = _SCHEMA.items(_SCHEMA.field(cd, "components"))
        protocols = _SCHEMA.items(_SCHEMA.field(components, "protocols"))
        port_ranges = _SCHEMA.items(_SCHEMA.field(protocols, "port-ranges"))
        start = _SCHEMA.field(port_ranges, "start")
        assert _SCHEMA.base_type(start) in ("number", "integer")

    def test_last_modified_is_string_location(self) -> None:
        catalog = _SCHEMA.field(_SCHEMA.root, "catalog")
        metadata = _SCHEMA.field(catalog, "metadata")
        last_modified = _SCHEMA.field(metadata, "last-modified")
        assert _SCHEMA.base_type(last_modified) == "string"

    def test_hash_algorithm_is_string_location(self) -> None:
        # back-matter resource -> rlinks -> hashes -> algorithm (open enum).
        catalog = _SCHEMA.field(_SCHEMA.root, "catalog")
        bm = _SCHEMA.field(catalog, "back-matter")
        resources = _SCHEMA.items(_SCHEMA.field(bm, "resources"))
        rlinks = _SCHEMA.items(_SCHEMA.field(resources, "rlinks"))
        hashes = _SCHEMA.items(_SCHEMA.field(rlinks, "hashes"))
        algorithm = _SCHEMA.field(hashes, "algorithm")
        assert _SCHEMA.base_type(algorithm) == "string"

    def test_as_is_is_boolean_location(self) -> None:
        profile = _SCHEMA.field(_SCHEMA.root, "profile")
        merge = _SCHEMA.field(profile, "merge")
        as_is = _SCHEMA.field(merge, "as-is")
        assert _SCHEMA.base_type(as_is) == "boolean"


# --- Task 2.2: scalar typing (YML-004.01 .. YML-004.10) --------------------

_SCALAR_YAML = textwrap.dedent(
    """\
    catalog:
      uuid: 7d2b6c1e-3f4a-4b5c-8d6e-9f0a1b2c3d41
      metadata:
        title: {title}
        last-modified: 2024-01-02T03:04:05Z
        version: {version}
        oscal-version: 1.2.3
    """
)


def _parse_catalog_metadata(title: str = "T", version: str = '"1.0"') -> dict:
    doc = parse_oscal_yaml(_SCALAR_YAML.format(title=title, version=version))
    return _json_value(doc)["catalog"]["metadata"]


class TestScalarTyping:
    def test_number_form_at_string_location_stays_string(self) -> None:
        # YML-004.01: version 1.0 at a string location is the string "1.0".
        md = _parse_catalog_metadata(version="1.0")
        assert md["version"] == "1.0"

    def test_boolean_form_at_string_location_stays_string(self) -> None:
        # YML-004.03: title yes is the string "yes".
        md = _parse_catalog_metadata(title="yes")
        assert md["title"] == "yes"

    def test_null_forms_at_string_location(self) -> None:
        # YML-004.04: plain null, ~, and empty keep their text at a string loc.
        y = textwrap.dedent(
            """\
            catalog:
              uuid: 7d2b6c1e-3f4a-4b5c-8d6e-9f0a1b2c3d41
              metadata:
                title: T
                last-modified: 2024-01-02T03:04:05Z
                version: "1.0"
                oscal-version: 1.2.3
                props:
                  - {name: a, value: x, remarks: null}
                  - {name: b, value: y, remarks: ~}
                  - {name: c, value: z, remarks: }
            """
        )
        props = _json_value(parse_oscal_yaml(y))["catalog"]["metadata"]["props"]
        assert [p["remarks"] for p in props] == ["null", "~", ""]

    def test_scalar_tag_ignored_at_string_location(self) -> None:
        # YML-004.05: !!int 7 at a string location is the string "7".
        y = textwrap.dedent(
            """\
            catalog:
              uuid: 7d2b6c1e-3f4a-4b5c-8d6e-9f0a1b2c3d41
              metadata:
                title: T
                last-modified: 2024-01-02T03:04:05Z
                version: "1.0"
                oscal-version: 1.2.3
                props:
                  - {name: a, value: !!int 7}
            """
        )
        props = _json_value(parse_oscal_yaml(y))["catalog"]["metadata"]["props"]
        assert props[0]["value"] == "7"

    def _component_definition_with_start(self, start: str) -> object:
        y = textwrap.dedent(
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
        return parse_oscal_yaml(y)

    def test_quoted_scalar_at_number_location_is_number(self) -> None:
        # YML-004.06: "443" at a number location is the number 443.
        doc = self._component_definition_with_start('"443"')
        cd = _json_value(doc)["component-definition"]
        pr = cd["components"][0]["protocols"][0]["port-ranges"][0]
        assert pr["start"] == 443

    @pytest.mark.parametrize("bad", ["0x1BB", "+443", "007"])
    def test_bad_number_form_is_parse_error(self, bad: str) -> None:
        # YML-004.07, YML-004.10: hex, plus sign, leading zero are grammar
        # errors at a number location.
        with pytest.raises(OscalParseError):
            self._component_definition_with_start(bad)

    def test_number_grammar_error_names_its_location(self) -> None:
        # YML-010.01 / PRS-006: the parse error carries a structured entry whose
        # location identifies the offending start scalar.
        with pytest.raises(OscalParseError) as info:
            self._component_definition_with_start("0x1BB")
        error = info.value
        assert error.errors, "the error carries no structured entry"
        entry = error.errors[0]
        assert "loc" in entry
        assert "line" in entry["loc"]
        assert "column" in entry["loc"]

    def test_boolean_location_rejects_non_boolean_text(self) -> None:
        # YML-004.08: yes at a boolean location is a parse error.
        y = textwrap.dedent(
            """\
            profile:
              uuid: 7d2b6c1e-3f4a-4b5c-8d6e-9f0a1b2c3d41
              metadata:
                title: T
                last-modified: 2024-01-02T03:04:05Z
                version: "1.0"
                oscal-version: 1.2.3
              imports:
                - href: https://example.com/c.json
                  include-all: {}
              merge:
                as-is: yes
            """
        )
        with pytest.raises(OscalParseError):
            parse_oscal_yaml(y)

    def test_true_at_boolean_location_is_boolean(self) -> None:
        y = textwrap.dedent(
            """\
            profile:
              uuid: 7d2b6c1e-3f4a-4b5c-8d6e-9f0a1b2c3d41
              metadata:
                title: T
                last-modified: 2024-01-02T03:04:05Z
                version: "1.0"
                oscal-version: 1.2.3
              imports:
                - href: https://example.com/c.json
                  include-all: {}
              merge:
                as-is: true
            """
        )
        merge = _json_value(parse_oscal_yaml(y))["profile"]["merge"]
        assert merge["as-is"] is True


# --- Task 2.3: node-layer structure rules ----------------------------------


class TestStructureRules:
    def test_duplicate_key_is_parse_error(self) -> None:
        # YML-003.
        y = textwrap.dedent(
            """\
            catalog:
              uuid: 7d2b6c1e-3f4a-4b5c-8d6e-9f0a1b2c3d41
              metadata:
                title: A
                title: B
                last-modified: 2024-01-02T03:04:05Z
                version: "1.0"
                oscal-version: 1.2.3
            """
        )
        with pytest.raises(OscalParseError, match="duplicate key"):
            parse_oscal_yaml(y)

    def test_same_text_keys_are_parse_error(self) -> None:
        # YML-003.03: a plain key and its quoted form share the same text.
        y = textwrap.dedent(
            """\
            catalog:
              uuid: 7d2b6c1e-3f4a-4b5c-8d6e-9f0a1b2c3d41
              metadata:
                title: A
                "title": B
                last-modified: 2024-01-02T03:04:05Z
                version: "1.0"
                oscal-version: 1.2.3
            """
        )
        with pytest.raises(OscalParseError, match="duplicate key"):
            parse_oscal_yaml(y)

    def test_non_scalar_key_is_parse_error(self) -> None:
        # YML-003.02: a sequence used as a key.
        y = textwrap.dedent(
            """\
            catalog:
              ? [a, b]
              : c
            """
        )
        with pytest.raises(OscalParseError, match="not a scalar"):
            parse_oscal_yaml(y)

    def test_merge_key_is_unknown_field(self) -> None:
        # YML-009.04: << is an ordinary key, so Pydantic rejects it as unknown.
        y = textwrap.dedent(
            """\
            catalog: &c
              uuid: 7d2b6c1e-3f4a-4b5c-8d6e-9f0a1b2c3d41
              metadata:
                title: T
                last-modified: 2024-01-02T03:04:05Z
                version: "1.0"
                oscal-version: 1.2.3
                <<:
                  extra: value
            """
        )
        with pytest.raises(OscalParseError):
            parse_oscal_yaml(y)

    def test_omap_tag_reads_as_array(self) -> None:
        # YML-009.03: a sequence tagged !!omap reads as an array.
        y = textwrap.dedent(
            """\
            catalog:
              uuid: 7d2b6c1e-3f4a-4b5c-8d6e-9f0a1b2c3d42
              metadata:
                title: T
                last-modified: 2024-01-02T03:04:05Z
                version: "1.0"
                oscal-version: 1.2.3
              back-matter:
                resources: !!omap
                  - uuid: 7d2b6c1e-3f4a-4b5c-8d6e-9f0a1b2c3d43
            """
        )
        bm = _json_value(parse_oscal_yaml(y))["catalog"]["back-matter"]
        assert isinstance(bm["resources"], list)

    def test_alias_inside_own_anchored_node_is_parse_error(self) -> None:
        # YML-009.02: a mapping anchored as &a that holds the alias *a.
        y = textwrap.dedent(
            """\
            catalog:
              uuid: 7d2b6c1e-3f4a-4b5c-8d6e-9f0a1b2c3d44
              metadata: &m
                title: T
                last-modified: 2024-01-02T03:04:05Z
                version: "1.0"
                oscal-version: 1.2.3
                extra: *m
            """
        )
        with pytest.raises(OscalParseError, match="own anchored node"):
            parse_oscal_yaml(y)


# --- Task 2.4: input-stream rules (YML-002) --------------------------------


class TestStreamRules:
    def test_invalid_utf8_is_parse_error(self) -> None:
        # PRS-001.03: the binding decodes and maps the failure to OscalParseError.
        with pytest.raises(OscalParseError, match="UTF-8"):
            parse_oscal_yaml(b"\xff\xfe\x00catalog")

    def test_utf16_bytes_are_rejected(self) -> None:
        # YML-002.04: UTF-16 with a BOM must be rejected, not decoded by PyYAML.
        data = MINIMAL_CATALOG_YAML.encode("utf-16")
        with pytest.raises(OscalParseError):
            parse_oscal_yaml(data)

    def test_no_document_is_parse_error(self) -> None:
        # YML-002.03.
        with pytest.raises(OscalParseError, match="no document"):
            parse_oscal_yaml("# only a comment\n")

    def test_two_documents_is_parse_error(self) -> None:
        # YML-002.02.
        y = MINIMAL_CATALOG_YAML + "---\n" + MINIMAL_CATALOG_YAML
        with pytest.raises(OscalParseError, match="more than one document"):
            parse_oscal_yaml(y)

    def test_syntax_error_is_parse_error(self) -> None:
        # YML-002.01: a flow sequence with no closing bracket.
        with pytest.raises(OscalParseError, match="Invalid YAML"):
            parse_oscal_yaml("catalog: [a, b\n")


# --- Task 3.1: parse_oscal_yaml --------------------------------------------


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
        json_doc = ob.parse_oscal(MINIMAL_CATALOG_JSON)
        assert _canon(_json_value(yaml_doc)) == _canon(_json_value(json_doc))

    def test_unknown_field_is_parse_error(self) -> None:
        # YML-005.03 / PRS-004.
        y = textwrap.dedent(
            """\
            catalog:
              uuid: 7d2b6c1e-3f4a-4b5c-8d6e-9f0a1b2c3d41
              metadata:
                title: T
                last-modified: 2024-01-02T03:04:05Z
                version: "1.0"
                oscal-version: 1.2.3
                colour: blue
            """
        )
        with pytest.raises(OscalParseError):
            parse_oscal_yaml(y)


# --- Task 3.2: parse_oscal_yaml_file ---------------------------------------


class TestParseOscalYamlFile:
    def test_parses_existing_file(self, tmp_path) -> None:
        path = tmp_path / "catalog.yaml"
        path.write_text(MINIMAL_CATALOG_YAML, encoding="utf-8")
        doc = parse_oscal_yaml_file(path)
        assert _canon(_json_value(doc)) == _canon(json.loads(MINIMAL_CATALOG_JSON))

    def test_missing_file_reports_not_found(self, tmp_path) -> None:
        # YML-006 / PRS-002: not-found is distinct from the parse error.
        missing = tmp_path / "nope.yaml"
        with pytest.raises(FileNotFoundError) as info:
            parse_oscal_yaml_file(missing)
        assert str(missing) in str(info.value)
        assert not isinstance(info.value, OscalParseError)


# --- Task 3.3: serialize_oscal_yaml ----------------------------------------


class TestSerializeOscalYaml:
    def test_version_string_survives_round_trip(self) -> None:
        # YML-008.02: a string "1.0" stays a string after serialize and parse.
        doc = parse_oscal_yaml(MINIMAL_CATALOG_YAML)
        out = serialize_oscal_yaml(doc)
        reparsed = parse_oscal_yaml(out)
        assert _json_value(reparsed)["catalog"]["metadata"]["version"] == "1.0"

    def test_output_holds_no_null(self) -> None:
        # YML-008.03.
        doc = parse_oscal_yaml(MINIMAL_CATALOG_YAML)
        out = serialize_oscal_yaml(doc)
        assert "null" not in out


# --- Task 3.4: re-export and import guard -----------------------------------


class TestPublicSurface:
    def test_names_import_from_top_level(self) -> None:
        from oscal_bindings import (
            parse_oscal_yaml,
            parse_oscal_yaml_file,
            serialize_oscal_yaml,
        )

        assert callable(parse_oscal_yaml)
        assert callable(parse_oscal_yaml_file)
        assert callable(serialize_oscal_yaml)

    def test_v1_all_carries_them(self) -> None:
        from oscal_bindings import v1

        for name in (
            "parse_oscal_yaml",
            "parse_oscal_yaml_file",
            "serialize_oscal_yaml",
        ):
            assert name in v1.__all__

    def test_import_without_extra_raises_install_hint(self, monkeypatch) -> None:
        # Design Decision 5: a missing PyYAML raises ImportError with a hint.
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "yaml" or name.startswith("yaml."):
                message = "No module named 'yaml'"
                raise ImportError(message)
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        monkeypatch.delitem(
            sys.modules, "oscal_bindings.v1.extensions.yaml_io", raising=False
        )
        with pytest.raises(ImportError, match=r"oscal-bindings\[yaml\]"):
            import oscal_bindings.v1.extensions.yaml_io  # noqa: F401


# --- Task 4.1: the collection-alias resource limit -------------------------


class TestResourceLimit:
    def _nested_aliases(self, depth: int) -> str:
        """A billion-laughs-style document: each level aliases the one below.

        The back-matter resource holds nested props that fan out through
        aliases, so the collection-alias resolutions grow multiplicatively and
        pass the limit well before ``depth`` is large.
        """
        lines = [
            "catalog:",
            "  uuid: 7d2b6c1e-3f4a-4b5c-8d6e-9f0a1b2c3d41",
            "  metadata:",
            "    title: T",
            "    last-modified: 2024-01-02T03:04:05Z",
            '    version: "1.0"',
            "    oscal-version: 1.2.3",
            "    props:",
            "      - name: a0",
            "        value: v",
            "        props: &a0",
            "          - {name: x, value: y}",
        ]
        for i in range(1, depth):
            prev = f"a{i - 1}"
            lines += [
                f"      - name: a{i}",
                "        value: v",
                f"        props: &a{i}",
                f"          - {{name: x, value: y, props: *{prev}}}",
                f"          - {{name: x, value: y, props: *{prev}}}",
            ]
        return "\n".join(lines) + "\n"

    def test_input_over_limit_is_parse_error(self) -> None:
        with pytest.raises(OscalParseError, match="exceeds the limit"):
            parse_oscal_yaml(self._nested_aliases(12))

    def test_small_fixed_collection_aliasing_parses(self) -> None:
        # A handful of collection aliases stays far under the limit.
        y = textwrap.dedent(
            """\
            catalog:
              uuid: 7d2b6c1e-3f4a-4b5c-8d6e-9f0a1b2c3d41
              metadata:
                title: T
                last-modified: 2024-01-02T03:04:05Z
                version: "1.0"
                oscal-version: 1.2.3
                props: &p
                  - {name: a, value: v}
              back-matter:
                resources:
                  - uuid: 7d2b6c1e-3f4a-4b5c-8d6e-9f0a1b2c3d42
                    props: *p
            """
        )
        doc = parse_oscal_yaml(y)
        assert _json_value(doc)["catalog"]["back-matter"]["resources"]

    def test_many_scalar_aliases_parse(self) -> None:
        # A scalar alias is not counted against the limit, so far more than the
        # limit of scalar aliases still parses.
        count = COLLECTION_ALIAS_LIMIT * 3
        props = "\n".join(f"      - {{name: n{i}, value: *v}}" for i in range(count))
        y = (
            "catalog:\n"
            "  uuid: 7d2b6c1e-3f4a-4b5c-8d6e-9f0a1b2c3d41\n"
            "  metadata:\n"
            "    title: T\n"
            "    last-modified: 2024-01-02T03:04:05Z\n"
            '    version: &v "1.0"\n'
            "    oscal-version: 1.2.3\n"
            "    props:\n" + props + "\n"
        )
        doc = parse_oscal_yaml(y)
        md = _json_value(doc)["catalog"]["metadata"]
        assert len(md["props"]) == count
        assert all(p["value"] == "1.0" for p in md["props"])


def test_module_all_matches_public_functions() -> None:
    assert set(yaml_io.__all__) == {
        "parse_oscal_yaml",
        "parse_oscal_yaml_file",
        "serialize_oscal_yaml",
    }
