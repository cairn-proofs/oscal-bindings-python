# Tasks

## 1. Baseline before the change

- [x] 1.1 Run `hatch run python scripts/bench_serialization.py` and `hatch run python scripts/bench_memory.py` on
  `main`. Record the medians, GC on and GC off, in the scratchpad. Verify that the record is not empty.

## 2. Tests that show each defect on `main`

- [x] 2.1 Add `tests/test_datatype_constraints.py` with one test for each scenario of
  [the spec delta](specs/datatype-constraints/spec.md). Do not change code outside `tests/`. Run
  `hatch test tests/test_datatype_constraints.py` on `main` and record the output in the scratchpad. Verify that each
  test whose scenario shows a defect of [proposal - Why](proposal.md#why) fails. Record the tests that pass on `main`,
  for example "A Unicode letter matches a letter class" and "Each scheme is accepted".
- [x] 2.2 In `tests/test_postprocess.py`, add a test: a `str` field whose `description` contains `integrity` keeps its
  `pattern` after `fix_non_string_patterns`. Verify that it fails on `main`.
- [x] 2.3 Add the completeness test of [design D7](design.md#d7-a-completeness-test-compares-the-models-with-the-schema)
  to `tests/test_hoist_names.py`, with a local `translate` that returns its input. Verify that it fails on `main`, and
  that the failure names the 23 `str` sites of [#77] and each site of the four datatypes, with the uri-reference sites.

## 3. Regex translation

- [x] 3.1 Add `scripts/regex_translation.py` with `translate`, as
  [design D2](design.md#d2-each-pattern-is-translated-from-ecma-262-to-rust-regex) states. Add
  `tests/test_regex_translation.py`, which loads the module with `load_script`. Verify with these tests:
  1. For each of the 10 patterns of the pinned schema and each probe of design Context item 6, the translated pattern
     in pydantic gives the ECMA-262 result. The test holds the expected results as a table.
  2. Each construct of D2 item 4 raises an error that names the pattern.
- [x] 3.2 Replace the local `translate` of task 2.3 with the function of task 3.1. Verify that the test still fails
  on the same sites.
- [x] 3.3 Document the mapping of D2 in `DEVELOPING.md`, in a section that cites PRS-007. Verify that the section
  lists each rule of D2 items 1 to 4.

## 4. Datatype types

- [x] 4.1 Add `src/oscal_bindings/v1/_datatypes.py` with `OscalUri`, `OscalUriReference`, and `OscalEmailAddress`, as
  [design D4](design.md#d4-a-string-datatype-is-a-chain-of-rust-patterns) states, and `OscalDateTimeWithTimezone`, as
  [design D5](design.md#d5-a-datetime-value-is-checked-as-text) states. Add `tests/test_datatypes.py`. Verify with a
  `TypeAdapter` of each type:
  1. The values of the uri, uri-reference, email-address, and date-time-with-timezone scenarios of the spec delta give
     the expected result in JSON input and in Python input.
  2. Each accepted string value serializes to the input text.
  3. In Python input, an `int` and a naive `datetime` fail for `OscalDateTimeWithTimezone`.
  4. In Python input, a `datetime` of 1 January 1850, 00:00 UTC, gives one error for `OscalDateTimeWithTimezone`, at
     the location of the value, with the error type of D5.
- [x] 4.2 Add the drift test of
  [design D6](design.md#d6-the-patterns-of-the-hand-written-types-are-literals-with-a-drift-test) to
  `tests/test_datatypes.py`. Verify that it passes, and that it fails when one literal in `_datatypes.py` changes.

## 5. Generation

- [x] 5.1 In `scripts/hoist_names.py`, replace the four datatype definitions in the copy, as
  [design D3](design.md#d3-the-four-datatypes-are-hand-written-types-that-the-hoist-names) states. Add a step to the
  module docstring. Verify with a test in `tests/test_hoist_names.py` that each of the four definitions of the hoisted
  schema has its `customTypePath`, its `title`, and its `description`, and no `pattern`, `format`, or `allOf`.
- [x] 5.2 In `scripts/postprocess_models.py`, replace `fix_email_str_patterns` and `fix_non_string_patterns` with the
  function of [design D1](design.md#d1-the-post-processor-classifies-each-pattern-by-the-base-of-its-annotated), and
  apply `translate` of task 3.1. Replace the tests of the two old functions in `tests/test_postprocess.py`, and move the
  test of task 2.2 to the new function. Verify with tests:
  1. A `str` pattern stays and is translated, also when the description contains `integrity` or `point`.
  2. A pattern on `int` or `float` goes.
  3. A pattern on `bool`, on `AwareDatetime`, on a union of `str` and `int`, and outside an `Annotated` each give a
     failure that names the site. One run reports each failure, and writes no output file.
- [x] 5.3 Update the post-processing text in the module docstring of `scripts/postprocess_models.py`, `DEVELOPING.md`
  step 3.1, and `AGENTS.md` "Code Generation Pipeline" step 3. Verify with a `grep` for `fix_non_string_patterns`,
  `AnyUrl`, and `EmailStr` in the three files that no text describes the old behavior.
- [x] 5.4 Run `hatch run generate`. Verify that it passes, that `src/oscal_bindings/v1/models.py` has no `AnyUrl`,
  `EmailStr`, or lookahead, and that each `pattern` of `models.py` is on a `str`.
- [x] 5.5 Remove `build-resource/invalid-document-id` from `tests/support/expected_failures.py`. Run `hatch test`.
  Verify that each test of tasks 2.1, 2.3, and 4.1 passes, and that the strict expected failures of
  `tests/test_conformance.py` stay expected failures.
- [x] 5.6 Fix each test that the new types break, with no change to a model. Examine `tests/test_closed_enums.py`
  ([design Risks](design.md#risks--trade-offs) item 3), `tests/strategies.py`, and `tests/test_schema_validation.py`,
  whose docstring names `AwareDatetime`, `EmailStr`, and `AnyUrl`. Verify that `hatch test --all` passes.
- [x] 5.7 List each module-level name that `git diff` of `src/oscal_bindings/v1/models.py` shows as removed after task
  5.4. [Design Risks](design.md#risks--trade-offs) item 4 expects `URIDatatype` and `EmailAddress`. Record the list for
  the commit message of the workflow follow-up. Verify that the list holds each removed name and no other name.
- [x] 5.8 Document the four datatypes in `AGENTS.md` "Repo-Specific Patterns & Gotchas" and in
  `.agents/summary/components.md` and `.agents/summary/data_models.md`: the value type, the checks, and that a uri,
  uri-reference, or email-address value keeps the input text. Verify with a `grep` for `AnyUrl` and `EmailStr` in `AGENTS.md` and `.agents/summary/` that
  no text describes the old types.

## 6. Runtime dependency

- [x] 6.1 Change the runtime dependency to `pydantic>=2.14.2,<3`, as
  [design D8](design.md#d8-the-runtime-dependency-is-pydantic) states. Update `tests/test_pydantic_version.py`, the
  comments in `pyproject.toml`, `README.md` line 23, the Pydantic floor entry of `DEVELOPING.md`, and the
  "Config-Derived Facts" of `AGENTS.md`. Run `hatch run lock`. Verify that no lockfile has `email-validator` or
  `dnspython`, and that `hatch test tests/test_pydantic_version.py` passes.

## 7. Integration

- [x] 7.1 Run `hatch run release`. Verify that it passes, and that a second `hatch run generate` gives no change to
  `src/oscal_bindings/v1/models.py`.
- [x] 7.2 Run the two benchmark scripts of task 1.1 again. Update `PERFORMANCE.md` with the before and after medians,
  GC on and GC off. Verify that the record has both runs.

## Workflow follow-up

- Commit as `fix!:` with a `BREAKING CHANGE` footer. The footer says that the models reject values that they accepted
  before, that a uri or email field holds a `str`, that the runtime dependency is `pydantic` without the `email` extra,
  and which scalar aliases of task 5.7 left the module. Close #77.
- Report the medians of task 7.2 in the PR description.
- Archive the change after review.

[#77]: https://github.com/cairn-proofs/oscal-bindings-python/issues/77
