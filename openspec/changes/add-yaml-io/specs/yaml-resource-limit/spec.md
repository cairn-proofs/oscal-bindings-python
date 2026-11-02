# Spec Delta

## Purpose

Defines the resource limit that the binding applies to YAML input, so a small untrusted YAML document cannot exhaust
memory through alias expansion. This limit is the one YAML behavior the binding itself decides, under the resource-limit
requirement of the store's `yaml-documents` capability.

## ADDED Requirements

### Requirement: A documented limit caps collection-alias expansion

The binding SHALL apply a limit on the expansion of collection aliases in a YAML input. A YAML input whose collection
aliases expand past the limit SHALL be a parse error.

#### Scenario: Input over the limit is a parse error

- **WHEN** the caller parses a YAML input whose collection aliases expand past the limit
- **THEN** the binding reports a parse error

### Requirement: Bounded collection aliasing does not reach the limit

The binding SHALL NOT reject a YAML input for the resource limit when its collection aliases are few enough to stay
within the limit. The limit constrains only input that would expand to an unsafe size, not ordinary use of aliases.

#### Scenario: Bounded collection aliasing is not rejected

- **WHEN** the caller parses a YAML input that holds a small, fixed number of collection aliases
- **THEN** the binding does not reject the input for the resource limit

### Requirement: The limit counts collection aliases only

The binding SHALL count the resolution of a collection alias against the limit. The binding SHALL NOT count the
resolution of a scalar alias against the limit.

#### Scenario: Scalar aliases are not counted against the limit

- **WHEN** the caller parses a YAML input that holds many scalar aliases and no collection alias
- **THEN** the binding does not reject the input for the resource limit

### Requirement: The binding publishes the limit

The binding SHALL state in its own documentation that it limits collection-alias expansion, and SHALL name the limit
value. A reader learns the limit without reading the source.

#### Scenario: The limit is documented

- **WHEN** a reader consults the binding's documentation
- **THEN** the documentation states that the binding limits collection-alias expansion and names the limit value

### Requirement: An undocumented limit does not reject input

The binding SHALL NOT reject a YAML input for a resource limit that it does not document.

#### Scenario: Input below every documented limit is not rejected for a limit

- **WHEN** the caller parses a YAML input whose resource use is below every limit the binding documents
- **THEN** the binding does not reject the input for a resource limit

### Requirement: A resource-limit rejection surfaces as the parse error

A YAML input that the binding rejects for the documented resource limit SHALL surface as the binding's parse error. The
caller SHALL NOT need a separate error type to handle a resource-limit rejection.

#### Scenario: Resource-limit rejection uses the parse error

- **WHEN** the binding rejects a YAML input for the documented collection-alias limit
- **THEN** the caller receives the binding's parse error
