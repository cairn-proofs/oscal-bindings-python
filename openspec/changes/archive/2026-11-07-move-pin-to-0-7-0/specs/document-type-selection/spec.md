# Spec Delta

## MODIFIED Requirements

### Requirement: The root key selects one document type

The contract rule for the document type of the parse failures is
[PRS-013](https://github.com/cairn-proofs/oscal-bindings-specs/blob/v0.7.0%2Boscal.1.2.3/openspec/specs/document-parsing/spec.md#requirement-prs-013-the-root-key-selects-the-document-type-of-the-parse-failures).
For a JSON object input, the binding SHALL meet these conditions:

1. For an object with two or more root keys, the binding selects the document type of the first root key, in input
   order.
2. The first segment of the location of each entry of the parse error is the class name of the selected document type.

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

For an input that names no document type, as item 2 of
[PRS-013](https://github.com/cairn-proofs/oscal-bindings-specs/blob/v0.7.0%2Boscal.1.2.3/openspec/specs/document-parsing/spec.md#requirement-prs-013-the-root-key-selects-the-document-type-of-the-parse-failures)
defines it, the binding SHALL report a parse error with exactly one entry. The entry SHALL have:

1. The type `oscal_document_type`.
2. An empty location.
3. For a JSON object with one or more keys, a message that names the keys of the object.

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
