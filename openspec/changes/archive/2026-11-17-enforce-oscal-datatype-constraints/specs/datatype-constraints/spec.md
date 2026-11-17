# Spec Delta

## Purpose

Defines how the binding enforces the string patterns of the OSCAL schema and the definitions of the OSCAL datatypes
date-time-with-timezone, uri, uri-reference, and email-address. Also defines how the generation of the models treats a
pattern that it cannot place.

## ADDED Requirements

### Requirement: Each string pattern of the schema constrains its field

For each string value of the schema with a `pattern`, the model SHALL reject a value that the pattern does not match. A
string value is one of these:

1. The value of a property.
2. An item of an array.
3. A member of an `anyOf`.

This includes a pattern that the schema gives through a reference to a datatype, and each pattern of an `allOf`.

#### Scenario: An empty document identifier is rejected

- **WHEN** the caller parses a document whose `document-ids` entry has the `identifier` `""`
- **THEN** parsing reports a parse error for that `identifier`

#### Scenario: A malformed UUID is rejected

- **WHEN** the caller parses a document with a back-matter resource whose `uuid` is `not a uuid`
- **THEN** parsing reports a parse error for that `uuid`

#### Scenario: Both patterns of an allOf apply

- **WHEN** the caller parses a document whose party `email-addresses` entry is U+00A0 followed by `a@example.com`
- **THEN** parsing reports a parse error, because the pattern of the string datatype rejects the leading U+00A0

### Requirement: A pattern matches as ECMA-262 matches it

A pattern of the schema SHALL accept the same values and reject the same values as the pattern does in the ECMA-262
regex dialect with the Unicode flag, which is the dialect of JSON Schema. In that dialect, `.` matches no line
terminator: LF, CR, U+2028, or U+2029.

#### Scenario: A carriage return inside a string is rejected

- **WHEN** the caller parses a document with a property whose `value` is `a` followed by CR followed by `b`
- **THEN** parsing reports a parse error for that `value`

#### Scenario: A line separator inside a string is rejected

- **WHEN** the caller parses a document with a property whose `value` contains U+2028
- **THEN** parsing reports a parse error for that `value`

#### Scenario: A carriage return inside a markup line is accepted

- **WHEN** the caller parses a document with a `title` that is `a` followed by CR followed by `b`
- **THEN** parsing accepts the document, because the pattern of the markup-line datatype excludes only LF

#### Scenario: A Unicode letter matches a letter class

- **WHEN** the caller parses a document with a property `name` of `é1`
- **THEN** parsing accepts the document

### Requirement: The generation fails on a pattern that it cannot place

The generation of the models SHALL fail when it finds a pattern on a value that is not a string and not a number. The
failure SHALL name each such pattern. A pattern on a number value SHALL NOT constrain the field, because JSON Schema
applies `pattern` only to a string.

#### Scenario: A pattern on a boolean stops the generation

- **WHEN** the generation reads a schema with a `pattern` on a property whose type is `boolean`
- **THEN** the generation fails, names that property, and writes no models

#### Scenario: A decimal is not checked against its pattern

- **WHEN** the caller parses a mapping collection whose mapping has a `coverage` with the `target-coverage` `0.5`
- **THEN** parsing accepts the document

### Requirement: A datatype value is kept as the input gives it

A field of the datatype uri, uri-reference, or email-address SHALL hold the input text as a string, with no change.
A serialization SHALL write that text.

#### Scenario: A URI with no path keeps its form

- **WHEN** a document with a property whose `ns` is `http://a` is parsed and serialized
- **THEN** the output has `http://a`

#### Scenario: A URI with a dot segment keeps its form

- **WHEN** a document with a property whose `ns` is `https://example.com/a/../b` is parsed and serialized
- **THEN** the output has `https://example.com/a/../b`

#### Scenario: An email address keeps its case

- **WHEN** a document with the email address `A@Example.COM` is parsed and serialized
- **THEN** the output has `A@Example.COM`

### Requirement: A date-time-with-timezone value matches its pattern

A field of the datatype date-time-with-timezone SHALL accept only these values:

1. A string that matches the pattern of the datatype.
2. In Python input, a `datetime` with a timezone whose serialization matches the pattern of the datatype.

A value that the field rejects SHALL give one failure, at the location of the field.

#### Scenario: A year before 1900 is rejected

- **WHEN** the caller parses a document whose `last-modified` is `1850-01-01T00:00:00Z`
- **THEN** parsing reports a parse error for `last-modified`

#### Scenario: An offset outside the set of the pattern is rejected

