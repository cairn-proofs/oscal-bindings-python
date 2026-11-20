# Design

## Context

See [proposal.md](proposal.md#why) for the problem. `validate_element` gives each element to Pydantic. The recursion
guard of pydantic-core stops an element that nests too deep, or that holds itself. Pydantic then raises a
`ValidationError`, and `validate_element` turns it into an invalid result.

A probe of the current code gave these facts:

1. pydantic-core sets the guard limit by platform. It is 255 on CPython for Linux and macOS, 99 on Windows and on
   PyPy, and 49 on wasm and on PyPy for Windows. On CPython for Linux and macOS, the guard stops
   `catalog-group-with-groups` at 255 levels of groups. It stops the `catalog-group` union and the `catalog-document`
   at 254 levels. Another recursive type can stop at another count.
2. A deep element and an element that holds itself at a position of its own recursive type each give an entry of the
   type `recursion_loop`. A deep element that also has other failures gives the same entry. The text of the message
   differs between the cases, so the text is not a safe signal.
3. The failure also holds entries of other types, for example `extra_forbidden`, that the guard causes.
4. An element that holds itself through a field of another type, for example `props`, gives no `recursion_loop` entry.
   It gives an ordinary invalid result.

## Goals / Non-Goals

**Goals:**

1. Document the limit that already applies, and report it with the error that the store requires.
2. Add no cost to a call that stays within the limit.

**Non-Goals:**

1. A depth value that the binding chooses. The guard stays the only depth limit of element validation.
2. A change to the parse operations or to their limits.

## Decisions

### D1. Use the guard of pydantic-core as the limit

`validate_element` keeps the guard and does not walk the element before it validates. The alternative is a walk that
counts the levels of the element, with a value such as 200 to match the JSON limit. The walk gives an exact value.
It also adds about a fifth or more of the time of each call on a realistic catalog element. It needs a cycle guard too,
because a level-by-level walk of an element that holds itself two times grows without end. The store requires a
documented limit and its measure. It does not require an exact value. So the exact value does not justify the cost on
each call.

### D2. Detect the limit from the entry type

`validate_element` reads the entries of the `ValidationError` before it selects a branch. When any entry has the type
`recursion_loop`, it raises the new error. It does so even when the failure holds entries of other types. ELV-004.02
allows no valid or invalid result for an element over the limit. The alternative is a match on the message
text. The text changes between cases and can change with a Pydantic release, so the type is the safer signal.

### D3. The new error is `OscalLimitExceededError`

The class is a subclass of `Exception`, next to `OscalUnknownElementTypeError`, in `validate_element.py`. It takes a
message and the keyword `limit`, and it stores `limit`. It is not a subclass of `OscalParseError`, because ERR-011
requires that. The two re-export modules export it, and the top-level package takes it from `v1.__all__`.

The class does not carry `errors` entries. The error holds no copy of the element, as the parse errors for a limit
hold no copy of the input.

`validate_element` raises the error after the `except` block, as `parse_oscal` does for a limit. The `except` block
only records that an entry has the type `recursion_loop`. So neither `__cause__` nor `__context__` holds the
`ValidationError`, because its entries hold the element as `input`. A test asserts both attributes are `None`, as
`tests/test_parser.py` does for the parse error.

### D4. An element that holds itself gives the same error

The guard cannot tell an element that holds itself at a position of its own recursive type from a deep element. It
stops the first after a few steps. The binding does not add a guard to tell them apart. A cycle through a field of
another type fails as a type failure before any recursion, so it gives the ordinary invalid result. The documentation
says that a cyclic element can give this error.

### D5. The documentation is a section, not a table row

`docs/limits.md` gets the section `## Element validation` after the table. The table row format does not fit. The limit
has no entry `type`, because the error is not a parse error. It has no parse operations. The section states:

1. The operation: `validate_element`.
2. The measure: the nested validations of a recursive type.
3. The value: 255 on CPython for Linux and macOS, and lower on Windows, PyPy, and wasm (99 or 49). For groups on
   CPython for Linux and macOS, 255 is the last level that passes.
4. The reasons for the approximate value, as the spec lists them: the library, the measure, the element type, the
   platform, and the library release.
5. The error and its `limit`, `element_depth`.

The intro paragraph of the page names the parse limits and the parse error. It gets one sentence that points to the
new section. `docs/errors.md` adds the new category next to `OscalUnknownElementTypeError`.

The page test `test_documented_limit_rows_state_values_and_operations` reads only the section from `# Resource limits`
to the next heading of level 1 to 3. A new `##` section after the table does not change what it reads.

## Risks / Trade-offs

1. [A Pydantic release or the platform changes the guard depth] → The documentation says the value is approximate and
   names both reasons. The tests use depths far from every limit (20 and 1,000 levels), so they pass on each platform
   and when the value moves.
2. [A caller that tests `result.valid` for a deep element now gets an exception] → The proposal lists this under
   Impact. The previous result was a wrong result for a valid element, so no caller can rely on it.
3. [The value in the documentation differs by element type] → The section says so, and it gives the groups value as
   the example.
