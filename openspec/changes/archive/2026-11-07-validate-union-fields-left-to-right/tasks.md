# Tasks

## 1. Baseline before the change

- [x] 1.1 Run `hatch run python scripts/bench_serialization.py --catalog <path>` for each document of
  [design Context item 4](design.md#context), from the NIST and AWS corpus caches. Record the `parse_oscal(bytes)`
  medians, GC on and GC off.
- [x] 1.2 Record, for each document of the NIST, AWS, local, and spec-artifact corpora, the class of each value at each
  union site, and record the error entries of each invalid input of the spec-artifact corpus. Save both in the
  scratchpad. Verify that the record is not empty.

## 2. Post-processor and regeneration

- [x] 2.1 Add the optional `wrap` argument to `replace_inline_unions`, and pass it from `add_union_aliases`, as
  [design D1](design.md#d1-union_modeleft_to_right-at-each-union-field) states. Update the module docstring of
  `scripts/postprocess_models.py`. Verify that the emitted lines of the fixture module pass
  `black --check -S -l 88`.
- [x] 2.2 Update `test_inline_unions_of_the_variant_set_use_the_alias` in `tests/test_postprocess.py` for the new field
  text, and add a test that the `generated` fixture module validates a union field. Verify with
  `hatch test tests/test_postprocess.py tests/test_prop_postprocess.py`.
- [x] 2.3 Run `hatch run generate`. Verify that the diff of `models.py` changes only the union fields, and that
  `hatch test tests/test_models_manifest.py` passes with no change.
- [x] 2.4 Update the post-process step of `AGENTS.md` and `DEVELOPING.md`. Verify by reading both against design D1.

## 3. Checks

- [x] 3.1 Repeat task 1.2 on the new models and compare. Verify that each union site has the same class, and that
  each invalid input gives the same error entries.
- [x] 3.2 Repeat task 1.1. Verify the targets of
  [design D3](design.md#d3-the-performance-target-is-a-pass-or-fail-check): the GC-off median of the catalog is at
  least 10% lower, and no other document is more than 5% slower. If a target fails, stop and report before task 3.3.
- [x] 3.3 Run `hatch run release`. Verify that it passes, and that a second `hatch run generate` leaves `models.py`
  unchanged.

## Workflow follow-up

- Open the pull request with `Closes #43`. Report the benchmark runs of tasks 1.1 and 3.2 in it.
- Archive the change in the pull request, before the merge.