- **WHEN** the caller parses a document whose `last-modified` is `2024-01-02T03:04:05+05:17`
- **THEN** parsing reports a parse error for `last-modified`

#### Scenario: A lowercase zone designator is rejected

- **WHEN** the caller parses a document whose `last-modified` is `2024-01-02T03:04:05z`
- **THEN** parsing reports a parse error for `last-modified`

#### Scenario: A number is rejected

- **WHEN** the caller parses a document whose `last-modified` is the JSON number `1700000000`
- **THEN** parsing reports a parse error for `last-modified`

#### Scenario: A datetime given by name is checked

- **WHEN** the caller constructs metadata with a `last_modified` of 1 January 1850, 00:00 UTC
- **THEN** the construction reports one validation error, at `last_modified`

#### Scenario: A valid datetime is accepted

- **WHEN** the caller parses a document whose `last-modified` is `2024-01-02T03:04:05.123-05:00`
- **THEN** parsing accepts the document

### Requirement: A uri value is a URI

A field of the datatype uri SHALL accept a value only when it matches the pattern of the datatype and is a URI by the
`URI` grammar of RFC 3986. The field SHALL accept each scheme that the grammar allows.

#### Scenario: A fragment is accepted

- **WHEN** the caller parses a document with a property whose `ns` is `https://example.com/ns#x`
- **THEN** parsing accepts the document

#### Scenario: A line break is rejected

- **WHEN** the caller parses a document with a property whose `ns` is `http://a` followed by CR, LF, and `b`
- **THEN** parsing reports a parse error for that value

#### Scenario: A space is rejected

- **WHEN** the caller parses a document with a property whose `ns` is `https://x.org/a b`
- **THEN** parsing reports a parse error for that value

#### Scenario: A one-letter scheme is rejected

- **WHEN** the caller parses a document with a property whose `ns` is `x://`
- **THEN** parsing reports a parse error for that value, because the pattern requires two or more scheme characters

#### Scenario: Each scheme is accepted

- **WHEN** the caller parses documents with properties whose `ns` values are `urn:ietf:rfc:3986`,
  `javascript:alert(1)`, and `file:///etc/passwd`
- **THEN** parsing accepts each document

### Requirement: A uri-reference value is a URI reference

A field of the datatype uri-reference SHALL accept a value only when it is a URI reference by the `URI-reference`
grammar of RFC 3986.

#### Scenario: A relative reference is accepted

- **WHEN** the caller parses documents whose link `href` values are `#ac-1`, `../a.json`, and `https://example.com/x`
- **THEN** parsing accepts each document

#### Scenario: A space is rejected

- **WHEN** the caller parses a document whose link `href` is `a b`
- **THEN** parsing reports a parse error for that `href`

#### Scenario: A line break is rejected

- **WHEN** the caller parses a document whose link `href` is `a` followed by LF and `b`
- **THEN** parsing reports a parse error for that `href`

### Requirement: An email-address value is a mailbox

A field of the datatype email-address SHALL accept a value only when it matches the pattern of the datatype and is a
mailbox by the `Mailbox` grammar of RFC 5321 as RFC 6531 extends it.

#### Scenario: A one-label domain is accepted

- **WHEN** the caller parses documents whose email addresses are `a@b` and `x@localhost`
- **THEN** parsing accepts each document

#### Scenario: A non-ASCII address is accepted

- **WHEN** the caller parses a document whose email address is `ü@例え.jp`
- **THEN** parsing accepts the document

#### Scenario: A display name is rejected

- **WHEN** the caller parses a document whose email address is `Name <a@example.com>`
- **THEN** parsing reports a parse error for that address

#### Scenario: Two at signs are rejected

- **WHEN** the caller parses a document whose email address is `a@@b`
- **THEN** parsing reports a parse error for that address

### Requirement: Each validation path applies the constraints

Each check of this capability SHALL apply on each path that validates a value: a parse, the validation of an element,
the construction of a model by field name, and a back-matter builder.

#### Scenario: Element validation rejects a malformed UUID

- **WHEN** the caller validates a `back-matter-resource` element whose `uuid` is `not a uuid`
- **THEN** the result reports invalid

#### Scenario: Construction rejects a malformed UUID

- **WHEN** the caller constructs a back-matter resource by field name with the `uuid` `not a uuid`
- **THEN** the construction reports a validation error

#### Scenario: A builder rejects an empty document identifier

- **WHEN** the caller builds a back-matter resource with a document identifier whose `identifier` is `""`
- **THEN** the builder reports a builder error
