# document-type-selection Specification

## Purpose

Defines how the binding selects one OSCAL document type for the validation of a parse input. Also defines the error
that the binding reports when the input names no document type.

## Requirements

### Requirement: The root key selects one document type

For a JSON object input, the binding SHALL select one document type from the root keys of the object:

1. The root key of a document type is the one required top-level key of that type, for example `catalog`.
2. The selected type is the type of the first root key, in input order, that is the root key of a document type.
3. The binding SHALL validate the input only against the selected type.

#### Scenario: A valid document parses to its type

- **WHEN** the caller parses a valid OSCAL document of any of the eight document types
- **THEN** the binding returns the typed document value of that type

#### Scenario: A fault reports only errors of the selected type

- **WHEN** the caller parses a catalog document in which one control has an `id` that is not a string
- **THEN** each entry of the parse error has a location inside the catalog body
- **AND** no entry states that a key of another document type is missing

#### Scenario: The error location names the selected type

- **WHEN** the caller parses a catalog document whose body has a validation fault
- **THEN** the first segment of the location of each entry is the name of the Catalog document type

#### Scenario: Two root keys select the first one

- **WHEN** the caller parses a JSON object that has the key `catalog` and, after it, the key `profile`
- **THEN** the binding reports a parse error
- **AND** each entry of the parse error has the Catalog document type as the first segment of its location

### Requirement: An input with no root key reports one error

The binding SHALL report a parse error with exactly one entry for an input of these kinds:

1. A value that is not a JSON object.
2. A JSON object that has no root key of a document type.

The entry SHALL have:

1. The type `oscal_document_type`.
2. An empty location.
3. A message that states that the input is not an OSCAL document because it has no known root key.
4. For a JSON object with one or more keys, a message that names the keys of the object.

#### Scenario: An object with no known root key

- **WHEN** the caller parses the JSON object `{"metadata": {}}`
- **THEN** the binding reports a parse error with one entry of type `oscal_document_type` and an empty location

#### Scenario: A root key in the form of an internal field name

- **WHEN** the caller parses an assessment plan whose root key is `assessment_plan` in place of `assessment-plan`
- **THEN** the binding reports a parse error with one entry of type `oscal_document_type` and an empty location
- **AND** the message of the entry names the key `assessment_plan`

#### Scenario: A value that is not an object

- **WHEN** the caller parses the JSON array `[]`
- **THEN** the binding reports a parse error with one entry of type `oscal_document_type` and an empty location

#### Scenario: The validity check returns false

- **WHEN** the caller runs the validity check on the JSON object `{"metadata": {}}`
- **THEN** the check returns false and does not surface an error

### Requirement: A document value is accepted as the document root

The binding SHALL accept a typed document value of each of the eight document types as the root of the document union.
This applies when the caller constructs the document union from that value, and when the caller validates it.

#### Scenario: Construct the document union from a catalog document value

- **WHEN** the caller constructs the document union with a Catalog document value as its root
- **THEN** the root of the result is that Catalog document value

#### Scenario: Round trip through serialization

- **WHEN** the caller serializes a parsed document of any of the eight document types and parses the result
- **THEN** the binding returns a document value equal to the first parsed value
