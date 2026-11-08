# Tasks

## 1. Move the pin

- [x] 1.1 Set `SPEC_ARTIFACT_VERSION` to `0.7.0+oscal.1.2.3` and `SPEC_ARTIFACT_SHA256` to
  `39f61f5c40200882106d9df6367d5aa5ccc6d604288741a8a70e93e119fa933e` in `scripts/spec_artifact.py`, and update the
  pinned version in `tests/test_spec_artifact_script.py`. Verify that the sha256 equals `SHA256SUMS` of the published
  store release, and that `hatch test tests/test_spec_artifact_script.py tests/test_spec_artifact.py` passes.
- [x] 1.2 Run `hatch run generate`. Verify that `git diff --exit-code -- src/oscal_bindings/v1/models.py` reports no
  change.

## 2. Conformance and traceability

- [x] 2.1 In `_parse` of `tests/test_conformance.py`, check that the parse error carries no more entries than
  `expected-max-failures` when the case has the field. Verify with `hatch test tests/test_conformance.py`, and verify
  that the check fails when the maximum of `parse/two-failures` is set to 1 in a scratch copy of the corpus index.
- [x] 2.2 In `openspec/traceability.json`, add `PRS-013` to `parse_oscal`, `parse_oscal_file`, `parse_oscal_yaml`,
  `parse_oscal_yaml_file`, and `OscalDoc`. Verify with `hatch test tests/test_traceability.py`.
- [x] 2.3 In the docstring of `test_merge_of_different_bodies_fails_and_names_both_sites` in
  `tests/test_hoist_names.py`, replace `MDL-007.06` with `MDL-021.03`. Verify that a search of `src`, `tests`, and the
  docs finds no scenario identifier that 0.7.0 retires.

## 3. Docs

- [x] 3.1 Replace `0.6.0+oscal.1.2.3` with `0.7.0+oscal.1.2.3` in `DEVELOPING.md` and `.agents/summary/`. Verify that a
  search outside `openspec/changes/archive/` finds no `0.6.0+oscal.1.2.3`.

## 4. Full gate

- [x] 4.1 Run `hatch run release`. Verify that it passes, and that `models.py` is unchanged.
- [x] 4.2 Run `scripts/bench_serialization.py` on the 800-53 catalog, and record the `parse_oscal(bytes)` medians for
  the pull request. The change is not expected to move them.

## Workflow follow-up

- Open the pull request with `Closes #45`, with the benchmark numbers.
- Archive the change in the pull request, before the merge. The archive syncs the `document-type-selection` delta.
