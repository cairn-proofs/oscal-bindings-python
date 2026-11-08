# Proposal

## Why

The 13 union aliases of `models.py` (`CatalogGroup`, `Parameter`, `Merge`, `TaskTiming`, ...) are plain unions, so
pydantic validates each union field in "smart" mode ([#43]). Smart mode tries more than one variant for each value,
and that costs parse time. On the NIST SP 800-53 rev5 catalog, with GC disabled, `OscalDocument.model_validate_json`
takes 55.5 to 56.5 ms today. A scratch copy of the models with `union_mode='left_to_right'` at each union field takes
45.7 to 46.3 ms, about 18% less.

## What Changes

1. The post-processor writes each use of a union alias in a model field as
   `Annotated[<Alias>, Field(union_mode='left_to_right')]`. Pydantic then tries the variants in manifest order and
   stops at the first one that validates.
2. Nothing else changes. The probe of [design D1](design.md#d1-union_modeleft_to_right-at-each-union-field) found these
   results:
   1. The same variant class at each union site of the 800-53 catalog (46,901 sites), the HIGH baseline profile, and
      the SSP example.
   2. The same error entries for each of the 16 inputs that it compared.
   3. The same JSON Schema of `OscalDocument`.
3. The union aliases stay plain unions, so `isinstance(value, CatalogGroup)` and type hints work as today.

Out of scope:

1. Fewer error entries for a fault inside a union value. `left_to_right` reports the same entries as smart mode. The
   contract question is cairn-proofs/oscal-bindings-specs#36.
2. `TypeAdapter(CatalogGroup)` and other direct uses of an alias. They keep smart mode.
3. The tracking of benchmark numbers in each pull request. It is a separate change.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. The change has no observable behavior other than speed, so `.openspec.yaml` sets `skip_specs: true`.

## Impact

1. Code: `scripts/postprocess_models.py` (`replace_inline_unions`) and the regenerated
   `src/oscal_bindings/v1/models.py`.
2. Tests: `tests/test_postprocess.py` (the text of the union fields of the fixture module).
3. Docs: the post-process step of `AGENTS.md` and `DEVELOPING.md`, and the module docstring of
   `scripts/postprocess_models.py`.
4. Performance: the target of [design D3](design.md#d3-the-performance-target-is-a-pass-or-fail-check).

[#43]: https://github.com/cairn-proofs/oscal-bindings-python/issues/43
