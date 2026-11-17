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

## ADDED Requirements

### Requirement: A file-path parse finds the category of a read failure from the read

A file-path parse SHALL find the category of a read failure from the error of the read itself:

1. When no file can exist at the path (`ENOENT`, `ENOTDIR`, or a `ValueError` for a path that the operating system
   cannot represent), the error is not-found.
2. For each other read failure, the error is a read error. Its `filename` is the path, and its message names the path.

A file-path parse does not test whether the path exists before the read.

#### Scenario: A missing path is not-found

- **WHEN** the caller parses a file at a path that does not exist
- **THEN** the error is an instance of `FileNotFoundError`

#### Scenario: A path below a regular file is not-found

- **WHEN** the caller parses a file at a path whose parent is a regular file
- **THEN** the error is an instance of `FileNotFoundError` and not an instance of `OscalReadError`

#### Scenario: A path that the operating system cannot represent is not-found

- **WHEN** the caller parses a file at a path that contains a NUL byte
- **THEN** the error is an instance of `FileNotFoundError` and not an instance of `OscalReadError`

#### Scenario: A file without read permission is a read error

- **WHEN** the caller parses a file that the caller has no permission to read
- **THEN** the error is an instance of `OscalReadError`, and its message names the path

#### Scenario: A loop of symbolic links is a read error

- **WHEN** the caller parses a file at a path that is a loop of symbolic links
- **THEN** the error is an instance of `OscalReadError`, and its message names the path

#### Scenario: A directory that the caller cannot search is a read error

- **WHEN** the caller parses a file at a path through a directory that the caller has no permission to search
- **THEN** the error is an instance of `OscalReadError`, and its message names the path
