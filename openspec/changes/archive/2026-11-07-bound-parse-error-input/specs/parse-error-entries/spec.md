# Spec Delta

## Purpose

Defines what the structured entries of a parse error hold of the failing values, and what the parse error keeps of
the input document.

## ADDED Requirements

### Requirement: An entry keeps a scalar input and marks an omitted container input

Each structured entry of a schema-conformance parse error SHALL meet these conditions:

1. When the failing value is a string, a number, a boolean, or a null, `input` is that value.
2. When the failing value is an object or an array, `input` is the sentinel `OscalParseError.OMITTED_INPUT`.

The sentinel SHALL have the repr `<omitted input>`, and a copy, a deep copy, or a pickle round trip of the sentinel
SHALL give the same object.

#### Scenario: A missing field

- **WHEN** the caller parses a catalog that has no `metadata`
- **THEN** the parse error has one `missing` entry for `metadata`, and its `input` is the sentinel

#### Scenario: A scalar of the wrong type

- **WHEN** the caller parses a catalog in which the `id` of one control is the number 5
- **THEN** the `input` of the entry for that `id` is 5

#### Scenario: An unknown key with an array value

- **WHEN** the caller parses a catalog whose body has the unknown key `bogus` with an array value
- **THEN** the `input` of the `extra_forbidden` entry for `bogus` is the sentinel

#### Scenario: An object with no known root key

- **WHEN** the caller parses the JSON object `{"metadata": {}}`
- **THEN** the `input` of the `oscal_document_type` entry is the sentinel, and its message names the key `metadata`

#### Scenario: The sentinel survives a copy

- **WHEN** the caller deep-copies or pickles the entries of a parse error with a sentinel `input`
- **THEN** the `input` of the copy is the same sentinel object

### Requirement: A parse error holds no copy of the input document

A parse error SHALL hold no reference to the validation exception of the parse. Neither the cause nor the context of
the parse error is that exception.

#### Scenario: No exception in the chain

- **WHEN** the caller parses a catalog that has no `metadata`
- **THEN** the cause and the context of the parse error are `None`

#### Scenario: The memory that a parse error holds

- **WHEN** the caller parses the NIST SP 800-53 rev5 catalog with its `metadata` removed, and keeps the parse error
- **THEN** the parse error holds less memory than one tenth of the size of the input text
