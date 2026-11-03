# Tasks

## 1. Move the pin and add the dependency

- [x] 1.1 Move the pin in `scripts/spec_artifact.py` to `0.5.1+oscal.1.2.3` with sha256
  `33a14ab00fcbc049934ad217989452896b74a1bb215bbd4f132ca3b81c8dfd8f`. The OSCAL release stays `1.2.3`, so
  `__oscal_schema_version__` needs no edit. Verify with `hatch run generate` and
  `git diff --exit-code -- src/oscal_bindings/v1/models.py`: the artifact re-fetches and `models.py` shows no drift.
- [x] 1.2 Add the `yaml` optional extra in `pyproject.toml` with `pyyaml` pinned exactly. Add `pyyaml` and
  `types-PyYAML` to the dev and test environments. Re-lock with `hatch run lock`. Verify the committed lockfiles change
  and `hatch test` collects in the `hatch-test` env.
- [x] 1.3 Pin `types-PyYAML` exactly in the default env, as every other default-env dependency is. Re-lock with
  `hatch run lock`. Verify the lockfile diff changes only the stubs line, and `hatch run typing` passes.

## 2. YAML-to-JSON converter

- [x] 2.1 Add `v1/extensions/yaml_io.py` with a schema-type resolver that maps a scalar location to its base JSON type.
  It follows `$ref`, folds `allOf` to one base type, and treats a string open-enum `anyOf` as a string location (design
  Decision 1). Verify with a unit test that resolves `start` to a number location, `last-modified` to a string
  location, and a hash `algorithm` to a string location.
- [x] 2.2 Implement the walk over the binding's composed node tree that writes the JSON text, with an explicit stack
  and no recursion per nesting level, and with the scalar typing of design Decision 1:
  1. A string location emits a quoted string that keeps the scalar's text, including `null`, `~`, and an empty scalar
     as `"null"`, `"~"`, and `""`.
  2. A number or integer location emits a bare JSON number token when the text matches the RFC 8259 number grammar,
     else a located grammar error.
  3. A boolean location emits `true` or `false`, else a located grammar error.
  Verify with unit tests for YML-004.01 through YML-004.10, including `1.0` at a string location, `"443"` at a number
  location, and `+443`, `007`, `0x1BB`, and `yes` at the locations the scenarios name. Verify that a `0x1BB` at a
  `start` location reports a parse error whose structured entry names that `start` location (YML-010.01, PRS-006).
- [x] 2.3 Enforce the node-layer structure rules in the composer and the walk:
  1. Reject a mapping with two keys of the same text, including a plain key and its quoted form (YML-003).
  2. Reject a mapping whose key node is not a scalar, such as a sequence used as a key (YML-003.02).
  3. Key a mapping on the `<<` scalar value, so a merge key is an unknown field (YML-009.04).
  4. Ignore a node tag, so `!!int 7` keeps `"7"` and `!!omap` reads as an array (YML-004.05, YML-009.03).
  5. Reject an alias to a node that is still open on the composer's stack, which is an alias inside its own anchored
     node (YML-009.02). Reject an alias to an undefined anchor.
  6. Let a later anchor with the name of an earlier anchor redefine it, as YAML 1.2 does.
  Verify with a unit test for each rule.
- [x] 2.4 Enforce the input-stream rules:
  1. Decode bytes as UTF-8 in the binding and map a decode failure to `OscalParseError` without a lower-level decode
     error (YML-002.04, PRS-001.03). Reject a UTF-16 input.
  2. Require exactly one document, and reject a no-document, a two-document, and a syntax-error stream
     (YML-002.01 to YML-002.03).
  Verify with a unit test for each case.
- [x] 2.5 Compose the node tree from PyYAML's event stream with an explicit stack (design Decision 2). Use
  `CSafeLoader` when PyYAML provides it, else `SafeLoader`. Verify that the YAML unit tests and the YAML corpus cases
  pass with both parsers.
- [x] 2.6 Give U+0085, U+2028, and U+2029 their YAML 1.2 meaning (design Decision 2). Replace each raw occurrence with a
  free private-use placeholder before the parse, and restore it in scalar and key text. Exclude each code point that an
  escape in the text names. Report a parse error when fewer than three placeholders are free. Verify with unit tests
  that each character in a plain scalar, a quoted scalar, a block scalar, and a key gives the same value as the JSON
  path, and that an escape which names a private-use character keeps that character.
- [x] 2.7 Give each YAML-layer failure one `errors` entry with the keys `type`, `loc`, `msg`, `input`, `line`, and
  `column` (design Decision 1). `loc` is the JSON path tuple. Verify with a test that a grammar error and a Pydantic
  validation error both have `type`, `loc` as a tuple, and `msg`, and that the grammar error's `loc` names the `start`
  of the first port range (YML-010.01).
