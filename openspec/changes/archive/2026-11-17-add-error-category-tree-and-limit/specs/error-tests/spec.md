# Spec Delta

## Purpose

Defines how a caller tests whether an error is in a category of the store's error model. Also defines how a caller
tests whether an error carries the limit property of the store's error model.

## ADDED Requirements

### Requirement: The class of an error is its category

For each category in this list, an error SHALL be in the category exactly when it is an instance of the class:

1. Parse error: `OscalParseError`.
2. Document-type mismatch: `OscalDocumentTypeMismatchError`, a subclass of `OscalParseError`.
3. Unknown element type: `OscalUnknownElementTypeError`, which is not a subclass of `OscalParseError`.
4. Access error: `OscalAccessError`.
5. Not-found: `FileNotFoundError`.

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

### Requirement: Each documented limit has its own identifier

Each documented limit SHALL have the identifier in this list:

1. JSON depth limit: `json_depth`.
2. JSON digit limit: `json_digits`.
3. YAML alias node limit: `yaml_alias_nodes`.
4. YAML alias character limit: `yaml_alias_characters`.
5. YAML depth limit: `yaml_depth`.
6. YAML line-break placeholder limit: `yaml_line_break_placeholders`.

No two limits have the same identifier.

#### Scenario: The two alias limits are told apart

- **WHEN** the caller compares the identifier of the YAML alias node limit with the identifier of the YAML alias
  character limit
- **THEN** the identifiers are `yaml_alias_nodes` and `yaml_alias_characters`, which are different

### Requirement: A parse error over a documented limit identifies the limit

The attribute `limit` of an `OscalParseError` SHALL be the limit property of the store's error model:

1. When a documented limit stopped the parse, `limit` is the identifier of that limit.
2. For each other parse error, `limit` is `None`.

A caller tests the property of an `OscalParseError` with `error.limit is not None`. Only `OscalParseError` and its
subclasses have the attribute. For an error of any class, the test is `getattr(error, "limit", None) is not None`.

#### Scenario: A JSON input over the depth limit

- **WHEN** the caller parses a JSON input that nests deeper than the JSON depth limit
- **THEN** the `limit` of the parse error is `json_depth`

#### Scenario: A schema failure carries no limit

- **WHEN** the caller parses a catalog that has no `metadata`
- **THEN** the `limit` of the parse error is `None`

#### Scenario: A document-type mismatch carries no limit

- **WHEN** the caller parses a profile with the catalog parser
- **THEN** the `limit` of the error is `None`

#### Scenario: The two alias limits have different identifiers

- **WHEN** the caller parses a YAML input whose aliases add more nodes than the node limit
- **AND** the caller parses a second YAML input whose aliases add more characters than the character limit, but fewer
  nodes than the node limit
- **THEN** the `limit` of the first parse error is `yaml_alias_nodes`
- **AND** the `limit` of the second parse error is `yaml_alias_characters`

#### Scenario: A YAML number over the digit limit

- **WHEN** the caller parses a YAML input with a number of more digits than the digit limit
- **AND** the schema names a number type at the location of the number
- **THEN** the `limit` of the parse error is `json_digits`
