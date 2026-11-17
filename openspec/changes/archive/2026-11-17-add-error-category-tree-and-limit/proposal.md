# Proposal

## Why

The store requirements ERR-009 and ERR-010 (cairn-proofs/oscal-bindings-specs#42, PR cairn-proofs/oscal-bindings-specs#54)
make the error categories a tree and add a limit property to an error. A caller must be able to test whether an error is
in a category, and whether an error carries the limit property ([#60]). The binding does not meet either requirement:

1. The binding has no test for the document-type-mismatch category. The typed parsers raise a plain `OscalParseError`,
   and only the message text `Document is not ...` tells the mismatch from other parse errors.
2. The binding has no test for the limit property. A parse error over a documented limit has one entry whose `type`
   names the limit. But the entry types of limits and the entry types of other failures are one set, so a caller must
   know which types are limits. Also, the alias-node limit and the alias-character limit give the same entry type,
   `yaml_alias_budget`. Thus the entry type does not identify each of the six documented limits.
3. `validate_element` raises `OscalParseError` for an element type that the binding does not recognize. ERR-008 puts
   this error in the unknown-element-type category, not in the parse-error category. With a category tree, a test for
   the parse-error category must be false for this error (ERR-009).

The pin is at `v0.8.0+oscal.1.2.3` (#70), the release that has ERR-009 and ERR-010. Thus the fix is now possible.

## What Changes

1. A new exception `OscalDocumentTypeMismatchError`, a subclass of `OscalParseError`. Each typed parser raises it for a
   document of another type. The message stays the same.
2. `OscalParseError` gets the attribute `limit`. Its value is a string that identifies the documented limit that stopped
   the parse. Each of the six documented limits has a different value. For each other parse error, the value is `None`.
   The entry types do not change.
3. **BREAKING**: a new exception `OscalUnknownElementTypeError`, a subclass of `Exception` and not of `OscalParseError`.
   `validate_element` raises it for an element type that the binding does not recognize. Code that catches
   `OscalParseError` for this case does not catch the new error.
4. The README table of resource limits shows the `limit` value of each limit.
5. The conformance runner finds the category of an error from its class only. It does not read the message text.

## Capabilities

### New Capabilities

1. `error-tests`: how a caller tests the category of an error and the limit property of an error.

### Modified Capabilities

None.

## Impact

1. Code: `src/oscal_bindings/v1/parser.py`, `src/oscal_bindings/v1/extensions/_yaml_loader.py`,
   `src/oscal_bindings/v1/extensions/validate_element.py`, and the re-exports in
   `src/oscal_bindings/v1/extensions/__init__.py`, `src/oscal_bindings/v1/__init__.py`, and the legacy alias module
   `src/oscal_bindings/parser.py`.
2. Tests: `tests/test_conformance.py`, `tests/test_validate_element.py`, `tests/test_prop_validate_element.py`, and the
   tests of the parser and the YAML limits.
3. Docs: `README.md`, `AGENTS.md`, and `.agents/summary/interfaces.md`, `workflows.md`, `components.md`, and
   `review_notes.md`.
4. Public API: two new exception classes, the attribute `OscalParseError.limit`, and the exception that `validate_element`
   raises for an unknown element type.

[#60]: https://github.com/cairn-proofs/oscal-bindings-python/issues/60
