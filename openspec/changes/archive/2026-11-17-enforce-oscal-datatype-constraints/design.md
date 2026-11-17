# Design

## Context

See [proposal.md - Why](proposal.md#why) for the motivation. These facts constrain the approach.

1. The artifact schema has 10 distinct patterns. Four datatypes have a `format` or an `allOf`: date-time-with-timezone
   (15 references), uri (16), uri-reference (13, no pattern), and email-address (1, an `allOf` of the string datatype
   and `^.+@.+$`). `DecimalDatatype` has a pattern on `type: number`.
2. Codegen merges the two patterns of an `allOf` into one pattern with lookahead: `(?=^\S(.*\S)?$)(?=^.+@.+$)`. The Rust
   `regex` engine of pydantic-core rejects lookaround when it builds the schema.
3. Pydantic applies one `pattern` per `str`. When an `Annotated` has two `Field(pattern=...)`, the last one wins.
4. Pydantic accepts `Field(pattern=...)` on `AwareDatetime`, `AnyUrl`, or a number when it builds the class. The first
   validation then raises `TypeError`, not `ValidationError`.
5. Codegen 0.83.0 reads `customTypePath` on a schema definition and emits the named type at each site of the definition.
   It ignores `customTypePath` on an `allOf`. Beside the custom type, it still emits `Field(pattern=...)`.
6. A comparison of the 10 patterns in Rust `regex` and in ECMA-262 with the `u` flag (Node.js) gives differences only
   for `.`: Rust matches CR, U+2028, and U+2029. In `\s`, Rust includes U+0085, and ECMA-262 includes U+FEFF. No schema
   pattern uses `\d`, `\w`, `\b`, lookaround, or a back-reference.
7. `AwareDatetime` accepts the JSON number `1700000000` and the string `"1700000000"`.

## Goals / Non-Goals

**Goals:**

1. Each check runs in pydantic-core with the Rust engine, so a JSON parse calls no Python function for the check.
   The one exception is a `datetime` that the caller gives in Python input
   ([D5](#d5-a-datetime-value-is-checked-as-text)).
2. The runtime package holds no schema and no regex translator. The generation and the tests own both.

**Non-Goals:**

1. A policy on URI schemes.
2. Validation of a U-label by the tables of IDNA2008.

## Decisions

### D1: The post-processor classifies each pattern by the base of its `Annotated`

One function replaces `fix_email_str_patterns` and `fix_non_string_patterns`. It parses the module with `ast` and visits
each `Annotated[base, ..., Field(..., pattern=P, ...)]`. It removes `None` from the members of `base`, then:

1. Each member is `str`: the pattern stays, as
   [D2](#d2-each-pattern-is-translated-from-ecma-262-to-rust-regex) translates it.
2. Each member is `int` or `float`: the pattern goes. JSON Schema applies `pattern` only to a string.
3. Each other base: a failure that names the class, the field, and the base.

A `pattern` keyword that is not in such an `Annotated` is also a failure. The function edits by source offset, with the
`_offsets` and `_apply` helpers. It collects each failure, and `postprocess` raises `PostprocessError` with all of them,
so a failed run writes no `models.py`.

Alternative: keep the line scan and match the base with a regex. The scan cannot know where an `Annotated` starts.
That is the defect of [#77]. Rejected.

### D2: Each pattern is translated from ECMA-262 to Rust `regex`

`scripts/regex_translation.py` holds one function, `translate(pattern) -> str`. It reads the pattern token by token and
writes a Rust pattern that accepts the same values:

1. `.` outside a class becomes a class that excludes the ECMA-262 line terminators: LF, CR, U+2028, and U+2029.
2. `\s` outside a class becomes a class of the ECMA-262 white space and line terminators: tab, LF, VT, FF, CR,
   space, U+00A0, U+1680, U+2000 to U+200A, U+2028, U+2029, U+202F, U+205F, U+3000, and U+FEFF. `\S` becomes the
   complement of that class.
3. Each other token stays: a literal, an escaped literal, a class, a negated class, `\p{...}`, a group, an
   alternation, a quantifier, `^`, and `$`. A class or a negated class can hold literals, escaped literals, and ranges.
   Without the multiline flag, `^` and `$` mean the same in both dialects.
4. Each other construct is an error that names the pattern: lookaround, a back-reference, `\d`, `\w`, `\b`, `\s`
   inside a class, and an inline flag.

The post-processor applies `translate` to each pattern of
[D1](#d1-the-post-processor-classifies-each-pattern-by-the-base-of-its-annotated) item 1. An error is a failure of the
step. `DEVELOPING.md` documents the mapping for PRS-007.

Alternative: run the checks with Python `re`. Its `\s` includes U+001C to U+001F, and `$` also matches before a final
LF. It is a second dialect to map, and each check is a Python call. Rejected.

### D3: The four datatypes are hand-written types that the hoist names

`src/oscal_bindings/v1/_datatypes.py` defines `OscalDateTimeWithTimezone`, `OscalUri`, `OscalUriReference`, and
`OscalEmailAddress`. In its copy of the schema, the hoist replaces each of the four definitions with
`{"type": "string", "customTypePath": "oscal_bindings.v1._datatypes.<Name>"}` and keeps its `title` and `description`.
Codegen then emits the type at each site, with no `pattern` beside it. The hoist does this after the closed-enum check,
which reads the original definitions.

The `Oscal` prefix keeps the names apart from the manifest names and the scalar aliases. The import guard of the
post-processor checks this.

Alternatives:

1. The post-processor finds the sites by their pattern text. uri-reference has no pattern. Rejected.
2. `--type-mappings`. It maps a format to a built-in type only. Rejected.

### D4: A string datatype is a chain of Rust patterns

Each of `OscalUri`, `OscalUriReference`, and `OscalEmailAddress` is `Annotated[str, ...]` with a `GetPydanticSchema`
that returns a `chain_schema` of `str_schema(pattern=...)` steps:

| Type | Steps |
|---|---|
| `OscalUri` | the uri pattern, then the RFC 3986 `URI` grammar |
| `OscalUriReference` | the RFC 3986 `URI-reference` grammar |
| `OscalEmailAddress` | the string-datatype pattern, the email pattern, then RFC 5321 `Mailbox` with RFC 6531 |

Each step is a full-string match in the Rust engine. The value stays the input `str`, so a serialization writes the
input text (SER-004). The JSON schema of the type is `{"type": "string"}` with its patterns.

The grammar patterns are hand-written from the ABNF of each RFC. The RFC 6531 sub-domain accepts a U-label as a run of
non-ASCII characters, letters, digits, and hyphens, with no hyphen at its start or end.

Alternative: an `AfterValidator` with Python `re`. See the alternative of
[D2](#d2-each-pattern-is-translated-from-ecma-262-to-rust-regex). Rejected.

### D5: A datetime value is checked as text

`OscalDateTimeWithTimezone` is `AwareDatetime` with a `GetPydanticSchema` that returns a `json_or_python_schema`:

1. JSON input: a chain of `str_schema(pattern=<the datetime pattern>)` and the aware `datetime_schema`. A JSON number
   fails the string step.
2. Python input: a union of the JSON chain and a strict, aware `datetime_schema` with an after-validator. The strict
   schema accepts only a `datetime` instance, so a number fails. The validator writes the value as the binding
   serializes it and matches the text with the pattern step of item 1. This validator is the one Python call of the
   checks.

The union sets `custom_error_type` and `custom_error_message`. Thus a rejected Python value gives one failure at the
field, not one failure for each member of the union at a location of pydantic. The root discriminator of `_base.py`
uses the same mechanism. These rules apply to the custom error:

1. The error type is `oscal_date_time_with_timezone`. It is not `json_invalid`, the document-type error, or a key of
   `_LIMIT_IDENTIFIERS`, because `parser.py` handles each of those types differently.
2. The message states the constraint of the field, not the type of the input. Thus it is correct for each value that
   the union rejects.

The value stays a `datetime`. The datetime pattern runs in pydantic-core, so the pattern of the schema decides the year
range and the set of offsets.

Alternatives:

1. A `str` value. It changes the type of 15 fields, and the facade operations of FAC-007 read `datetime` values.
   Rejected.
2. A wrap validator that selects one branch by the type of the input. Each failure keeps its pydantic error type, but
   the validator needs more hand-written schema code. Rejected.

### D6: The patterns of the hand-written types are literals with a drift test

`_datatypes.py` holds each OSCAL pattern as the literal output of `translate`. A test reads the four definitions of the
pinned artifact schema and checks that each literal equals `translate` of the schema pattern. A move of the pin that
changes a pattern fails this test.

Alternative: read the schema at import. The wheel ships no schema. Rejected.

### D7: A completeness test compares the models with the schema

A test walks each property of each object definition in the hoisted schema of `tests/test_hoist_names.py`. In each
property, it resolves the `$ref` chain, the `allOf`, the array `items`, and each member of an `anyOf`. Each string value
that it reaches is a site. On the model side, the test resolves the field to its leaf types in the same way. It opens
`list[...]`, each member of a union, and each scalar alias. For each site:

1. When the `$ref` chain of the site reaches one of the four datatypes, the leaf type of the model is the type of
   [D3](#d3-the-four-datatypes-are-hand-written-types-that-the-hoist-names). The test selects these sites by the `$ref`
   target, not by a pattern. The hoisted definitions hold no pattern, and uri-reference has no pattern in the schema.
2. Else, when the site has one or more patterns, the `pattern` of the leaf type equals `translate` of the schema
   pattern.

The test holds no list of exceptions.

### D8: The runtime dependency is `pydantic`

No model uses `EmailStr`, so `pyproject.toml` declares `pydantic>=2.14.2,<3`. `hatch run lock` re-locks each
environment, and `email-validator` and `dnspython` leave the lockfiles. `tests/test_pydantic_version.py` states the same
range.

## Risks / Trade-offs

1. [The U-label check is weaker than IDNA2008.] → [D4](#d4-a-string-datatype-is-a-chain-of-rust-patterns) states the
   rule. The tables of IDNA2008 need a dependency, and the stdlib `idna` codec implements IDNA2003.
2. [Codegen can stop reading `customTypePath`, or emit `pattern` beside it.] → The completeness test of
   [D7](#d7-a-completeness-test-compares-the-models-with-the-schema) fails, and
   [D1](#d1-the-post-processor-classifies-each-pattern-by-the-base-of-its-annotated) fails the generation for a pattern
   on an unknown base.
3. [An open-enum field is the union of a base type and its enum. With a new base type, smart mode can pick a different
   member for a value that is in the enum.] → `tests/test_closed_enums.py` checks the member that each union picks.
4. [The scalar aliases `URIDatatype` and `EmailAddress` can leave `models.py`. Codegen with the `generate` flags, on a
   schema of the D3 shape, emits no alias for either.] → They are binding names, not manifest names. Task 5.7 lists each
   module-level name that leaves, from `git diff`. The release notes of the breaking change name each one.
5. [Each URI, email, and datetime value gets more pattern steps.] → `PERFORMANCE.md` records the medians before and
   after, with GC on and off.

## Migration Plan

The change is breaking. It ships in the next release with the other breaking changes. Code that reads a uri or email
field as `AnyUrl` or `EmailStr` reads a `str`. Code that uses `email-validator` through this package installs it.

[#77]: https://github.com/cairn-proofs/oscal-bindings-python/issues/77