- [x] 2.8 Add a test that scans the pinned schema and fails when a resolver tie-break decides a result: a union that
  declares one key with two different scalar base types, or a scalar location with more than one base type.

## 3. Public YAML operations

- [x] 3.1 Implement `parse_oscal_yaml(data: str | bytes) -> OscalDocument`. It converts the YAML input to JSON text and
  calls `parse_oscal` (design Decision 1). Verify with unit tests that:
  1. A valid OSCAL YAML document parses to the same typed value as the equivalent JSON, from both `str` and `bytes`
     (YML-005).
  2. A YAML document carrying a field the schema does not define is a parse error (YML-005.03, PRS-004).
- [x] 3.2 Implement `parse_oscal_yaml_file(path: Path | str) -> OscalDocument`. It reads the file and parses the content
  as `parse_oscal_yaml` does, and reports the not-found condition that names the path as `parse_oscal_file` does
  (YML-006, PRS-002). Verify with unit tests that an existing file parses and a missing path reports not-found, distinct
  from the parse error.
- [x] 3.3 Implement `serialize_oscal_yaml(model: OscalDocument) -> str`. It dumps the model through the JSON value in
  block style and keeps a string-shaped scalar quoted (design Decision 4, YML-008). It writes a string that holds
  U+0085, U+2028, or U+2029 in double-quoted style. Verify with unit tests that:
  1. A document whose metadata `version` is `"1.0"` serializes and parses back to the string `"1.0"` (YML-008.02).
  2. The output, loaded as YAML, holds no `None` value at any depth (YML-008.03).
  3. A title that holds each of the three characters survives a round trip unchanged.
- [x] 3.4 Bind the three YAML names at call time, not at attribute access (design Decision 5).
  `v1/extensions/yaml_io.py` holds the three public functions with full docstrings and imports no PyYAML at module
  level. Each function imports the private `v1/extensions/_yaml_loader.py` inside its body. `v1/extensions/__init__.py`
  re-exports the three names, and `v1/__init__.py` re-exports them from `.extensions`. Remove the wrappers from
  `v1/__init__.py`. A base install without the `yaml` extra keeps every import path working, and a type checker resolves
  each function's real signature through every path. Only a call raises `ImportError` with the install hint. Verify with
  the base-install and type tests of task 8.2, and with a test that each import path gives the same function object.

## 4. Resource limit

- [x] 4.1 Replace the emitted-node budget with the alias budget and depth limit of design Decision 3 (spec
  `yaml-resource-limit`):
  1. While the walk is inside an alias, charge each emitted node (scalar, sequence, mapping, and key) and the
     characters of each scalar and key text. Raise `OscalParseError` once the nodes pass 100,000 or the characters pass
     1,000,000. Content outside every alias charges nothing.
  2. Check the written depth in the composer and the expanded depth in the walk. Raise `OscalParseError` once a node
     sits deeper than 128 levels.
  Remove the 5,000,000-node budget, the 500-level limit, and the `RecursionError` mappings. Verify with the adversarial
  and accept-side tests of task 8.1.

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

- [x] 6.1 Write each number token into the JSON text as the scalar's text, with no `json.loads` conversion (design
  Decision 1, YML-005). So an oversized numeric token gives the JSON path's parse error, and no `ValueError` escapes.
  Do not raise the recursion limit. Verify with the error-boundary test of task 8.1 that the YAML path and the JSON
  path both report `OscalParseError` for the same token.
- [x] 6.2 Add `yaml-round-trip` and `yaml-parse` handlers to the `OPERATIONS` map in `tests/test_conformance.py`,
  reading the input as the corpus manifest defines. Verify all 23 YAML corpus cases pass with
  `hatch test -- -k conformance`.
- [x] 6.3 Document the YAML usage in the README, with the correct import contract: every import works without the
  extra, and only a call raises the install hint. Add a DEVELOPING.md note on the scalar-typing rule (YML-004), the
  three YAML 1.1 line-break characters, the alias budget of 100,000 nodes and 1,000,000 characters, the nesting-depth
  limit of 128 levels (YML-011), and the YAML parse speed. Correct the module docstrings to the same rules. Narrow the
  conformance claim to exclude YML-008 and SER-005 until issue #19 closes. Verify the documented usage example runs as
  written with `hatch run python`.
- [x] 6.4 Add a drift guard in `tests/test_lint_config.py` that asserts the README and DEVELOPING.md state the values
  of the node limit, the character limit, and the depth limit that the constants hold.

## 7. Full gate

- [x] 7.1 Run the full gate with `hatch run release > ./tmp/release.log 2>&1; echo "EXIT: $?"` and read the log. Verify
  it passes end to end: generate with no `models.py` drift, then lint, typing (including the top-level YAML surface),
  security, the whole Python matrix with the YAML corpus cases, and docs.

