# Design

## Context

See [proposal.md - Why](proposal.md#why) for the motivation. These facts constrain the approach.

1. Each typed parser in `parser.py` raises `OscalParseError("Document is not a ...")` for a document of another type.
2. Six raise sites stop a parse at a documented limit:
   1. `parse_oscal` in `parser.py`, for the JSON depth limit and the JSON digit limit (`_limit_entry`).
   2. `_yaml_loader.py`, through `_fail`, for the YAML depth limit (two sites), the two alias limits
      (`_Writer.charge`), and the line-break placeholder limit.
   3. `_yaml_loader.py`, directly, for the JSON digit limit at a YAML number location.
3. `_fail` also raises each YAML failure that is not a limit, such as `yaml_alias_cycle` and `yaml_undefined_alias`.
4. `validate_element` raises `OscalParseError("Unknown element type: ...")`.
5. The conformance runner (`category` in `tests/test_conformance.py`) maps the two message prefixes to the categories.
6. A name in `v1.__all__` must be in the surface snapshot (`tests/support/version_package.py`) and in
   `openspec/traceability.json`.

## Goals / Non-Goals

**Goals:**

1. Each category test and the limit test is one Python expression that reads no message text.

**Non-Goals:**

1. A change to a message or to an entry of a parse error.
2. The read-error category ([#61]) and the builder-error category ([#62]).

## Decisions

### D1: A category is a class, and the tree is the class hierarchy

ERR-009 says a test for a category is true for the category and for each descendant. `isinstance` behaves the same way
on a class hierarchy. Thus each category is a class (see the spec
[The class of an error is its category](specs/error-tests/spec.md#requirement-the-class-of-an-error-is-its-category)).

1. `OscalDocumentTypeMismatchError(OscalParseError)` is in `parser.py`, below `OscalParseError`. The eight typed
   parsers raise it with the message that they raise now.
2. `OscalUnknownElementTypeError(Exception)` is in `v1/extensions/validate_element.py`. It has no parent category, as
   `OscalAccessError` has none. `validate_element` raises it with the message that it raises now.
3. Both classes go through the re-export chain: `extensions/__init__.py` for the second one, then `v1/__init__.py`.
   The top level takes them from `v1.__all__`. The legacy alias module `src/oscal_bindings/parser.py` lists each name
   explicitly, because `v1.parser` declares no `__all__`. Thus `OscalDocumentTypeMismatchError` also goes into its
   import list and its `__all__`. The legacy `extensions` alias star-imports, so it needs no edit.

Alternative: a `category` attribute with a string value. A caller then needs a table of the tree to test for a parent
category. The binding then keeps the tree in two places, the attribute values and the table. Rejected.

### D2: The name says "mismatch"

The name `OscalDocumentTypeError` is shorter. But the entry type `oscal_document_type` marks a different parse error:
an input that names no document type. That error is not a mismatch. The name `OscalDocumentTypeMismatchError` keeps the
two apart.

### D3: The limit property is an attribute, not a class

ERR-010 says a property is independent of the category. A mixin class `OscalLimitError` gives a second `isinstance`
test, which a caller can mistake for a category test. An attribute does not. Thus `OscalParseError.__init__` gets the
keyword `limit: str | None = None` and stores it on `self.limit`.

Only `OscalParseError` and its subclasses have the attribute. `OscalAccessError`, `OscalUnknownElementTypeError`, and
`FileNotFoundError` do not. The test `error.limit is not None` applies to an `OscalParseError`. For an error of any
class, the test is `getattr(error, "limit", None) is not None`. A class attribute `limit = None` on the other binding
classes was rejected: it cannot cover `FileNotFoundError`, so the `getattr` form is needed anyway.

### D4: Each raise site sets the identifier, and the entry types stay

The `limit` values are new strings, one for each documented limit (see the spec
[Each documented limit has its own identifier](specs/error-tests/spec.md#requirement-each-documented-limit-has-its-own-identifier)).

1. The binding does not compute `limit` from the entry type. The two alias limits share the entry type
   `yaml_alias_budget`, so the entry type cannot give two values.
2. The binding does not change the entry types. A caller that reads an entry type keeps working.
3. `_LIMIT_PREFIXES` in `parser.py` gets the identifier for each JSON limit. `_fail` gets the keyword `limit`, and only
   the five limit calls set it: the line-break placeholder limit, the YAML depth limit at the compose stage, the alias
   node limit, the alias character limit, and the YAML depth limit in `emit` after alias expansion. A plain deep input
   reaches only the compose-stage depth site. The `emit` depth site is reached only through aliases. The direct
   digit-limit raise in `_yaml_loader.py` sets `limit="json_digits"`.

The identifiers drop the `_limit` and `_budget` suffixes of the entry types. A value of the `limit` attribute is always
a limit, so the suffix adds nothing.

### D5: The runner reads the class only

`category` checks `OscalDocumentTypeMismatchError` before `OscalParseError`, and adds `OscalUnknownElementTypeError`.
The two message-prefix checks go away. `test_every_category_is_mapped` builds one instance of each class.

### D6: Traceability

1. `OscalParseError`: add ERR-009 and ERR-010.
2. `OscalDocumentTypeMismatchError`: ERR-005 and ERR-009.
3. `OscalUnknownElementTypeError`: ERR-008 and ERR-009.

## Risks / Trade-offs

1. [Code that catches `OscalParseError` around `validate_element` does not catch an unknown element type.] →
   The proposal marks the break. The docstring of `validate_element` and the README name the new class.

[#61]: https://github.com/cairn-proofs/oscal-bindings-python/issues/61
[#62]: https://github.com/cairn-proofs/oscal-bindings-python/issues/62
