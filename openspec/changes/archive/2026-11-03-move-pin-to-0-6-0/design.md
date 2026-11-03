# Design

## Context

See [proposal.md](proposal.md#why) for the motivation. The requirements are in
[specs/json-resource-limit/spec.md](specs/json-resource-limit/spec.md).

Every JSON parse operation reaches `OscalDocument.model_validate_json` through `parse_oscal` in `v1/parser.py`:

1. `parse_oscal_file` reads the file bytes and calls `parse_oscal`.
2. The eight typed parsers call `parse_oscal`.
3. `OscalDoc.from_json` and `OscalDoc.from_file` call `parse_oscal` and `parse_oscal_file`.
4. The YAML parse operations build JSON text from the YAML value and call `parse_oscal` (`_yaml_loader.py`).
5. `validate_oscal` calls `model_validate_json` directly and returns `False` on any `ValidationError`.

`parse_oscal` copies every pydantic error entry into `OscalParseError.errors`. The YAML loader raises its own errors
through `_fail` in `_yaml_loader.py`. Each of those errors carries one entry with the keys `type` (`yaml_<kind>`), `loc`,
`msg`, `input`, `line`, and `column`. The exception message is the `msg` of the entry.

These facts come from probes on the locked pydantic 2.14.2 (pydantic-core 2.50.2), Python 3.14:

1. Depth. The JSON parser accepts a value that 200 arrays and objects hold, and rejects a value that 201 hold. Arrays
   and objects count the same. A valid catalog parses with groups nested 99 levels deep. It fails at 100 levels,
   where a group title has 202 containers. The error is one `json_invalid` entry whose `ctx.error` starts with
   `recursion limit exceeded`.
2. Digits. The JSON parser rejects a number whose integer part has 4,301 digits or more. A sign, a fraction, and an
   exponent do not count: `-` followed by 4,300 digits parses, and `1e5000` parses. A fraction of 20,000 digits
   parses. The error is one `json_invalid` entry whose `ctx.error` starts with `number out of range`. The limit does
   not follow `sys.set_int_max_str_digits`: values of 640, 4300, and 0 give the same result.
3. Scope. The digit limit applies at any location, also at a key that the schema rejects. On the YAML path, a plain
   scalar at a number location goes to the JSON parser as written, so the digit limit applies. At a string location,
   the scalar becomes a JSON string, so the limit does not apply.
4. The `input` key of each `json_invalid` entry holds the whole document text.
5. Neither `pydantic.ConfigDict` nor `model_validate_json` has a setting for either limit.
6. No other limit showed: a title of 50,000,000 characters parses.

## Goals / Non-Goals

**Goals:**

1. Each limit that a parse operation applies is documented, with its value, its measure, and its operations.
2. A parse error over a JSON limit names the limit and does not copy the input.
3. CI fails when a lock update moves a JSON limit away from its documented value.

**Non-Goals:**

1. Shorter `input` values in other `json_invalid` entries. A malformed document still gets an entry that holds its whole
   text. That behavior is older than this change, and the contract does not forbid it.
2. A limit that the binding sets lower than pydantic-core's limit.

## Decisions

### D1. Document the parser's limits. Do not enforce limits of the binding's own.

The binding documents 200 levels and 4,300 digits as its limits, because pydantic-core applies them and exposes no
setting for them.

Alternatives considered:

1. Scan the text before validation and enforce a lower limit in Python. The scan must know JSON strings and escapes,
   so it is a second JSON tokenizer. It adds a full Python pass over each input, also over valid input. Rejected for
   the cost and the second parser.
2. Raise the limits. pydantic has no setting for them (Context, fact 5). Rejected because it is not possible.
3. Record the two limits as known nonconformance and change nothing. PRS-010 then fails for valid documents that the
   binding could serve with documentation alone. Rejected.

### D2. Map the two parser errors to a limit error in `parse_oscal`.

`parse_oscal` checks a `ValidationError` before it copies the entries. The mapping applies when all of these are true:

1. The error has exactly one entry.
2. The entry type is `json_invalid`.
3. `ctx.error` starts with one of the two prefixes in Context facts 1 and 2.

Then `parse_oscal` raises `OscalParseError` with one new entry:

| Limit | `type` | `msg` |
|---|---|---|
| Depth | `json_depth_limit` | `JSON nesting exceeds the depth limit of 200` |
| Digits | `json_digit_limit` | `A JSON number exceeds the limit of 4,300 digits in its integer part` |

The entry has the keys of a YAML limit entry: `type`, `loc` (`()`), `msg`, `input` (`None`), `line`, and `column`. The
line and column come from the `at line N column M` suffix of `ctx.error`, or are `None` when the suffix is missing.
The column is a UTF-8 byte offset in the line, not a character offset. The docstring of `OscalParseError` states this.
The exception message is the `msg`. The `json_` prefix keeps the types apart from the `yaml_` types of the YAML loader.
`parse_oscal` raises the new error `from None`, so that no exception in the chain holds the input text.

A limit error carries one entry and no schema-failure entries. That shape is the shape the binding already gives a
malformed JSON input, which carries one `json_invalid` entry. ERR-001 gives structured per-location detail only to a
schema-conformance parse error. A limit error is not one, because the parser stops before it reads the whole document.
So the entry-count rules of PRS-006 and PRS-012 do not apply to the limit entry. PRS-012.03 agrees: an invalid document
over a limit carries no schema-failure entries.

Each JSON parse operation goes through `parse_oscal` (Context, items 1 to 3), so the one mapping reaches all of them.
The mapping runs only after validation fails, so valid input costs nothing more. `validate_oscal` needs no change,
because it returns `False` for any `ValidationError`.

### D2a. The YAML reader checks the digit limit at each number location.

On the YAML path, the `at line N column M` suffix of `ctx.error` points into the JSON text that the YAML reader builds.
It does not point into the caller's YAML source. So the YAML reader applies the digit limit itself. The scalar
step in `_yaml_loader.py` checks each scalar at a number location against the JSON number grammar. After that check passes, the step counts the digits of the integer part. When the count is more than
`JSON_DIGIT_LIMIT`, the step raises `OscalParseError` with one entry of type `json_digit_limit`. The entry gives the
JSON path in `loc`, the YAML line and column, and `input` `None`. The message is the D2 message. The reader then never
passes such a number to the JSON parser, so the D2 mapping does not fire for YAML input.

The YAML depth limit is 128, below 200. So the JSON depth limit cannot fire for YAML input either. The spec requirement
"The YAML depth limit rejects deep YAML input first" holds this order.

Alternatives considered:

1. Keep the pydantic entry and change only the exception message. The entry type stays `json_invalid` for every
   malformed input. A program then cannot tell a limit from a syntax error, and the entry still copies the input.
   Rejected.
2. Map by the `ctx.error` text in a helper that `validate_oscal` also uses. `validate_oscal` returns only a boolean, so
   the mapping changes nothing there. Rejected as dead code.

### D3. The limit values are module constants in `v1/parser.py`.

`JSON_DEPTH_LIMIT = 200` and `JSON_DIGIT_LIMIT = 4300` go in `v1/parser.py`. They are not in `__all__`, the same as
the YAML constants in `v1/extensions/yaml_io.py`. The messages of D2 use the constants. The test in
`tests/test_lint_config.py` that ties the README and DEVELOPING values to the YAML constants gets the two JSON
constants too.

### D4. Tests pin each limit at the boundary on the installed pydantic-core.

The tests in `tests/test_parser.py` parse inputs at each limit and one step past it. They do not use a mock. A lock
update can move a limit or change the `ctx.error` text. The test matrix then fails, and the maintainer updates the
constant and the docs in the same change. The tests cover these inputs:

1. Depth on a conformant catalog: groups nested 99 levels parse, and 100 levels fail with `json_depth_limit`. This
   runs through `parse_oscal`, `parse_oscal` with `bytes`, `parse_oscal_file`, `parse_catalog`, `OscalDoc.from_json`,
   `OscalDoc.from_file`, and `validate_oscal`. `validate_oscal` returns `True` at 99 levels and `False` at 100.
2. Depth with nested arrays and with nested objects at an unknown key, at 200 and at 201. At 200 the error is
   `extra_forbidden`, and at 201 it is `json_depth_limit`.
3. Digits on a conformant component definition: a `PortRange.start` of 4,300 digits parses and 4,301 digits fails with
   `json_digit_limit`, through the same JSON operations. `validate_oscal` returns `True` at 4,300 and `False` at 4,301.
   A minus sign, a fraction of 20,000 digits, and an exponent do not count.
4. Digits on the YAML path, through `parse_oscal_yaml` and `parse_oscal_yaml_file`: 4,301 digits fail with
   `json_digit_limit` at the YAML line and column of the scalar. A YAML title of 5,000 digits parses.
5. A deep YAML input names the YAML depth limit, and an assertion checks `DEPTH_LIMIT < JSON_DEPTH_LIMIT`.
6. No entry of a limit error holds the input text, for an input of more than 1,000 characters. The exception has no
   `__cause__` and no `__context__`.
7. A component definition with several schema failures and a 4,301-digit `start` gives one `json_digit_limit` entry.
8. The corpus case `parse/many-failures` runs from `tests/test_conformance.py`, which already reads
   `expected-min-failures`.

### D5. A new capability `json-resource-limit`, beside `yaml-resource-limit`.

The JSON limits go in a new local capability, not in `yaml-resource-limit`. OpenSpec has no way to rename a capability.
A capability named for YAML that also holds JSON limits misleads the reader. The two capabilities split at a real
boundary: the YAML reader applies `yaml-resource-limit`, and the JSON parser applies `json-resource-limit`. The YAML
parse operations go through both.

### D6. The docs list each limit with its measure and operations.

The README gets one "Resource limits" section that lists the two JSON limits and the four YAML limits. Each item states
the value, what the limit measures, and the operations it applies to. The YAML section keeps its prose and points to
that list. DEVELOPING.md records D1, D2, and D2a in Key Design Decisions. The YAML limit errors already name their limits
(`yaml_alias_budget`, `yaml_depth_limit`, `yaml_line_break_placeholder`), so they do not change.

## Risks / Trade-offs

1. [A consumer installs a pydantic-core newer than the lock, and it moves a limit.] → If the new limit is lower, a
   document within the documented limit gets rejected. If it is higher, a document past the documented limit parses
   on the JSON path. Both break PRS-010 for that install until the binding releases a fix. The digit check of D2a
   keeps the YAML path at the documented digit limit in either case. The runtime range `>=2.14.2,<3` stays, because a narrow upper
   bound blocks pydantic security releases. The D4 tests fail on the first lock update that moves a limit. If
   pydantic-core changes the `ctx.error` text, the D2 mapping does not match. The input is then still a parse error,
   with the old `json_invalid` entry, and the D4 tests fail in CI.
2. [Another failure gives `number out of range`.] → The probes found only the digit limit (Context, fact 2). The D2
   mapping then names the digit limit for that other failure. The D4 tests do not find this case. Accepted, because the
   input is still a parse error.
3. [A caller matches `json_invalid` for a deep or long-number input.] → The entry type changes to `json_depth_limit` or
   `json_digit_limit` for those two inputs. The binding is at 0.x. The README and the release notes state the change.
4. [The memory use of a small invalid document stays high.] → PRS-011 makes a cap optional, and this change adds none.
   The binding conforms without one.

## Migration Plan

No data migration. The pin move and the error mapping ship in one release. To roll back, revert the change. The old
pin still resolves, and nothing else depends on the new entry types.
