# yaml-resource-limit Specification

## Purpose
Defines the resource limits that the binding applies to YAML input. A small untrusted YAML document cannot then exhaust
memory or the call stack through alias expansion or deep nesting. These limits are the YAML behavior the binding itself
decides, under the resource-limit requirement of the store's `yaml-documents` capability.

## Requirements

### Requirement: A documented budget caps alias expansion

The binding SHALL apply a documented budget to the content that aliases add to a YAML input. Each use of an alias SHALL
charge the budget with the size of the value that the alias expands to at its location. A YAML input whose aliases
charge more than a limit of the budget SHALL be a parse error.

#### Scenario: Alias expansion past the budget is a parse error

- **WHEN** the caller parses a YAML input whose aliases expand to a size past a documented limit of the budget
- **THEN** the binding reports a parse error

### Requirement: The budget limits nodes and characters separately

The budget SHALL set one limit on the number of nodes that aliases add and one limit on the number of characters that
aliases add. Each scalar, each sequence, each mapping, and each mapping key is one node. The characters are the
characters of the scalar text and the key text.

#### Scenario: Alias expansion past the node limit is a parse error

- **WHEN** the caller parses a YAML input whose aliases expand to more nodes than the documented node limit
- **THEN** the binding reports a parse error

#### Scenario: Alias expansion past the character limit is a parse error

- **WHEN** the caller parses a small YAML input that anchors one long scalar and repeats it through scalar aliases past
  the documented character limit
- **THEN** the binding reports a parse error, not a success

### Requirement: Content that no alias repeats does not charge the budget

Content that a YAML input writes out, and that no alias repeats, SHALL NOT charge the alias budget.

#### Scenario: A large document without aliases does not charge the budget

- **WHEN** the caller parses a conformant OSCAL YAML document that holds more nodes and characters than either limit,
  and that holds no alias
- **THEN** the binding returns the typed document value

### Requirement: Expansion of any alias kind charges the budget

The binding SHALL charge the budget for an alias to a scalar, an alias to a mapping, and an alias to a sequence. No
alias kind is exempt. An alias inside a value that another alias repeats SHALL charge the budget each time the outer
alias repeats it.

#### Scenario: Scalar aliases charge the budget

- **WHEN** the caller parses a YAML input whose only aliases are scalar aliases that expand past a documented limit
- **THEN** the binding reports a parse error

#### Scenario: Nested collection aliases charge the budget

- **WHEN** the caller parses a small YAML input whose collection aliases repeat other collection aliases, so that the
  expanded value grows past a documented limit
- **THEN** the binding reports a parse error

### Requirement: Bounded alias expansion parses

The binding SHALL NOT reject a YAML input for the budget when the aliases of the input expand to a size within both
limits.

#### Scenario: An ordinary document with aliases parses

- **WHEN** the caller parses a conformant OSCAL YAML document whose aliases expand to a size well within both limits
- **THEN** the binding returns the typed document value

#### Scenario: An alias to a collection of about one hundred entries parses

- **WHEN** the caller parses a conformant OSCAL YAML document that anchors a list of about one hundred properties and
  repeats it through a few aliases
- **THEN** the binding returns the typed document value

### Requirement: A documented limit caps nesting depth

The binding SHALL apply a documented limit to the nesting depth of a YAML input. The depth of a node is the number of
sequences and mappings that hold it. The limit SHALL apply to the value after alias expansion. A YAML input that nests
past the limit SHALL be a parse error, not an uncaught failure.

#### Scenario: Input past the depth limit is a parse error

- **WHEN** the caller parses a YAML input nested deeper than the documented depth limit
- **THEN** the binding reports a parse error that names the depth limit

#### Scenario: Aliases that nest past the depth limit are a parse error

- **WHEN** the caller parses a YAML input whose written depth is within the limit, and whose aliases expand to a value
  nested deeper than the limit
- **THEN** the binding reports a parse error that names the depth limit

#### Scenario: Input at the depth limit is not rejected for depth

- **WHEN** the caller parses a YAML input nested to exactly the documented depth limit
- **THEN** the binding does not reject the input for a resource limit

### Requirement: The binding publishes its limits

The binding SHALL state in its own documentation the two limits of the alias budget and the depth limit, and SHALL name
each limit value. A reader learns the limits without reading the source.

#### Scenario: The limits are documented

- **WHEN** a reader consults the binding's documentation
- **THEN** the documentation names the node limit, the character limit, and the depth limit, and the value of each

### Requirement: An undocumented limit does not reject input

The binding SHALL NOT reject a YAML input for a resource limit that it does not document. A documented limit SHALL be
the check that rejects an input that exceeds it. A stack limit of the runtime SHALL NOT reject an input first.

#### Scenario: Input below every documented limit is not rejected for a limit

- **WHEN** the caller parses a YAML input whose resource use is below every limit the binding documents
- **THEN** the binding does not reject the input for a resource limit

#### Scenario: Deep input is rejected by the documented limit

- **WHEN** the caller parses a YAML input nested far deeper than the documented depth limit
- **THEN** the parse error names the documented depth limit, not a stack limit of the runtime

### Requirement: A resource-limit rejection surfaces as the parse error

A YAML input that the binding rejects for a documented resource limit SHALL surface as the binding's parse error. The
caller SHALL NOT need a separate error type to handle a resource-limit rejection.

#### Scenario: Resource-limit rejection uses the parse error

- **WHEN** the binding rejects a YAML input for a documented resource limit
- **THEN** the caller receives the binding's parse error
