# json-resource-limit Specification

## Purpose
Defines the documented limits that the binding applies to the JSON text that a parse operation reads. These limits are
the JSON behavior the binding itself decides, under the resource-limit rule PRS-010 of the store's `document-parsing`
capability.

## Requirements

### Requirement: A documented limit caps JSON nesting depth

The binding SHALL apply a documented JSON depth limit, as a limit of the store's PRS-010, to the JSON text that a
parse operation reads. The depth of a value is the number of arrays and objects that hold it. A value deeper than the
limit SHALL exceed the limit.

#### Scenario: A conformant document past the JSON depth limit is rejected

- **WHEN** the caller parses a conformant catalog whose groups nest so that a value is one level deeper than the
  documented JSON depth limit
- **THEN** the binding reports a parse error that names the JSON depth limit

#### Scenario: A conformant document at the JSON depth limit parses

- **WHEN** the caller parses a conformant catalog whose deepest value is at exactly the documented JSON depth limit
- **THEN** the binding returns the typed document value

#### Scenario: Arrays and objects count the same

- **WHEN** the caller parses a JSON input with nested arrays and a JSON input with nested objects, each one level
  past the limit
- **THEN** the binding reports a parse error that names the JSON depth limit for each input

### Requirement: The JSON depth limit applies to each JSON operation

The JSON depth limit SHALL apply to these operations:

1. The JSON parse operation, the JSON file parse operation, and each typed parser.
2. The facade constructors that parse JSON text or a JSON file.
3. The validity check.

#### Scenario: The JSON file parse operation applies the JSON depth limit

- **WHEN** the caller parses a JSON file that holds a value deeper than the documented JSON depth limit
- **THEN** the binding reports a parse error that names the JSON depth limit

#### Scenario: The validity check returns false past the JSON depth limit

- **WHEN** the caller runs the validity check on a conformant catalog that holds a value deeper than the documented
  JSON depth limit
- **THEN** the check returns false and does not surface an error

#### Scenario: The validity check returns true at the JSON depth limit

- **WHEN** the caller runs the validity check on a conformant catalog whose deepest value is at exactly the documented
  JSON depth limit
- **THEN** the check returns true

### Requirement: The YAML depth limit rejects deep YAML input first

The documented YAML depth limit SHALL be smaller than the documented JSON depth limit. A YAML parse operation SHALL
reject a deep input for the YAML depth limit. The JSON depth limit SHALL NOT reject a YAML input.

#### Scenario: Deep YAML input names the YAML depth limit

- **WHEN** the caller parses a YAML input whose value is deeper than the documented JSON depth limit
- **THEN** the parse error names the YAML depth limit, not the JSON depth limit

### Requirement: A documented limit caps the digits of a JSON number

The binding SHALL apply a documented digit limit to each number in the JSON text that a parse operation reads. It is
a limit of the store's PRS-010. The limit counts the digits of the integer part. A sign, a fraction, and an exponent
SHALL NOT count. A number with more digits than the limit SHALL exceed the limit.

#### Scenario: A conformant document past the digit limit is rejected

- **WHEN** the caller parses a conformant JSON component definition whose port-range start is a number with one digit
  more than the documented digit limit
- **THEN** the binding reports a parse error that names the digit limit

#### Scenario: A number at the digit limit parses

- **WHEN** the caller parses a conformant JSON component definition whose port-range start has exactly as many digits
  as the documented digit limit
- **THEN** the binding returns the typed document value

#### Scenario: A sign, a fraction, and an exponent do not count

- **WHEN** the caller parses three JSON inputs whose numbers have a minus sign, a long fraction, or a long exponent,
  and each integer part has as many digits as the limit
- **THEN** the binding does not reject any of the inputs for the digit limit

### Requirement: The digit limit applies to each JSON and YAML operation

The digit limit SHALL apply to these operations:

1. Each operation that the JSON depth limit applies to.
2. The YAML parse operation and the YAML file parse operation, at each location where the schema names a number or an
   integer type.

At a YAML location where the schema names no number or integer type, a scalar of digits SHALL stay text.

#### Scenario: The validity check returns false past the digit limit

- **WHEN** the caller runs the validity check on a conformant JSON document whose port-range start has one digit more
  than the documented digit limit
- **THEN** the check returns false and does not surface an error

#### Scenario: The validity check returns true at the digit limit

- **WHEN** the caller runs the validity check on a conformant JSON document whose port-range start has exactly as many
  digits as the documented digit limit
- **THEN** the check returns true

#### Scenario: A YAML number past the digit limit is rejected at its YAML location

- **WHEN** the caller parses a YAML input whose port-range start is a plain scalar with one digit more than the
  documented digit limit
- **THEN** the binding reports a parse error that names the digit limit and gives the line and column of the scalar in
  the YAML source

#### Scenario: Digits at a YAML string location are text

- **WHEN** the caller parses a conformant YAML document whose title is a plain scalar of more digits than the
  documented digit limit
- **THEN** the binding returns the typed document value

### Requirement: A JSON limit rejection identifies the limit

A parse error over a JSON limit SHALL carry one structured entry. The type of the entry SHALL name the limit. The JSON
depth limit and the digit limit SHALL have different types. No entry SHALL quote the input.

#### Scenario: The entry of a JSON limit rejection names the limit

- **WHEN** the binding rejects an input for the JSON depth limit, and then rejects a second input for the digit limit
- **THEN** each parse error carries one structured entry, and the two entries have different types that name their
  limits

#### Scenario: The entry does not quote the input

- **WHEN** the binding rejects a JSON input of more than 1,000 characters for a JSON limit
- **THEN** no structured entry of the parse error holds the input text

#### Scenario: A schema-invalid document over a limit gets one limit entry

- **WHEN** the caller parses a document that fails schema validation at several locations and that also holds a number
  past the digit limit
- **THEN** the parse error carries one structured entry, and its type names the digit limit

### Requirement: The binding publishes its JSON limits

The binding SHALL document each JSON limit as the store's PRS-010 and ERR-002 require, and SHALL name the value of each
limit. A reader learns the limits without reading the source.

#### Scenario: The JSON limits are documented

- **WHEN** a reader consults the binding's documentation
- **THEN** the documentation names the JSON depth limit and the digit limit, with the value, the measure, and the
  operations of each. The operations include the validity check
