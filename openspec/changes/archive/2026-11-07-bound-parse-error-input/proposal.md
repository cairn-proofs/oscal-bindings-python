# Proposal

## Why

A parse error can hold a copy of a large part of the input document ([#42]). The `input` of each entry of
`OscalParseError.errors` is the failing value. For a `missing` field, that value is the whole parent object. The
original `ValidationError` stays reachable through `__cause__` and holds the same values. On the NIST SP 800-53 rev5
catalog (10.4 MB), a catalog without `metadata` gives one entry, and the error holds 25.7 MB after the raise: 2.5×
the document. [#44] removed the fan-out over the eight document types, but the nested unions ([#43]) still add an
`extra_forbidden` entry whose `input` is a group's `controls` list. Three invalid control `id`s in each of 20 groups
give 80 entries, and the error holds 25.0 MB.

## What Changes

1. **BREAKING** (error content only): when the failing value of a schema entry of `OscalParseError.errors` is an
   object or an array, its `input` is the sentinel `OscalParseError.OMITTED_INPUT`, with the repr `<omitted input>`.
   A scalar `input` (a string, a number, a boolean, or a null) stays. A limit entry keeps `input: None`. `None` would
   read as a null input, so the sentinel states that the binding did not keep the value.
2. `parse_oscal` raises its `OscalParseError` outside the `except` block, as it does for a limit entry. Thus
   neither `__cause__` nor `__context__` holds the `ValidationError` and its copy of the input.
3. The `oscal_document_type` entry of an object with no known root key still names the keys of the object in its
   message. The binding reads the keys before it replaces the `input`.
4. The `OscalParseError` docstring and the README section "Error Handling" state the `input` contract.

Out of scope:

1. The nested-union entries themselves ([#43], cairn-proofs/oscal-bindings-specs#36). This change bounds what each
   entry holds, not how many entries a fault gives.
2. `validate_element`. Its result holds a path and a message for each failure, not the input.

## Capabilities

### New Capabilities

- `parse-error-entries`: what the structured entries of a parse error hold, and what the parse error keeps of the
  input.

### Modified Capabilities

None. The store requirements [ERR-003] and [PRS-006] require a location for each entry, not the input value.

## Impact

1. Code: `src/oscal_bindings/v1/parser.py` (the sentinel, `parse_oscal`, and the `OscalParseError` docstring).
2. Tests: new tests in `tests/test_parser.py`. No existing test changes. The public surface (`__all__`) and the
   traceability record stay as they are, because the sentinel is a class attribute.
3. Docs: `README.md` "Error Handling".
4. Callers that read a dict or a list from `errors[i]["input"]`, and callers that pass the entries to `json.dumps`
   without a `default`. The `type`, `loc`, and `msg` of each entry stay.
5. All parse operations get the change, because each one goes through `parse_oscal`: the typed parsers,
   `parse_oscal_file`, the YAML parse operations, and the `OscalDoc` constructors.

[#42]: https://github.com/cairn-proofs/oscal-bindings-python/issues/42
[#43]: https://github.com/cairn-proofs/oscal-bindings-python/issues/43
[#44]: https://github.com/cairn-proofs/oscal-bindings-python/pull/44
[ERR-003]: https://github.com/cairn-proofs/oscal-bindings-specs/blob/main/openspec/specs/error-model/spec.md#requirement-err-003-parse-errors-expose-structured-validation-detail
[PRS-006]: https://github.com/cairn-proofs/oscal-bindings-specs/blob/main/openspec/specs/document-parsing/spec.md#requirement-prs-006-schema-validation-failures-carry-structured-error-detail
