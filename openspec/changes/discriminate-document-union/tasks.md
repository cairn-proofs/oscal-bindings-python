# Tasks

## 1. Root-key discriminator in `_base.py`

- [x] 1.1 Add `root_key_discriminator(root_keys)` to `src/oscal_bindings/v1/_base.py`, as
  [design D3](design.md#d3-the-discriminator-logic-lives-in-_basepy-the-generated-module-holds-only-the-map) states:
  the dict, model-instance (MRO), and other-input cases, and the `oscal_document_type` custom error. Verify with
  `hatch run typing` (mypy passes).
- [x] 1.2 Add unit tests in `tests/test_base_model.py` over a two-member test `RootModel`. Cover each case of D3: the
  first known key in input order, a member instance, a subclass instance, a dict with no known key, a list, and a
  scalar. Assert the single `oscal_document_type` entry with `loc == ()`. Verify with
  `hatch test tests/test_base_model.py`.

## 2. Post-processor step

- [x] 2.1 Add `discriminate_document_union` to `scripts/postprocess_models.py` and call it after `rename_document_union`
  in `postprocess`. It rewrites only the `root` field of `OscalDocument` to the tagged form of
  [design D3](design.md#d3-the-discriminator-logic-lives-in-_basepy-the-generated-module-holds-only-the-map). It keeps
  the codegen member order and the base `RootModel[...]` subscript
  ([D5](design.md#d5-the-base-rootmodel-keeps-the-plain-union)). It adds the `Tag` import from `pydantic` and the
  `root_key_discriminator` import from `oscal_bindings.v1._base`. Verify that the emitted text is in the black format of
  the committed module: `black --check` on the output of the test fixture passes.
- [x] 2.2 Add the four step failures of
  [design D4](design.md#d4-the-root-key-map-comes-from-the-manifest-body-field). Verify with one test for each failure
  in `tests/test_postprocess.py` `TestOscalDocument`. Each test asserts the `PostprocessError` message names the entry.
- [x] 2.3 Add `body-field` to the document entries of the synthetic manifest in `tests/test_postprocess.py`, and add a
  test that the `generated` fixture module rejects a dict with no known root key with one `oscal_document_type` entry.
  Verify with `hatch test tests/test_postprocess.py tests/test_prop_postprocess.py`.
- [x] 2.4 Update the module docstring of `scripts/postprocess_models.py` (item 2.2 of its list), the "Post-process"
  step of `AGENTS.md`, and the matching section of `DEVELOPING.md` to state that the document union is discriminated on
  the manifest `body-field`. Verify by reading the three texts against design D3 and D4.

## 3. Regenerate and adapt the binding tests

- [x] 3.1 Run `hatch run generate`. Verify that `git diff src/oscal_bindings/v1/models.py` changes only the imports and
  the `root` field of `OscalDocument`, and that the root-key map has eight entries equal to the manifest `body-field`s.
- [x] 3.2 Update `test_oscal_document_is_the_root_model_of_the_documents` in `tests/test_postprocess.py` to read the
  members through the `Annotated` root and to assert each `Tag` equals the member class name. Verify with
  `hatch test tests/test_postprocess.py tests/test_models_manifest.py`.
- [x] 3.3 Add parser tests in `tests/test_parser.py` for each scenario of the
  [document-type-selection spec](specs/document-type-selection/spec.md). For the fault scenario, set one control `id`
  of a catalog to an integer and assert the exact error count and that each `loc` starts with `'CatalogDocument'`.
  Verify with `hatch test tests/test_parser.py`.
- [x] 3.4 Run `hatch test tests/test_parser.py tests/test_closed_enums.py tests/test_prop_serialization_preservation.py
  tests/test_document.py`. Fix each test that pins the old error count. Do not change a `loc` assertion: design D2 keeps
  each location. In the two name-keyed property tests, expect one `oscal_document_type` entry at `()` for a root-key
  site, and `extra_forbidden` at every other site
  ([design D7](design.md#d7-the-parse-operation-names-the-root-keys-of-an-object-with-no-known-root-key)).
- [x] 3.6 In `parse_oscal`, rewrite the message of a lone `oscal_document_type` entry whose `input` is a dict with keys
  to name the keys ([design D7](design.md#d7-the-parse-operation-names-the-root-keys-of-an-object-with-no-known-root-key)).
  Add parser tests for the name-keyed root scenario of the spec, for `{}`, and for a non-object input. Verify with
  `hatch test tests/test_parser.py tests/test_yaml_io.py tests/test_prop_serialization_preservation.py`.
- [x] 3.5 Print `OscalDocument.model_json_schema()` without `$defs` and confirm the root is a `oneOf` of the eight
  member `$ref`s ([design D6](design.md#d6-the-json-schema-of-the-root-becomes-oneof)). Run
  `hatch test tests/test_yaml_io.py` and verify that it passes. Record the root shape for the pull request.

## 4. Integration checks

- [x] 4.1 Run `hatch test tests/test_conformance.py tests/test_local_corpus.py`. Verify that each corpus document parses
  and that `tests/support/expected_failures.py` is unchanged.
- [x] 4.2 Run `hatch run python scripts/bench_serialization.py` before and after the change on the 800-53 catalog.
  Verify that the `parse_oscal(bytes)` median is at least 2× faster with cyclic GC disabled. Record both results for
  the pull request. Result (Python 3.14.8): 160 → 63 ms (2.5×) with GC disabled, and 253 → 157 ms (1.6×) as the
  script runs. About 95 ms of each run is cyclic GC, which does not depend on the union.
- [x] 4.3 Run `hatch run release`. Verify that it passes, and that `git diff --exit-code --
  src/oscal_bindings/v1/models.py` is clean after a second `hatch run generate`.
- [ ] 4.4 Draft the release-notes entry: fewer `OscalParseError.errors` entries for a document fault, each `loc`
  unchanged, the new `oscal_document_type` error for input with no known root key, the `oneOf` root schema, and the
  parse speed result. Verify that the pull request description holds the entry and cites #41 and #42.

## 5. Benchmark and performance documentation

- [x] 5.1 Change `scripts/bench_serialization.py` as
  [design D9](design.md#d9-the-benchmark-measures-the-binding-not-the-gc-cost-of-the-harness) states, and update its
  docstring. Verify that `hatch run python scripts/bench_serialization.py` prints a GC-on and a GC-off median for each
  case, and that `hatch run release` (ruff, mypy, bandit) passes.
- [x] 5.2 Add a "Performance" section to `README.md` with the facts of
  [design D8](design.md#d8-the-cyclic-gc-cost-of-a-parse-is-an-application-setting-not-a-library-setting): the tracked
  objects of a parse, the GC cost and its growth with the live objects, and `gc.freeze()` and `gc.set_threshold()` as
  application settings. Add the `oscal_document_type` entry to "Error Handling". Verify that each number in the README
  equals a measured number of this change.

## Workflow follow-up

- Archive the change after the pull request merges.
- Comment on #42 with the error count and memory result of task 3.3, and on #43 that the nested unions remain.
