"""Tests for the optional YAML parse and serialize operations.

Covers the ``yaml-documents`` contract behavior (YML-002 to YML-011) and the
binding-local resource limit (spec ``yaml-resource-limit``). The YAML corpus
cases run from :mod:`tests.test_conformance`; these tests check the individual
scenarios at the unit level, including the schema-type resolver that the corpus
does not exercise in isolation.
"""

import builtins
import json
import subprocess
import sys
import textwrap

import pytest

import oscal_bindings as ob
from oscal_bindings import OscalParseError
from oscal_bindings.v1.extensions import yaml_io
from oscal_bindings.v1.extensions.yaml_io import (
    _SCHEMA,
    DEPTH_LIMIT,
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

    def test_yaml_io_import_without_extra_raises_install_hint(
        self, monkeypatch
    ) -> None:
        # Importing the yaml_io submodule directly still fails fast with a hint.
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


# --- Task 8.2: the base install (no `yaml` extra) works for non-YAML paths -


def _run_without_yaml(body: str) -> subprocess.CompletedProcess[str]:
    """Run ``body`` in a fresh interpreter where importing `yaml` fails.

    A `sys.meta_path` finder blocks `yaml` (and submodules), simulating a base
    install without the extra. The body runs after the block is in place.
    """
    prelude = textwrap.dedent(
        """\
        import sys, importlib.abc, importlib.machinery

        class _BlockYaml(importlib.abc.MetaPathFinder):
            def find_spec(self, name, path, target=None):
                if name == "yaml" or name.startswith("yaml."):
                    raise ImportError("No module named 'yaml'")
                return None

        sys.meta_path.insert(0, _BlockYaml())
        for _m in list(sys.modules):
            if _m == "yaml" or _m.startswith("yaml."):
                del sys.modules[_m]
        """
    )
    return subprocess.run(  # noqa: S603 - fixed interpreter, no shell
        [sys.executable, "-c", prelude + textwrap.dedent(body)],
        capture_output=True,
        text=True,
        check=False,
    )


class TestBaseInstallWithoutYaml:
    @pytest.mark.parametrize(
        "stmt",
        [
            "import oscal_bindings",
            "from oscal_bindings import *",
            "import oscal_bindings.extensions",
            "from oscal_bindings.extensions import *",
            "import oscal_bindings.v1",
            "from oscal_bindings.v1 import *",
            "from oscal_bindings import parse_oscal, OscalDoc, make_hash",
        ],
    )
    def test_import_path_works_without_yaml(self, stmt: str) -> None:
        # Review finding #1: no import path may require PyYAML on a base install.
        proc = _run_without_yaml(f"{stmt}\nprint('ok')\n")
        assert proc.returncode == 0, proc.stderr
        assert "ok" in proc.stdout

    def test_calling_a_yaml_op_raises_the_install_hint(self) -> None:
        # Only a call touches PyYAML, and then it raises the hint.
        proc = _run_without_yaml(
            """
            from oscal_bindings import parse_oscal_yaml
            try:
                parse_oscal_yaml("catalog: {}")
            except ImportError as exc:
                print("HINT" if "oscal-bindings[yaml]" in str(exc) else "NO-HINT")
            else:
                print("NO-RAISE")
            """
        )
        assert proc.returncode == 0, proc.stderr
        assert "HINT" in proc.stdout

    def test_top_level_yaml_name_is_not_any_at_runtime(self) -> None:
        # Review finding #5: the top-level name resolves to the real function,
        # not a dynamic `__getattr__` fallback. The static-type guarantee is
        # verified by mypy over the top-level surface (tests/typing/, checked by
        # `hatch run typing`); this runtime check pins that the name is the same
        # object as the v1 wrapper, i.e. a genuine re-export, not a shim.
        import oscal_bindings
        import oscal_bindings.v1

        assert oscal_bindings.parse_oscal_yaml is oscal_bindings.v1.parse_oscal_yaml
        assert type(oscal_bindings.parse_oscal_yaml).__name__ == "function"


# --- Tasks 4.1, 6.1, 8.1: resource limits, adversarial and accept-side -----


def _catalog_with_props(props_yaml: str) -> str:
    """A minimal valid catalog whose metadata props block is ``props_yaml``."""
    return (
        "catalog:\n"
        "  uuid: 7d2b6c1e-3f4a-4b5c-8d6e-9f0a1b2c3d41\n"
        "  metadata:\n"
        "    title: T\n"
        "    last-modified: 2024-01-02T03:04:05Z\n"
        '    version: "1.0"\n'
        "    oscal-version: 1.2.3\n"
        "    props:\n" + props_yaml
    )


class TestResourceLimit:
    def test_collection_alias_bomb_is_parse_error(self) -> None:
        # A billion-laughs expansion: each level references the one below twice,
        # so the materialized value grows multiplicatively past the budget. A
        # small input that must NOT be accepted (review finding #3).
        lines = [
            (
                "      - name: a0\n"
                "        value: v\n"
                "        props: &a0\n"
                "          - {name: x, value: y}\n"
            )
        ]
        for i in range(1, 24):
            prev = f"a{i - 1}"
            lines.append(
                f"      - name: a{i}\n        value: v\n        props: &a{i}\n"
                f"          - {{name: x, value: y, props: *{prev}}}\n"
                f"          - {{name: x, value: y, props: *{prev}}}\n"
            )
        y = _catalog_with_props("".join(lines))
        with pytest.raises(OscalParseError, match="budget"):
            parse_oscal_yaml(y)

    def test_alias_bomb_over_sequences_is_parse_error(self) -> None:
        # A billion-laughs over sequences: a small input whose nested aliased
        # sequences expand past the node budget. The old design exempted scalar
        # aliases and under-counted this class (review finding #4). It must be a
        # parse error, not a success or a hang.
        with pytest.raises(OscalParseError, match="budget"):
            parse_oscal_yaml(_scalar_sequence_bomb())

    def test_deep_nesting_is_parse_error(self) -> None:
        # Deep nesting must be a parse error, not an uncaught RecursionError
        # (review finding #2).
        depth = DEPTH_LIMIT + 50
        inner = "[" * depth + "]" * depth
        y = _catalog_with_props(f"      - {{name: a, value: v, props: {inner}}}\n")
        with pytest.raises(OscalParseError):
            parse_oscal_yaml(y)

    def test_oversized_number_is_parse_error(self) -> None:
        # A numeric token past CPython's integer-string digit limit must surface
        # as OscalParseError, not a bare ValueError (review finding #7).
        digits = "9" * 5000
        with pytest.raises(OscalParseError):
            parse_oscal_yaml(_component_with_port(digits))

    def test_bounded_collection_aliasing_parses(self) -> None:
        # Accept side: an alias to a ~100-entry collection parses. The old design
        # rejected this (review finding #3); it must now be accepted. The props
        # block is anchored under metadata (a valid props location) and the
        # back-matter resource references it.
        items = "\n".join(f"      - {{name: n{i}, value: v}}" for i in range(100))
        y = (
            "catalog:\n"
            "  uuid: 7d2b6c1e-3f4a-4b5c-8d6e-9f0a1b2c3d41\n"
            "  metadata:\n"
            "    title: T\n"
            "    last-modified: 2024-01-02T03:04:05Z\n"
            '    version: "1.0"\n'
            "    oscal-version: 1.2.3\n"
            "    props: &p\n" + items + "\n"
            "  back-matter:\n"
            "    resources:\n"
            "      - uuid: 7d2b6c1e-3f4a-4b5c-8d6e-9f0a1b2c3d42\n"
            "        props: *p\n"
        )
        doc = parse_oscal_yaml(y)
        resources = _json_value(doc)["catalog"]["back-matter"]["resources"]
        assert len(resources[0]["props"]) == 100

    def test_ordinary_document_with_aliases_parses(self) -> None:
        # Accept side: modest aliasing in an otherwise ordinary document parses.
        y = (
            "catalog:\n"
            "  uuid: 7d2b6c1e-3f4a-4b5c-8d6e-9f0a1b2c3d41\n"
            "  metadata:\n"
            "    title: T\n"
            "    last-modified: 2024-01-02T03:04:05Z\n"
            '    version: "1.0"\n'
            "    oscal-version: 1.2.3\n"
            "    props: &p\n"
            "      - {name: a, value: v}\n"
            "  back-matter:\n"
            "    resources:\n"
            "      - uuid: 7d2b6c1e-3f4a-4b5c-8d6e-9f0a1b2c3d42\n"
            "        props: *p\n"
        )
        doc = parse_oscal_yaml(y)
        assert _json_value(doc)["catalog"]["back-matter"]["resources"]


def _scalar_sequence_bomb() -> str:
    """A small input whose aliased sequences expand past the node budget.

    Classic billion-laughs over sequences of scalars: each anchor is a sequence
    that references the previous anchor several times, so the emitted-node count
    grows multiplicatively well past the budget from a small input.
    """
    lines = [
        "catalog:",
        "  uuid: 7d2b6c1e-3f4a-4b5c-8d6e-9f0a1b2c3d41",
        "  metadata:",
        "    title: T",
        "    last-modified: 2024-01-02T03:04:05Z",
        '    version: "1.0"',
        "    oscal-version: 1.2.3",
        "    props: &a0",
        "      - {name: x, value: y}",
    ]
    for i in range(1, 20):
        prev = f"*a{i - 1}"
        lines.append(f"    props{i}: &a{i}")
        lines.append(f"      - {{name: x, value: y, props: {prev}}}")
        lines.append(f"      - {{name: x, value: y, props: {prev}}}")
        lines.append(f"      - {{name: x, value: y, props: {prev}}}")
    return "\n".join(lines) + "\n"


def _component_with_port(start_token: str) -> str:
    """A component-definition YAML whose port-range start is ``start_token``."""
    return (
        "component-definition:\n"
        "  uuid: 7d2b6c1e-3f4a-4b5c-8d6e-9f0a1b2c3d41\n"
        "  metadata:\n"
        "    title: T\n"
        "    last-modified: 2024-01-02T03:04:05Z\n"
        '    version: "1.0"\n'
        "    oscal-version: 1.2.3\n"
        "  components:\n"
        "    - uuid: 7d2b6c1e-3f4a-4b5c-8d6e-9f0a1b2c3d42\n"
        "      type: service\n"
        "      title: C\n"
        "      description: d\n"
        "      protocols:\n"
        "        - name: p\n"
        "          port-ranges:\n"
        f"            - start: {start_token}\n"
    )


def test_module_all_matches_public_functions() -> None:
    assert set(yaml_io.__all__) == {
        "parse_oscal_yaml",
        "parse_oscal_yaml_file",
        "serialize_oscal_yaml",
    }
