# Proposal

## Why

Spec artifact `0.7.0+oscal.1.2.3` adds PRS-013: the root key selects the document type of the parse failures
(cairn-proofs/oscal-bindings-specs#34). It also adds the corpus case field `expected-max-failures`, with a maximum on
eight `parse` cases. This binding meets PRS-013 since [#44], but its conformance runner does not read the new field,
so the corpus cannot catch a regression. [#45] asks to move the pin.

The local spec `document-type-selection` states rules that PRS-013 now holds in the contract. The project rules forbid
the copy of normative content from one spec to another, so the local spec keeps only the binding details.

## What Changes

1. Move the pin in `scripts/spec_artifact.py` from `0.6.0+oscal.1.2.3` to `0.7.0+oscal.1.2.3` (sha256
   `39f61f5c40200882106d9df6367d5aa5ccc6d604288741a8a70e93e119fa933e`). The schema and `names.json` of 0.7.0 are the
   same bytes as in 0.6.0, so `models.py` does not change.
2. `_parse` in `tests/test_conformance.py` checks that the parse error carries no more entries than
   `expected-max-failures`.
3. `openspec/traceability.json` cites PRS-013 for `parse_oscal`, `parse_oscal_file`, `parse_oscal_yaml`,
   `parse_oscal_yaml_file`, and `OscalDoc`.
4. The local spec `document-type-selection` refers to PRS-013 for the contract rule, and keeps the binding details:
   the class name as the first `loc` segment, the first root key in input order, and the one `oscal_document_type`
   entry at `loc == ()` whose message names the keys.
5. A test docstring cites the retired scenario MDL-007.06. It cites MDL-021.03, its `replaced_by` in 0.7.0.
6. The docs that name the pin name `0.7.0+oscal.1.2.3`: `DEVELOPING.md` and `.agents/summary/`.

Out of scope:

1. More exact citations of the requirements that 0.7.0 split out, for example ERR-007 for `OscalAccessError` or FAC-005
   and FAC-006 for the assessment period. The current citations stay valid, because 0.7.0 retires no requirement.
2. A release of the package.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `document-type-selection`: two requirements refer to PRS-013 and keep only the binding details.

## Impact

1. Code: `scripts/spec_artifact.py`.
2. Tests: `tests/test_conformance.py`, `tests/test_spec_artifact_script.py` (the pinned version), and the docstring in
   `tests/test_hoist_names.py`.
3. Records and docs: `openspec/traceability.json`, `openspec/specs/document-type-selection/spec.md` (through the
   delta), `DEVELOPING.md`, and `.agents/summary/`.
4. `models.py` does not change. The CI drift check confirms it.

[#44]: https://github.com/cairn-proofs/oscal-bindings-python/pull/44
[#45]: https://github.com/cairn-proofs/oscal-bindings-python/issues/45
