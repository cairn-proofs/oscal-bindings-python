# Proposal

## Why

`validate_element` returns an invalid result for an element that nests deeply, for example 500 levels of groups. The
result holds one error: "Recursion error". The element is valid OSCAL, so the result is wrong. pydantic-core sets this
depth limit. The binding does not document it. The store requires a documented limit, and it requires the
limit-exceeded error for an element over that limit (ELV-004, ERR-011). The issue is
[#89](https://github.com/cairn-proofs/oscal-bindings-python/issues/89).

## What Changes

1. `validate_element` reports an element over the depth limit with a new limit-exceeded error. It returns no valid or
   invalid result for that element.
2. A new exception class, `OscalLimitExceededError`, is the limit-exceeded category. It is not an `OscalParseError`. It
   has the attribute `limit`, and its value is the new identifier `element_depth`.
3. The depth limit is the recursion guard of pydantic-core. The binding adds no walk of the element and no limit value
   of its own. A walk adds 20 to 30 percent to each call on a realistic element.
4. A group in its own `groups` list gives the same error as a deep element. So does another element that holds itself
   at a position of its own recursive type. The guard does not tell them apart.
5. `docs/limits.md` gets a section for `validate_element`. It explains why the value is approximate. `docs/errors.md`
   names the new category.
6. The three `KNOWN GAP` records in `tests/support/spec_not_applicable.py` (ELV-004.02, ERR-011.01, ERR-011.02) are
   replaced by tests that cite those scenarios.

## Capabilities

### New Capabilities

- `element-resource-limit`: the documented depth limit of element validation, the error that reports it, and the
  documentation that the limit needs.

### Modified Capabilities

- `error-tests`: the limit-exceeded category and its class, the identifier `element_depth`, and the classes that have
  the attribute `limit`.

## Impact

1. Code: `src/oscal_bindings/v1/extensions/validate_element.py` and the exports in
   `src/oscal_bindings/v1/extensions/__init__.py` and `src/oscal_bindings/v1/__init__.py`.
2. API: one new public exception class. A caller that tests `result.valid` for a deep element now gets an exception.
3. Docs: `docs/limits.md`, `docs/errors.md`, and `.agents/summary/interfaces.md`.
4. Tests and records: `tests/test_validate_element.py`, `tests/support/spec_not_applicable.py`,
   `tests/support/version_package.py` (the `PUBLISHED_ALL` set), and `openspec/traceability.json`.
5. Performance: none. The change adds no work to a call that stays within the limit.
