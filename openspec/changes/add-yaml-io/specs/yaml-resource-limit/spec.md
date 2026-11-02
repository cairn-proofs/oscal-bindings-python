# Spec Delta

## Purpose

Defines the resource limits that the binding applies to YAML input. A small untrusted YAML document cannot then exhaust
memory or the call stack through alias expansion or deep nesting. These limits are the YAML behavior the binding itself
decides, under the resource-limit requirement of the store's `yaml-documents` capability.

## ADDED Requirements

### Requirement: A documented budget caps total expansion

The binding SHALL apply a documented budget on the total expansion of a YAML input. The budget counts the materialized
size of the value the input expands to, so an alias of any kind contributes its expanded size. A YAML input whose
expansion exceeds the budget SHALL be a parse error.

#### Scenario: Expansion over the budget is a parse error

- **WHEN** the caller parses a YAML input whose aliases expand to a value larger than the documented budget
- **THEN** the binding reports a parse error

#### Scenario: A scalar-alias bomb is rejected

- **WHEN** the caller parses a small YAML input whose scalar aliases expand to a value far larger than the budget
- **THEN** the binding reports a parse error, not a success

### Requirement: Expansion of any alias kind counts toward the budget

The binding SHALL count the expanded size that an alias to a scalar, a mapping, or a sequence contributes. No alias
kind is exempt, because a scalar alias expands the materialized value as much as a collection alias.

#### Scenario: Scalar aliases count

- **WHEN** the caller parses a YAML input whose only aliases are scalar aliases that expand past the budget
- **THEN** the binding reports a parse error

#### Scenario: Collection aliases count

- **WHEN** the caller parses a YAML input whose collection aliases expand past the budget
- **THEN** the binding reports a parse error

### Requirement: Bounded expansion parses

The binding SHALL NOT reject a YAML input for the expansion budget when the input expands to a value within the budget.
The budget constrains only input that expands to an unsafe size, not ordinary use of aliases.

#### Scenario: An ordinary document with aliases parses

- **WHEN** the caller parses a conformant OSCAL YAML document whose aliases expand to a value well within the budget
- **THEN** the binding returns the typed document value

### Requirement: A documented limit caps nesting depth

The binding SHALL apply a documented limit on the nesting depth of a YAML input. A YAML input nested past the limit
SHALL be a parse error, not an uncaught failure.

#### Scenario: Input past the depth limit is a parse error

- **WHEN** the caller parses a YAML input nested deeper than the documented depth limit
- **THEN** the binding reports a parse error

### Requirement: The binding publishes its limits

The binding SHALL state in its own documentation the expansion budget and the depth limit it applies, and SHALL name
each limit value. A reader learns the limits without reading the source.

#### Scenario: The limits are documented

- **WHEN** a reader consults the binding's documentation
- **THEN** the documentation names the expansion budget and the depth limit and their values

### Requirement: An undocumented limit does not reject input

The binding SHALL NOT reject a YAML input for a resource limit that it does not document.

#### Scenario: Input below every documented limit is not rejected for a limit

- **WHEN** the caller parses a YAML input whose resource use is below every limit the binding documents
- **THEN** the binding does not reject the input for a resource limit

### Requirement: A resource-limit rejection surfaces as the parse error

A YAML input that the binding rejects for a documented resource limit SHALL surface as the binding's parse error. The
caller SHALL NOT need a separate error type to handle a resource-limit rejection.

#### Scenario: Resource-limit rejection uses the parse error

- **WHEN** the binding rejects a YAML input for a documented resource limit
- **THEN** the caller receives the binding's parse error
