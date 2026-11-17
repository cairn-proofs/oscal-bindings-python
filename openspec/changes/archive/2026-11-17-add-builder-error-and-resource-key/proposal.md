# Proposal

## Why

The pinned spec artifact `v0.8.0+oscal.1.2.3` has these store requirements for the back-matter builders:

1. [BMB-004]: `make_resource` accepts a key. When the caller gives a key and no identifier, the identifier is the UUID
   version 5 of the key. An empty key, or a key with an identifier, is a validation error ([#62]).
2. [ERR-013]: each validation error of a builder is in the builder-error category of [ERR-001]. It is not a parse
   error ([#62]).
3. [BMB-001]: the hash builder accepts each algorithm that the schema accepts, also an algorithm that is not a named
   algorithm ([#63]).

The binding does not meet these requirements:

1. `make_resource` in `src/oscal_bindings/v1/extensions/builders.py` has no key input.
2. The binding has no builder-error category. The builders raise `pydantic.ValidationError`, and `make_hash` raises
   `ValueError` for an unknown algorithm string ([#53]).
3. `make_hash` converts every string with `HashAlgorithm(algorithm)`, so it rejects `SHA-999`. The `Hash` model accepts
   `SHA-999`.
4. `make_resource` does not validate an item of `document_ids` or `rlinks` that is a model instance. An instance that
   the caller makes with `model_construct` goes into the resource with no validation.
5. The conformance runner has no `build-hash`, `build-rlink`, or `build-resource` operation. Thus 14 corpus cases are
   expected failures, and `test_every_category_is_mapped` is an expected failure.

The `facade` operation of [#63] is not in this change.

## What Changes

1. A new exception `OscalBuilderError`, a subclass of `ValueError`. It is not a subclass of `OscalParseError`. Each
   builder raises it for each invalid input. Its `errors` attribute holds the structured entries.
2. `make_resource` gets a keyword argument `key`. A key and no `uuid` give the UUID version 5 of [BMB-004]. An empty
   key, or a key with a `uuid`, raises `OscalBuilderError`.
3. `make_hash` converts a string that is a named algorithm to its `HashAlgorithm` member, as today, and gives any
   other string to the `Hash` model as is. Thus `SHA-999` is accepted, and ` SHA-256` raises `OscalBuilderError`.
4. The builders validate each item of a list input, also an item that is a model instance.
5. **BREAKING**: the builders do not raise `pydantic.ValidationError`. Code that catches `ValidationError` from a
   builder does not catch the new error. Code that catches `ValueError` catches it.
6. The conformance runner runs `build-hash`, `build-rlink`, and `build-resource`, and maps `OscalBuilderError` to the
   category `builder-error`. The expected-failure entries of 13 `build-*` cases and the expected failure of
   `test_every_category_is_mapped` are removed.
7. The case `build-resource/invalid-document-id` stays an expected failure. Its entry points to [#77]: the generated
   `DocumentId.identifier` has no pattern, so it accepts `""`.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

1. `error-tests`: the list of categories and classes gets the builder-error category and its class
   `OscalBuilderError`.

## Impact

1. Code: `src/oscal_bindings/v1/extensions/builders.py`, and the re-exports in
   `src/oscal_bindings/v1/extensions/__init__.py` and `src/oscal_bindings/v1/__init__.py`.
2. Tests: `tests/test_conformance.py`, `tests/support/expected_failures.py`, `tests/test_builders.py`, and
   `tests/test_serialization_defaults.py`.
3. Docs: `README.md`, `AGENTS.md`, `DEVELOPING.md`, and the `.agents/summary/` pages that name the builder errors,
   the builder construction, or the `make_resource` signature.
4. Records: `openspec/traceability.json` and the surface snapshot `tests/support/version_package.py`.
5. Public API: one new exception class, one new keyword argument, and the exception that each builder raises.

[BMB-001]: https://github.com/cairn-proofs/oscal-bindings-specs/blob/v0.8.0%2Boscal.1.2.3/openspec/specs/backmatter-builders/spec.md
[BMB-004]: https://github.com/cairn-proofs/oscal-bindings-specs/blob/v0.8.0%2Boscal.1.2.3/openspec/specs/backmatter-builders/spec.md
[ERR-001]: https://github.com/cairn-proofs/oscal-bindings-specs/blob/v0.8.0%2Boscal.1.2.3/openspec/specs/error-model/spec.md
[ERR-013]: https://github.com/cairn-proofs/oscal-bindings-specs/blob/v0.8.0%2Boscal.1.2.3/openspec/specs/error-model/spec.md
[#53]: https://github.com/cairn-proofs/oscal-bindings-python/issues/53
[#62]: https://github.com/cairn-proofs/oscal-bindings-python/issues/62
[#63]: https://github.com/cairn-proofs/oscal-bindings-python/issues/63
[#77]: https://github.com/cairn-proofs/oscal-bindings-python/issues/77
