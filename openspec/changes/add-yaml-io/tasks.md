# Tasks

## 1. Move the pin and add the dependency

- [x] 1.1 Move the pin in `scripts/spec_artifact.py` to `0.5.1+oscal.1.2.3` with sha256
  `33a14ab00fcbc049934ad217989452896b74a1bb215bbd4f132ca3b81c8dfd8f`. The OSCAL release stays `1.2.3`, so
  `__oscal_schema_version__` needs no edit. Verify with `hatch run generate` and
  `git diff --exit-code -- src/oscal_bindings/v1/models.py`: the artifact re-fetches and `models.py` shows no drift.
- [x] 1.2 Add the `yaml` optional extra in `pyproject.toml` with `pyyaml` pinned exactly. Add `pyyaml` and
  `types-PyYAML` to the dev and test environments. Re-lock with `hatch run lock`. Verify the committed lockfiles change
  and `hatch test` collects in the `hatch-test` env.

## 2. YAML-to-JSON converter

- [x] 2.1 Add `v1/extensions/yaml_io.py` with a schema-type resolver that maps a scalar location to its base JSON type.
  It follows `$ref`, folds `allOf` to one base type, and treats a string open-enum `anyOf` as a string location (design
  Decision 1). Verify with a unit test that resolves `start` to a number location, `last-modified` to a string
  location, and a hash `algorithm` to a string location.
- [x] 2.2 Implement the node walk over the PyYAML composed graph that builds a JSON value, with the scalar typing of
  design Decision 1:
  1. A string location emits a quoted string that keeps the scalar's text, including `null`, `~`, and an empty scalar
     as `"null"`, `"~"`, and `""`.
  2. A number or integer location emits a bare JSON number token when the text matches the RFC 8259 number grammar,
     else a located grammar error.
  3. A boolean location emits `true` or `false`, else a located grammar error.
  Verify with unit tests for YML-004.01 through YML-004.10, including `1.0` at a string location, `"443"` at a number
  location, and `+443`, `007`, `0x1BB`, and `yes` at the locations the scenarios name. Verify that a `0x1BB` at a
  `start` location reports a parse error whose structured entry names that `start` location (YML-010.01, PRS-006).
- [x] 2.3 Enforce the node-layer structure rules in the walk:
  1. Reject a mapping with two keys of the same text, including a plain key and its quoted form (YML-003).
  2. Reject a mapping whose key node is not a scalar, such as a sequence used as a key (YML-003.02).
  3. Key a mapping on the `<<` scalar value, so a merge key is an unknown field (YML-009.04).
  4. Ignore a node tag, so `!!int 7` keeps `"7"` and `!!omap` reads as an array (YML-004.05, YML-009.03).
  5. Carry an ancestor set and reject an alias inside its own anchored node (YML-009.02).
  Verify with a unit test for each rule.
- [x] 2.4 Enforce the input-stream rules:
  1. Decode bytes as UTF-8 in the binding and map a decode failure to `OscalParseError` without a lower-level decode
     error (YML-002.04, PRS-001.03). Reject a UTF-16 input.
  2. Require exactly one document, and reject a no-document, a two-document, and a syntax-error stream
     (YML-002.01 to YML-002.03).
  Verify with a unit test for each case.

## 3. Public YAML operations

- [x] 3.1 Implement `parse_oscal_yaml(data: str | bytes) -> OscalDocument`. It converts the YAML input to a JSON value,
  serializes it to JSON text, and calls `parse_oscal` (design Decision 1). Verify with unit tests that:
  1. A valid OSCAL YAML document parses to the same typed value as the equivalent JSON, from both `str` and `bytes`
     (YML-005).
  2. A YAML document carrying a field the schema does not define is a parse error (YML-005.03, PRS-004).
- [x] 3.2 Implement `parse_oscal_yaml_file(path: Path | str) -> OscalDocument`. It reads the file and parses the content
  as `parse_oscal_yaml` does, and reports the not-found condition that names the path as `parse_oscal_file` does
  (YML-006, PRS-002). Verify with unit tests that an existing file parses and a missing path reports not-found, distinct
  from the parse error.
- [x] 3.3 Implement `serialize_oscal_yaml(model: OscalDocument) -> str`. It dumps the model through the JSON value in
  block style and keeps a string-shaped scalar quoted (design Decision 4, YML-008). Verify with unit tests that:
  1. A document whose metadata `version` is `"1.0"` serializes and parses back to the string `"1.0"` (YML-008.02).
  2. The output holds no null (YML-008.03).
- [x] 3.4 Bind the three YAML names at call time, not at attribute access (design Decision 5). Each public name is a
  thin typed wrapper in `v1/__init__.py` (re-exported at the top level and the compatibility module) that imports
  `yaml_io` inside its body. Remove the module `__getattr__` and `globals()` loop. A base install without the `yaml`
  extra keeps `import oscal_bindings`, `from oscal_bindings import *`, and `import oscal_bindings.extensions` working,
  and a type checker resolves each wrapper's real signature. Only a call raises `ImportError` with the install hint.
  Verify with the base-install and type tests of task 8.2.