## 8. Adversarial resource tests and base-install tests

- [x] 8.1 Write the adversarial and accept-side resource tests first, so they fail against the old limits and pass
  against tasks 4.1 and 6.1. The tests run in the default `hatch test` run, so each bomb stays small and fast. Remove
  the `slow` marker, the `-m "not slow"` default, and the release gate's `-m` override, because no test uses them.
  Each over-limit case asserts `OscalParseError` and the message of the guard that rejected it, not only the error
  type:
  1. A scalar-alias bomb: a small input that anchors one long scalar and repeats it past the character limit.
  2. A collection-alias bomb: a small input whose nested collection aliases expand past the node limit.
  3. A deep-nesting input past 128 levels, a deep input of 100,000 levels, and an input whose aliases nest past 128
     levels although its written depth is within the limit.
  4. An oversized numeric token past CPython's integer-string digit limit.
  5. Accept side: a conformant OSCAL document with modest aliasing, an alias to a collection of about 100 entries
     repeated a few times, an input nested to exactly 128 levels, and the SP 800-53 rev5 catalog written as YAML with no
     alias. Each one is not rejected for a resource limit.
  6. Memory: with `tracemalloc`, the peak traced memory of a bomb just under each budget limit stays below 100 MB.
- [x] 8.2 Write the base-install import tests and the type-surface test, with PyYAML unavailable via a `sys.modules`
  shim. Assert that each of these succeeds and binds the non-YAML names:
  1. `import oscal_bindings`.
  2. `from oscal_bindings import *`.
  3. `import oscal_bindings.extensions`, and a star import of it.
  4. `import oscal_bindings.v1.extensions.yaml_io`.
  Assert that only calling a YAML operation raises the install hint. Assert with a type-checker check that
  `parse_oscal_yaml` resolves to its real signature, not `Any`, through `oscal_bindings`, `oscal_bindings.v1`, and
  `oscal_bindings.extensions`.

## 9. Fixes from the third review

- [x] 9.1 Create the event parser inside the error handling of the composer, and map a failure at creation, including
  libyaml's `UnicodeEncodeError` for a lone surrogate, to the parse error (design Decision 2). Verify with tests for a
  NUL character and a lone surrogate with both parsers.
- [x] 9.2 Quote at most 40 characters of input text in each parse-error message, and keep the whole text in `input`
  (design Decision 1). Verify that `str(exc)` stays short for a 2 MB scalar at a number location, a 2 MB duplicate
  key, and a 2 MB undefined anchor name.
- [x] 9.3 Accept `%YAML 1.1` and `%YAML 1.2` and read both as YAML 1.2. Reject every other version with both parsers,
  and reject a surrogate-pair escape with both parsers (design Decision 2). Verify with a test for each case on both
  parsers.
- [x] 9.4 Compute the line and the character column of an invalid-UTF-8 error over LF, CR, and CRLF line breaks (design
  Decision 6). Verify with tests for CR-only line breaks and for a multibyte character before the invalid byte.
- [x] 9.5 Lower the memory cost of input without aliases: no `items` list for a scalar node, and the walk joins its
  output in chunks instead of keeping one string per node. Measure the peak against the input size with
  `tracemalloc`, state the measured factor in the README, and correct the README claim that the limits stop memory
  exhaustion: they bound alias expansion and depth. Add a test that bounds the peak for a node-dense input without
  aliases.
- [x] 9.6 Use `CSafeDumper` when PyYAML has it, else `SafeDumper`, with the escape rule of design Decision 4. Select the
  parser and the emitter through functions that a test can call with a PyYAML that has no libyaml. Verify the
  serializer with both emitters, a round trip of the SP 800-53 rev5 catalog, and the fallback selection.
- [x] 9.7 Make `tests/test_yaml_io.py` collect and pass on a PyYAML without libyaml: skip only the libyaml cases.
- [x] 9.8 Document the limit values as prose, not as exported data (design Decision 5). Document the two divergences
  from YML-005 (the datetime defect and the surrogate-pair escape) in the `yaml_io` docstring and the README. Document
  the `input` difference for a scalar at a location with no scalar type (design Decision 1).
- [x] 9.9 Add SER-004 and SER-005 to the `serialize_oscal` entry of the traceability record, because the record states
  the requirements that define an operation, not its current conformance. Make the traceability self-check tests call
  the same check functions as the guard tests, on a broken record.
- [x] 9.10 Assert `line` and `column` on the depth-limit and alias-budget errors. Record the lifetime rule of the
  `id()`-keyed schema caches. Rename `PRE_MOVE_ALL` to `PUBLISHED_ALL`.
- [x] 9.11 Run the full gate with `hatch run release > ./tmp/release.log 2>&1; echo "EXIT: $?"` and read the log.

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
