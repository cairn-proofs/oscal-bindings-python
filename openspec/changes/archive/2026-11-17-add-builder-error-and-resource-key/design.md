# Design

## Context

See [proposal.md - Why](proposal.md#why) for the motivation. These facts constrain the approach.

1. The `Hash.algorithm` field is the union of the string datatype alias and `HashAlgorithm`. The model accepts
   `SHA-999` and `MD5`, and rejects ` SHA-256` with two entries, one for each member of the union.
2. Pydantic does not validate a model instance again when the instance is the value of a field
   (`revalidate_instances` is `never`). Thus `DocumentId.model_construct(identifier="")` goes into a
   `BackMatterResource` with no validation.
3. The corpus README says that the runner gives each item of `hashes` and `document-ids` to the builder as the element
   of the binding, with no validation. In Python, that element is `model_construct` of the item JSON.
4. The conformance runner (`category` in `tests/test_conformance.py`) maps a class to a category.
   `test_every_category_is_mapped` is a strict expected failure until the builder-error category has a class.
5. A name in `v1.__all__` must be in the surface snapshot (`tests/support/version_package.py`) and in
   `openspec/traceability.json`.

## Goals / Non-Goals

**Goals:**

1. Each invalid input to a builder gives one `OscalBuilderError`, with the structured entries of the failure.

**Non-Goals:**

1. The missing patterns of the generated models ([#77]). The case `build-resource/invalid-document-id` stays an
   expected failure until that issue is fixed.

## Decisions

### D1: `OscalBuilderError` is a subclass of `ValueError`

`pydantic.ValidationError` is a subclass of `ValueError`. With `OscalBuilderError(ValueError)`, code that catches
`ValueError` from a builder continues to catch each builder error. The class is not a subclass of `OscalParseError`
([ERR-013.02]).

The class has the same constructor and `errors` attribute as `OscalParseError`: `OscalBuilderError(message, errors)`.
`errors` holds the entries in the Pydantic entry shape (`type`, `loc`, `msg`, `input`). A builder raises it
`from` the `ValidationError`, so `__cause__` keeps the original error. The input of a builder is small and comes from
the caller, so the error does not omit `input` as `OscalParseError` does.

The class is in `builders.py`. It goes through the re-export chain: `v1/extensions/__init__.py` and `v1/__init__.py`.
The top level takes it from `v1.__all__`.

Alternative: a subclass of `pydantic.ValidationError`. Code that catches `ValidationError` then continues to work. But
each key error must be made with `ValidationError.from_exception_data` and a custom line error, and the public error
class then depends on the internals of pydantic-core. Rejected.

### D2: The builders validate a JSON-shaped object

Each builder makes one object with the JSON keys of the element and calls `model_validate` on it one time. An item of
a list input that is a model instance goes into the object as `item.model_dump()`. An item of another type goes in as
is. Thus the model validates each item, also an item that the caller made with `model_construct`. An item that is not
a model gives the current `model_type` entry.

`make_hash` converts a string that is a `HashAlgorithm` value to the member, and puts any other string into the object
as is. Thus `make_hash(d, "SHA-256").algorithm is HashAlgorithm.SHA_256`, as today. `SHA-999` stays a string, which
the model accepts, and ` SHA-256` stays a string, which the model rejects. `HashAlgorithm` is not a `str` enum, so
with no conversion the string would stay a `str` and would not equal the member.

A `ValidationError` from `model_validate` becomes an `OscalBuilderError` as [D1](#d1-oscalbuildererror-is-a-subclass-of-valueerror) shows.

Alternative: set `revalidate_instances='always'` on `OscalBaseModel`. This validates each nested instance again on each
construction in each part of the binding, not only in the builders. Rejected.

### D3: The key gives the identifier before validation

`make_resource` gets the keyword argument `key: str | None = None`. Before it makes the object of
[D2](#d2-the-builders-validate-a-json-shaped-object), it validates the key and the `uuid`:

1. A key that is not a `str` raises `OscalBuilderError` with one entry of type `string_type` at `loc == ("key",)`.
   Without this check, `uuid.uuid5` raises `TypeError` for an `int`, and for `bytes` it raises on 3.11 but not on 3.12
   and later.
2. A key with a `uuid` raises `OscalBuilderError` with one entry of type `key_with_uuid` at `loc == ("key",)`.
3. An empty key raises `OscalBuilderError` with one entry of type `empty_key` at `loc == ("key",)`.
4. A key and no `uuid` give `str(uuid.uuid5(NAMESPACE, key))`. `uuid.uuid5` encodes a `str` name as UTF-8, as
   [BMB-004] requires.
5. No key and no `uuid` give `str(uuid.uuid4())`.

`NAMESPACE` is a module constant, `uuid.UUID("3942257f-e1cf-5e06-9c6f-eeb97ecabe77")`, the namespace that [BMB-004]
states. The binding does not derive it from the URL in `docs/back-matter-keys.md` of the spec artifact.

### D4: The runner runs the three builder operations

The runner gets `build-hash`, `build-rlink`, and `build-resource`. A builder case has no input. Each operation:

1. Maps the JSON keys of `arguments` to the keyword arguments of the builder. `media-type` gives `media_type`,
   `document-ids` gives `document_ids`, and `identifier` gives `uuid`.
2. Gives each item of `hashes` or `document-ids` as `Hash.model_construct(...)` or `DocumentId.model_construct(...)`
   of the item JSON (see [Context](#context) item 3).
3. Validates `expected-category` with `_expect_error`, compares the `uuid` with `expected-uuid`, or compares the
   canonical JSON of the result with `expected-element`. For a `build-resource` case with no `key` and no `identifier`,
   it validates the `uuid` of the result against the UUID pattern of the schema, and removes `uuid` before the compare.

`category` maps `OscalBuilderError` to `builder-error`.

## Risks / Trade-offs

1. [Code that catches `pydantic.ValidationError` from a builder does not catch the new error.] → The proposal marks
   the change as breaking. `OscalBuilderError` is a `ValueError`, so `except ValueError` continues to work.
2. [`model_dump` of an item that the caller made with `model_construct` and values of the wrong type can emit a
   Pydantic serialization warning before the validation error.] → The builder still raises `OscalBuilderError`. The
   warning comes only from an item that bypassed validation.

[BMB-004]: https://github.com/cairn-proofs/oscal-bindings-specs/blob/v0.8.0%2Boscal.1.2.3/openspec/specs/backmatter-builders/spec.md
[ERR-013.02]: https://github.com/cairn-proofs/oscal-bindings-specs/blob/v0.8.0%2Boscal.1.2.3/openspec/specs/error-model/spec.md
[#77]: https://github.com/cairn-proofs/oscal-bindings-python/issues/77
