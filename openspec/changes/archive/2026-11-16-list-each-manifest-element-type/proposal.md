# Proposal

## Why

The store requirement ELV-002 (cairn-proofs/oscal-bindings-specs#40) says that each type of the naming manifest has an
element-type name, whatever its kind. For OSCAL 1.2.3 the corpus file `expected/element-types.json` holds 244 names.
`get_supported_element_types()` returns 188 names ([#59]). It does not have the 44 enums and the 13 unions, and it holds
`root-model`, which is not a manifest type. Thus a caller can validate `parameter-with-select` but not `parameter`.

The pin is at `v0.8.0+oscal.1.2.3` (#70), which has the `element-types/all` corpus case. Thus the fix is now possible.

## What Changes

1. `get_supported_element_types()` returns the kebab-case name of each manifest type: 187 object and document types,
   44 enums, and 13 unions. The list has no other name.
2. **BREAKING**: the list does not hold `root-model`. `validate_element(x, "root-model")` reports the
   unknown-element-type error. The name was never an OSCAL type.
3. `validate_element` accepts each listed name. For an enum, the element is the string value of the enum, as ELV-001
   requires. The type of the `element` parameter changes from `dict[str, Any] | None` to `Any`.
4. The conformance runner runs the `element-types` operation. The `element-types/all` case passes, so its entry in
   `tests/support/expected_failures.py` goes away.

Out of scope: which branch a failure of a union element reports. That is [#69].

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. The store requirements ELV-001 and ELV-002 define this behavior, and the binding adds no detail to them. Thus
`.openspec.yaml` sets `skip_specs: true`.

## Impact

1. Code: `src/oscal_bindings/v1/extensions/validate_element.py`.
2. Tests: `tests/test_conformance.py`, `tests/support/expected_failures.py`, `tests/test_validate_element.py`, and
   `tests/test_prop_serialization_preservation.py`. The file `tests/support/element_types_snapshot.txt` goes away.
3. Docs: `AGENTS.md`, and `.agents/summary/components.md` and `data_models.md`.
4. Public API: the list of element types, and the type of the `element` parameter of `validate_element`.

[#59]: https://github.com/cairn-proofs/oscal-bindings-python/issues/59
[#69]: https://github.com/cairn-proofs/oscal-bindings-python/issues/69
