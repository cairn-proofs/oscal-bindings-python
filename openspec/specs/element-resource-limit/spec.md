# element-resource-limit Specification

## Purpose
Defines the documented depth limit of element validation, the error that reports it, and the documentation that the
limit needs. These rules are the element-validation behavior the binding itself decides, under the resource-limit rule
ELV-004 of the store's `element-validation` capability.

## Requirements

### Requirement: A documented limit caps the nesting depth of an element

The binding SHALL apply a documented depth limit to the element that the element validation operation reads, as a limit
of the store's ELV-004. An element that nests deeper than the limit SHALL exceed the limit. An element within the limit
SHALL get a valid or invalid result.

#### Scenario: An element within the depth limit gets a result

- **WHEN** the caller validates a group element that holds 20 levels of nested groups against the type
  `catalog-group-with-groups`
- **THEN** the result is valid

#### Scenario: An element over the depth limit exceeds the limit

- **WHEN** the caller validates a group element that holds 1,000 levels of nested groups against the type
  `catalog-group-with-groups`
- **THEN** the operation reports the limit-exceeded error and returns no valid or invalid result

### Requirement: The element depth limit is documented with an approximate value

The documentation SHALL state the element depth limit as an approximate value. It SHALL give these items:

1. What the limit measures.
2. The element validation operation as the operation that the limit applies to.
3. The value for each platform where the value differs.

#### Scenario: The documentation names the operation, the measure, and the value

- **WHEN** a reader looks for the element depth limit in the documentation of the resource limits
- **THEN** the documentation names the element validation operation, states what the limit measures, and gives the
  approximate value for each platform where the value differs

### Requirement: The documentation gives the reasons that the value is approximate

The documentation of the element depth limit SHALL give these reasons:

1. A library sets the limit.
2. The limit counts nested validations of a recursive type, not levels of the element.
3. The count at which the limit stops an element depends on the element type.
4. The count depends on the platform.
5. A release of the library can change the count.

#### Scenario: The documentation gives each reason

- **WHEN** a reader looks for the reason that the element depth limit is approximate
- **THEN** the documentation gives the five reasons of this requirement

### Requirement: An element over the depth limit is a limit-exceeded error

The element validation operation SHALL report an element over the element depth limit with the error
`OscalLimitExceededError`. The error SHALL be in the limit-exceeded category and SHALL NOT be a parse error. Its
attribute `limit` SHALL be `element_depth`. The operation SHALL NOT return a valid or invalid result for that element.

#### Scenario: The error identifies the limit

- **WHEN** the caller validates an element that nests deeper than the element depth limit
- **THEN** the error is an `OscalLimitExceededError`, and its `limit` is `element_depth`

#### Scenario: The error is not a parse error

- **WHEN** the caller validates an element that nests deeper than the element depth limit
- **THEN** the error is not an instance of `OscalParseError`

#### Scenario: An element within the limit raises no error

- **WHEN** the caller validates an element that violates the constraints of the type and nests within the element depth
  limit
- **THEN** the result is invalid, and the operation raises no `OscalLimitExceededError`

### Requirement: An element that holds itself exceeds the depth limit

An element that holds itself at a position of its own recursive type SHALL exceed the element depth limit. A group in
the `groups` list of the same group is an example. The element validation operation SHALL report it as the requirement
above states.

#### Scenario: An element that holds itself

- **WHEN** the caller validates a group element whose `groups` list holds the group element itself
- **THEN** the operation reports the limit-exceeded error with the `limit` `element_depth`
