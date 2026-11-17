# Proposal

## Why

The models accept values that OSCAL rejects, and they change some values that OSCAL accepts ([#77]). The store
requirement PRS-007 says that a binding MUST NOT drop a pattern constraint silently. SER-004 says that a parse and a
serialization give a document that is equivalent to the input. The binding does not meet these requirements:

1. `fix_non_string_patterns` in `scripts/postprocess_models.py` removes `pattern=` when a type name such as `int` occurs
   as a substring in the 10 lines before the pattern. The word "integrity" in a description contains `int`. Thus 23
   `str` fields lose their pattern, among them `DocumentId.identifier` and `BackMatterResource.uuid`. The corpus case
   `build-resource/invalid-document-id` is an expected failure because of this defect.
2. The 17 date-time-with-timezone fields are `AwareDatetime` with no pattern. They accept `1850-01-01T00:00:00Z`, the
   offset `+05:17`, a lowercase `z`, a space in place of `T`, no seconds, and a JSON number such as `1700000000`.
3. The uri fields are `AnyUrl`. Codegen drops the OSCAL pattern. `AnyUrl` accepts `a:b` and `x://`, and it changes the
   value: `http://a` becomes `http://a/`, `https://example.com/a/../b` becomes `https://example.com/b`, and
   `http://a\r\nb` becomes `http://ab/`.
4. The email fields are `EmailStr`. It rejects `a@b` and `x@localhost`, which OSCAL accepts. It changes the value:
   `A@Example.COM` becomes `A@example.com`, and `Name <a@example.com>` becomes `a@example.com`.
5. The uri-reference fields are `str` with no check. They accept CR, LF, and spaces.
6. Pydantic evaluates a pattern with the Rust `regex` engine. In that engine, `.` matches CR, U+2028, and U+2029. In
   ECMA-262, the regex dialect of JSON Schema, `.` matches none of them. Thus `^\S(.*\S)?$` accepts `a\rb`, which the
   schema rejects.

## What Changes

1. One pass of the post-processor finds the base type of each pattern from the `Annotated[...]` that holds it. A
   pattern on a `str` stays. A pattern on a number goes, because JSON Schema applies `pattern` only to a string. Each
   other pattern stops the generation with a failure that names it.
2. The binding maps each OSCAL pattern to the regex engine of pydantic, and keeps the set of accepted values and the
   set of rejected values. The mapping is documented.
3. Each value of a datatype in this list must match the OSCAL pattern and the definition of the datatype. A uri,
   uri-reference, or email-address value keeps the input text:
   1. date-time-with-timezone: the value stays `AwareDatetime`. The input must be a string or a `datetime`. A
      serialization writes the `datetime`, not the input text. For example, it truncates fractional seconds after six
      digits ([#19]).
   2. uri: the value is a `str` that is a URI of RFC 3986. It is not `AnyUrl`.
   3. uri-reference: the value is a `str` that is a URI reference of RFC 3986.
   4. email-address: the value is a `str` that is a mailbox of RFC 6531. It is not `EmailStr`.
4. The binding accepts each URI scheme, for example `javascript:` and `file:`. The caller decides which schemes to use.
5. **BREAKING**: the models reject values that they accepted before, in each field of the list above and in the 23
   `str` fields of item 1 of [Why](#why). A uri field and an email field hold a `str`, not `AnyUrl` or `EmailStr`.
6. **BREAKING**: the runtime dependency is `pydantic`, not `pydantic[email]`. A caller that uses `email-validator`
   through this package must install it.
7. The corpus case `build-resource/invalid-document-id` passes.

## Capabilities

### New Capabilities

1. `datatype-constraints`: how the binding enforces the OSCAL patterns and the definitions of the datatypes
   date-time-with-timezone, uri, uri-reference, and email-address, and how the generation treats a pattern that it
   cannot place.

### Modified Capabilities

None.

## Impact

1. Code: `scripts/postprocess_models.py`, the `generate` script in `pyproject.toml`, a new private module in
   `src/oscal_bindings/v1/` for the datatype checks, and the regenerated `src/oscal_bindings/v1/models.py`.
2. Dependencies: `pyproject.toml` and each lockfile. `email-validator` and `dnspython` leave the runtime closure.
3. Tests: `tests/test_postprocess.py`, `tests/support/expected_failures.py`, `tests/test_schema_validation.py`,
   `tests/test_pydantic_version.py`, and new tests for the datatypes and for pattern completeness.
4. Docs: `README.md`, `DEVELOPING.md`, `AGENTS.md`, `.agents/summary/`, and `PERFORMANCE.md`.
5. Public API: the type of each uri, uri-reference, and email field, and the values that each field in
   [What Changes](#what-changes) accepts.

[#19]: https://github.com/cairn-proofs/oscal-bindings-python/issues/19
[#77]: https://github.com/cairn-proofs/oscal-bindings-python/issues/77
