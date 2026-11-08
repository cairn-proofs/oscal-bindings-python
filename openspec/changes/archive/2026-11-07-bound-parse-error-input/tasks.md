# Tasks

## 1. Parse error entries

- [x] 1.1 In `src/oscal_bindings/v1/parser.py`, add the sentinel class and `OscalParseError.OMITTED_INPUT`, as
  [design D1](design.md#d1-a-container-input-becomes-the-sentinel-oscalparseerroromitted_input) states. Add a helper
  that replaces each `dict` or `list` `input` with the sentinel. In `parse_oscal`, apply `_name_root_keys` first and
  the helper second ([D3](design.md#d3-the-root-keys-are-read-before-the-inputs-are-replaced)), and raise the schema
  `OscalParseError` after the `except` block ([D2](design.md#d2-parse_oscal-raises-outside-the-except-block)).
  Verify with `hatch run typing`.
- [x] 1.2 Add tests in `tests/test_parser.py` for each scenario of the
  [parse-error-entries spec](specs/parse-error-entries/spec.md). Use small inputs for the entry and copy scenarios, and
  the 800-53 catalog from `nist_docs` for the memory scenario
  ([D4](design.md#d4-the-memory-test-uses-the-800-53-catalog-of-the-nist-corpus-fixture)). Do not change an existing
  test. Verify with `hatch test tests/test_parser.py`.
- [x] 1.3 Update the `OscalParseError` docstring and the README section "Error Handling": a container `input` is
  `OscalParseError.OMITTED_INPUT`, a scalar `input` stays, a limit entry has `input: None`, and `json.dumps` of the
  entries needs `default=repr`. Verify by reading both texts against design D1.

## 2. Integration checks

- [x] 2.1 Run `hatch test tests/test_parser.py tests/test_yaml_io.py tests/test_prop_serialization_preservation.py
  tests/test_conformance.py tests/test_oscal_bindings.py tests/test_traceability.py`. Verify that each passes, and that
  `git diff --stat tests/` shows only `tests/test_parser.py`.
- [x] 2.2 Measure the three faults of the proposal on the 800-53 catalog, as `tracemalloc` measures what the caught
  error holds. Verify that each one holds less than 2 MB, and record the results for the pull request.
- [x] 2.3 Run `hatch run release`. Verify that it passes.

## Workflow follow-up

- Open the pull request with `Closes #42`, with a release-notes entry for the `input` change.
- Archive the change in the pull request, before the merge.
