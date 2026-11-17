# Tasks

## 1. Baseline before the change

- [x] 1.1 Run `hatch run python scripts/bench_serialization.py` and `hatch run python scripts/bench_memory.py` on
  `main`. Record the medians, GC on and GC off, in the scratchpad. Verify that the record is not empty.

## 2. Element map and validation

- [x] 2.1 Change `_build_element_map()` in `src/oscal_bindings/v1/extensions/validate_element.py` as
  [design D1](design.md#d1-find-the-types-in-the-models-module-by-their-run-time-form) states. Verify that
  `get_supported_element_types()` returns 244 names and that `root-model` is not one of them.
- [x] 2.2 Validate an enum or a union element through a cached `TypeAdapter`, and change the type of `element` to
  `Any`, as
  [design D2](design.md#d2-a-typeadapter-validates-an-enum-or-a-union-and-the-adapter-is-made-on-first-use) states.
  Update the docstring. Verify with new tests in `tests/test_validate_element.py`:
  1. `validate_element("SHA-256", "hash-algorithm")` is valid, and `validate_element("sha-256", "hash-algorithm")` is
     not valid.
  2. A valid parameter is valid for `parameter`, and a parameter with an unknown key is not valid.
  3. `validate_element({}, "root-model")` reports the unknown-element-type error.
- [x] 2.3 Update `tests/test_prop_serialization_preservation.py` and delete `tests/support/element_types_snapshot.txt`,
  as [design D3](design.md#d3-the-corpus-case-replaces-the-snapshot-of-the-list) items 2 and 3 state. Verify with
  `hatch test tests/test_prop_serialization_preservation.py tests/test_validate_element.py
  tests/test_prop_validate_element.py`.
- [x] 2.4 Update `AGENTS.md` (the `validate_element` gotcha) and `.agents/summary/components.md` and `data_models.md`.
  Delete each mention of the snapshot and of `root-model`. Verify that `grep -rn "root-model\|element_types_snapshot"`
  over the repo finds no hit outside `openspec/changes/`.

## 3. Conformance runner

- [x] 3.1 Add the `element-types` operation to `tests/test_conformance.py`, and pass the input path only when the case
  has `input`, as [design D3](design.md#d3-the-corpus-case-replaces-the-snapshot-of-the-list) item 1 states. Remove the
  `element-types/all` entry from `tests/support/expected_failures.py`. Verify that
  `hatch test tests/test_conformance.py -k element-types` passes.

## 4. Checks

- [x] 4.1 Repeat task 1.1. Verify that no median moves by more than the run-to-run spread of the two runs.
- [x] 4.2 Run `hatch run release`. Verify that it passes.

## Workflow follow-up

- Open the pull request with `Closes #59`. Report the benchmark runs of tasks 1.1 and 4.1 in it, and name the removal
  of `root-model`.
- Archive the change in the pull request, before the merge.
