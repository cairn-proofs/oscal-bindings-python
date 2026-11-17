# Tasks

## 1. Baseline before the change

- [x] 1.1 Run `hatch run python scripts/bench_serialization.py` and `hatch run python scripts/bench_memory.py` on
  `main`. Record the medians, GC on and GC off, in the scratchpad. Verify that the record is not empty.

## 2. Builder error and validation of a JSON-shaped object

- [x] 2.1 Add `OscalBuilderError(ValueError)` to `src/oscal_bindings/v1/extensions/builders.py`, as
  [design D1](design.md#d1-oscalbuildererror-is-a-subclass-of-valueerror) states. Its docstring says that it is not a
  parse error and that `except ValueError` catches it. Re-export it from `src/oscal_bindings/v1/extensions/__init__.py`
  and `src/oscal_bindings/v1/__init__.py`. Add it to `tests/support/version_package.py`, and add an entry with
  `ERR-001` and `ERR-013` to `openspec/traceability.json`. Add `BMB-004` to the `make_resource` entry of that file.
  Verify that `oscal_bindings.OscalBuilderError` is
  `oscal_bindings.v1.OscalBuilderError`.
- [x] 2.2 Change `make_hash`, `make_rlink`, and `make_resource` to call `model_validate` one time on a JSON-shaped object and to raise
  `OscalBuilderError` from the `ValidationError`, as [design D2](design.md#d2-the-builders-validate-a-json-shaped-object)
  states. Update the module docstring and the docstrings of the three builders. Verify with `tests/test_builders.py`:
  1. Each test that expects `ValidationError` expects `OscalBuilderError`, and the error is not an instance of
     `OscalParseError`. This includes the `make_resource` test at `tests/test_serialization_defaults.py:184`.
  2. `make_hash("ab", "MD5")` and `make_hash("ab", "SHA-999")` return a hash whose algorithm is the string as given.
     The test that expects `ValueError` for `MD5` is removed.
  3. `make_hash("ab", " SHA-256")` raises `OscalBuilderError` whose `errors` is not empty, and the error is an instance
     of `ValueError` (the scenario of the `error-tests` delta).
  4. `make_hash("ab", HashAlgorithm.SHA_256)` and `make_hash("ab", "SHA-256")` give equal hashes, and the algorithm of
     each is `HashAlgorithm.SHA_256`. `test_algorithm_by_string`, `tests/test_prop_builders.py`, and
     `tests/test_prop_serialization_preservation.py` pass with no change.
  5. `make_rlink` with a hash from `Hash.model_construct(algorithm=" SHA-256", value="ab")` raises `OscalBuilderError`.
- [x] 2.3 Add a test in `tests/test_conformance.py`, or change one, to show that `category` maps `OscalBuilderError` to
  `builder-error`. Add the class to `_CATEGORIES` and to `test_every_category_is_mapped`, and remove the `xfail` of
  that test. Verify that `hatch test tests/test_conformance.py` passes.

## 3. Resource identifier from a key

- [x] 3.1 Add the keyword argument `key` and the module constant of the namespace to `make_resource`, as
  [design D3](design.md#d3-the-key-gives-the-identifier-before-validation) states. Document `key` in the docstring of
  `make_resource`, with a link to `docs/back-matter-keys.md` of the spec store. Verify with `tests/test_builders.py`:
  1. Two resources with the same key and different titles have the same `uuid` ([BMB-004.02]).
  2. The key `https://example.org/policies/données` gives `daa01937-2576-5dc8-9fb0-4da240946a5e` ([BMB-004.03]).
  3. A key with a `uuid` raises `OscalBuilderError` with one entry of type `key_with_uuid` at `("key",)`.
  4. An empty key raises `OscalBuilderError` with one entry of type `empty_key` at `("key",)`.
  5. No key and no `uuid` give a UUID version 4.
  6. `key=5` and `key=b"abc"` each raise `OscalBuilderError` with one entry of type `string_type` at `("key",)`, on
     each Python version of the test matrix.

## 4. Builder operations of the conformance runner

- [x] 4.1 Add the operations `build-hash`, `build-rlink`, and `build-resource` to `OPERATIONS` in
  `tests/test_conformance.py`, as [design D4](design.md#d4-the-runner-runs-the-three-builder-operations) states.
  Remove from `tests/support/expected_failures.py` the entries of the five `build-resource` cases of #62, and of the
  `build-hash`, `build-rlink`, `build-resource/generated-identifier`, and `build-resource/omitted-inputs` cases of #63.
  Change the entry of `build-resource/invalid-document-id` to point to #77. Verify that `hatch test
  tests/test_conformance.py` passes, with `build-resource/invalid-document-id` as a strict expected failure.

## 5. Docs

- [x] 5.1 Update these builder docs:
  1. The builders section of `README.md`: add a `key` example and `OscalBuilderError`.
  2. The builders bullet of "Valid OSCAL by default" in `AGENTS.md`.
  3. The `make_resource` signature and the error row of `.agents/summary/interfaces.md`.
  4. The `make_hash`, `make_rlink`, and `make_resource` rows of `.agents/summary/components.md`.
  5. The builders section of `.agents/summary/architecture.md`.
  6. The builder flow of `.agents/summary/workflows.md`.
  7. The builders sentence of "Valid OSCAL by default" in `DEVELOPING.md`.

  Verify that
  `grep -rn "ValidationError" README.md AGENTS.md .agents/summary` names no builder error, and that `hatch run docs`
  passes.

## 6. Integration

- [x] 6.1 Run `hatch run release`. Verify that it passes, and that `git diff --exit-code -- src/oscal_bindings/v1/models.py`
  shows no change.
- [x] 6.2 Run the two benchmarks of task 1.1 again. Record the before and after numbers, GC on and GC off, for the pull
  request. Update `PERFORMANCE.md` only if a number moves.
- [x] 6.3 Run `openspec validate add-builder-error-and-resource-key --strict`. Verify that it passes.

## Workflow follow-up

- Archive the change after the pull request merges.
- Close #53 and #62 with the pull request. Update #63 to say that only the `facade` operation stays open.

[BMB-004.02]: https://github.com/cairn-proofs/oscal-bindings-specs/blob/v0.8.0%2Boscal.1.2.3/openspec/specs/backmatter-builders/spec.md
[BMB-004.03]: https://github.com/cairn-proofs/oscal-bindings-specs/blob/v0.8.0%2Boscal.1.2.3/openspec/specs/backmatter-builders/spec.md