## 4. Resource limit

- [x] 4.1 Replace the alias-resolution counter with the expansion budget and depth limit of design Decision 3 (spec
  `yaml-resource-limit`). During the walk:
  1. Count every emitted JSON node (each scalar, array, and object), so an expanded alias of any kind adds its whole
     subtree. Raise `OscalParseError` once the count passes 5,000,000.
  2. Track recursion depth and raise `OscalParseError` once the document nests past 500 levels.
  Remove the scalar-alias exemption and the collection-only edge count. Verify with the adversarial and accept-side
  tests of task 8.1.

## 5. Traceability record

- [x] 5.1 Add the traceability record that holds one entry for every public operation in `v1/__all__`, each citing the
  contract requirement that defines it. The three YAML functions cite YML-005, YML-006, and YML-008 (proposal item 7,
  `binding-surface` SRF-003). Verify the record validates against `openspec/traceability.schema.json` of the pinned
  0.5.1 artifact, and that each cited identifier resolves in that artifact's `openspec/requirements.json` (SRF-004).
- [x] 5.2 Add a test that fails on either condition (SRF-003.04, SRF-004):
  1. A name in `v1/__all__` has no entry in the record.
  2. A cited identifier does not resolve in the pinned requirement index.
  Verify the test passes for the current surface and fails when an entry is removed.

## 6. Error boundary, conformance, and documentation

- [x] 6.1 Map three failures to `OscalParseError` (design Decision 2):
  1. A `RecursionError` from `yaml.compose_all`.
  2. A `RecursionError` from the walk.
  3. A `ValueError` from `json.loads` on an oversized numeric token.
  Do not raise the recursion limit. Verify with the error-boundary tests of task 8.1 that each surfaces as
  `OscalParseError`, not a bare `RecursionError` or `ValueError`.
- [x] 6.2 Add `yaml-round-trip` and `yaml-parse` handlers to the `OPERATIONS` map in `tests/test_conformance.py`,
  reading the input as the corpus manifest defines. Verify all 23 YAML corpus cases pass with
  `hatch test -- -k conformance`.
- [x] 6.3 Document the YAML usage in the README. Add a DEVELOPING.md note on the scalar-typing rule (YML-004), the
  expansion budget of 5,000,000 emitted nodes, and the nesting-depth limit of 500 levels (YML-011). Narrow the
  conformance claim to exclude YML-008 and SER-005 until issue #19 closes. Verify the documented usage example runs as
  written with `hatch run python`.

## 7. Full gate

- [x] 7.1 Run the full gate with `hatch run release > ./tmp/release.log 2>&1; echo "EXIT: $?"` and read the log. Verify
  it passes end to end: generate with no `models.py` drift, then lint, typing (including the top-level YAML surface),
  security, the whole Python matrix with the YAML corpus cases, and docs.

## 8. Adversarial resource tests and base-install tests

- [x] 8.1 Write the adversarial and accept-side resource tests first, so they fail against the old limit and pass
  against tasks 4.1 and 6.1. Mark the two expensive alias-bomb tests `@pytest.mark.slow`, excluded from the default
  `hatch test` run and included in the release gate. Each over-limit case asserts `OscalParseError`, not a crash, a
  hang, or a success:
  1. A scalar-alias bomb: a small input whose scalar aliases expand past the budget.
  2. A collection-alias bomb: a small input whose collection aliases expand past the budget.
  3. A deep-nesting input past 500 levels.
  4. An oversized numeric token past CPython's integer-string digit limit.
  5. Accept side: a conformant OSCAL document with modest aliasing, and an alias to a collection of about 100 entries.
     Both parse and return the typed value.
- [x] 8.2 Write the base-install import tests and the type-surface test, with PyYAML unavailable via a `sys.modules`
  shim. Assert that each of these succeeds and binds the non-YAML names:
  1. `import oscal_bindings`.
  2. `from oscal_bindings import *`.
  3. `import oscal_bindings.extensions`, and a star import of it.
  Assert that only calling a YAML operation raises the install hint. Assert with a type-checker check that
  `from oscal_bindings import parse_oscal_yaml` resolves to its real signature, not `Any`.

## Workflow follow-up

- Commit the spec files first on the feature branch, then each task group as a checkpoint, including the updated
  `tasks.md`, per the project's GitHub workflow.
- Open a pull request that references issue #7 once `hatch run release` passes. The pull request carries the
  implementation only, not the archive.
- After the pull request review approves, archive the change on the branch with `openspec archive add-yaml-io -y`. This
  moves the change into `openspec/changes/archive/` and syncs the `yaml-resource-limit` delta into
  `openspec/specs/yaml-resource-limit/spec.md`, the project's first main spec.
- Verify the archive on the branch: `openspec validate --strict` passes for the archived change and the new main spec,
  `openspec list --specs` shows `yaml-resource-limit`, and `hatch run release` passes on the archived tree. Push the
  archive as a follow-up commit on the same pull request.
- Merge the pull request once it is approved and the archive commit is in it. No archive step remains after the merge.
