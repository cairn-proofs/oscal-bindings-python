# Proposal

## Why

`OscalDocument.root` is a plain union of the eight document types, so pydantic validates it in "smart" mode. Smart mode
validates the document body against more than one member. On the NIST SP 800-53 rev5 catalog, `parse_oscal` takes
677 ms, and validation of `CatalogDocument` alone takes 194 ms ([#41]). The same mode makes a one-field fault in a large
document report 16 error entries. Each entry holds a copy of the document body, so the error holds about 349 MB
([#42]).

Each document type has exactly one required root key (`catalog`, `profile`, and so on). The manifest records that key
as `body-field`. A discriminator on the root key selects one member, so the binding validates the body one time.

## What Changes

1. `scripts/postprocess_models.py` emits the `root` field of `OscalDocument` as a discriminated union. Each member has a
   `Tag`. A callable `Discriminator` selects the member from the root key of the input. The tag map comes from the
   `body-field` of each `document` entry of the manifest.
2. A new hand-written module function in `oscal_bindings.v1._base` builds the discriminator. The generated module holds
   only the root-key map.
3. Input that has no known root key fails with one error entry of type `oscal_document_type`. For a JSON object, the
   message of the parse error names the keys of the object, for example a root key `assessment_plan` in the form of a
   field name.
4. The post-processor adds a step failure for each of these cases: a `document` entry without a `body-field`, two
   members with the same `body-field`, and a document class with no required field of that alias.
5. **BREAKING** (error shape only): a document that fails validation reports only the errors of the selected member.
   Entries that say the input is not some other document type no longer occur. `OscalParseError.errors` has fewer
   entries. The `loc` of each entry keeps the member class name as its first segment (for example
   `('CatalogDocument', 'catalog', …)`). The release notes state the change.
6. The JSON Schema of `OscalDocument` (`model_json_schema()`) can change shape at the root. The YAML loader resolves its
   walk against that schema, so the change includes a check of the YAML loader.
7. `scripts/bench_serialization.py` reports each median two times: with cyclic GC enabled and with it disabled. It
   drops each result before the next timed run, and it parses the document for the serialize cases only after the
   parse case. Thus the parse time does not include the GC cost of documents that the script holds.
8. The README gets a "Performance" section. It states the GC cost of a parse and the process-level settings that an
   application can use to reduce it. The library does not change the GC state.

Out of scope:

1. The 13 nested union aliases ([#43]).
2. A bound on the `input` that `OscalParseError.errors` keeps (item 2 of [#42]).

## Capabilities

### New Capabilities

- `document-type-selection`: how the binding selects one document type for the validation of a parse input. It also
  covers the error for an input that has no known root key.

### Modified Capabilities

None. The store requirements [PRS-001] and [ERR-003] stay the same. The change keeps one entry for each failure
location of the selected document type.

## Impact

1. Code: `scripts/postprocess_models.py`, `src/oscal_bindings/v1/_base.py`, `src/oscal_bindings/v1/parser.py`, and the
   regenerated `src/oscal_bindings/v1/models.py`.
2. Tests: `tests/test_base_model.py`, `tests/test_postprocess.py` (with the `get_args` check of the root annotation),
   `tests/test_parser.py`, the name-keyed property tests in `tests/test_prop_serialization_preservation.py`, and the
   README section boundary in `tests/test_lint_config.py`.
3. Callers that pin the count or the content of `OscalParseError.errors` for a parse input.
4. Performance: `parse_oscal` on the 800-53 catalog is at least 2× faster with cyclic GC disabled.
   `scripts/bench_serialization.py` measures it with GC enabled and with GC disabled.
5. Docs and tooling: `README.md` ("Performance" and "Error Handling"), `AGENTS.md`, `DEVELOPING.md`, and
   `scripts/bench_serialization.py`.
6. No dependency change. The pydantic floor (2.14.2) supports `Discriminator`, `Tag`, and the custom error arguments.

[#41]: https://github.com/cairn-proofs/oscal-bindings-python/issues/41
[#42]: https://github.com/cairn-proofs/oscal-bindings-python/issues/42
[#43]: https://github.com/cairn-proofs/oscal-bindings-python/issues/43
[PRS-001]: https://github.com/cairn-proofs/oscal-bindings-specs/blob/main/openspec/specs/document-parsing/spec.md#requirement-prs-001-parse-an-oscal-document-from-text-or-bytes
[ERR-003]: https://github.com/cairn-proofs/oscal-bindings-specs/blob/main/openspec/specs/error-model/spec.md#requirement-err-003-parse-errors-expose-structured-validation-detail
