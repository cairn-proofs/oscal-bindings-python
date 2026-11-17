# Spec Delta

## MODIFIED Requirements

### Requirement: The class of an error is its category

For each category in this list, an error SHALL be in the category exactly when it is an instance of the class:

1. Parse error: `OscalParseError`.
2. Document-type mismatch: `OscalDocumentTypeMismatchError`, a subclass of `OscalParseError`.
3. Unknown element type: `OscalUnknownElementTypeError`, which is not a subclass of `OscalParseError`.
4. Access error: `OscalAccessError`.
5. Not-found: `FileNotFoundError`.
6. Read error: `OscalReadError`, a subclass of `OSError`, which is not a subclass of `OscalParseError` or of
   `FileNotFoundError`.
7. Builder error: `OscalBuilderError`, a subclass of `ValueError`, which is not a subclass of `OscalParseError`.

A caller tests a category with `isinstance`.

#### Scenario: A document-type mismatch is also a parse error

- **WHEN** the caller parses a profile with the catalog parser
- **THEN** the error is an instance of `OscalDocumentTypeMismatchError` and an instance of `OscalParseError`

#### Scenario: A parse error of another kind is not a document-type mismatch

- **WHEN** the caller parses input that is not valid JSON
- **THEN** the error is an instance of `OscalParseError` and not an instance of `OscalDocumentTypeMismatchError`

#### Scenario: An unknown element type is not a parse error

- **WHEN** the caller validates an element with an element type that the binding does not recognize
- **THEN** the error is an instance of `OscalUnknownElementTypeError` and not an instance of `OscalParseError`

#### Scenario: A read error is not a parse error or a not-found error

- **WHEN** the caller parses a file at a path that is a directory
- **THEN** the error is an instance of `OscalReadError` and an instance of `OSError`
- **AND** the error is not an instance of `OscalParseError` and not an instance of `FileNotFoundError`

#### Scenario: A builder error is a value error and not a parse error

- **WHEN** the caller builds a hash with the algorithm ` SHA-256`, which has a leading space
- **THEN** the error is an instance of `OscalBuilderError` and an instance of `ValueError`
- **AND** the error is not an instance of `OscalParseError`
