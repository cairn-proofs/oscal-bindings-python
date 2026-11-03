# Design

## Context

See [proposal.md](proposal.md#why) for motivation and
[issue #7](https://github.com/cairn-proofs/oscal-bindings-python/issues/7). This design covers how to implement the
three YAML operations and the resource limits, and how to move the pin.

The contract fixes the observable behavior of YAML input. The governing capability is `yaml-documents`
(YML-001 to YML-011) in the store `oscal-bindings-specs`, pinned at `0.5.1+oscal.1.2.3`. The binding-owned behavior is
the resource limits, specified in [specs/yaml-resource-limit/spec.md](specs/yaml-resource-limit/spec.md).

Five contract rules shape every loader decision below:

1. YML-002: the input is one YAML 1.2 document in UTF-8.
2. YML-003: two keys of the same text in one mapping are a parse error. The text of a scalar is its content after
   YAML 1.2 processes quotes, escapes, line folding, and chomping.
3. YML-004: the schema decides the type of each scalar at its location, so a scalar keeps its text until the schema
   coerces it. A number or boolean form at a string location stays a string.
4. YML-009: `<<` is an ordinary key, and an alias adds no meaning beyond the value of its anchored node.
5. YML-011: the binding documents each resource limit, and no undocumented limit rejects an input.

The existing JSON parser is `parse_oscal` in `v1/parser.py`. It validates with Pydantic, which coerces each JSON
value to the schema type and rejects an unknown field. The YAML operations reuse it.

This design is the third revision of the resource limits. Two earlier implementations failed review. The first counted
collection-alias resolutions and exempted scalar aliases. The second counted all emitted nodes against a budget of
5,000,000 and set a depth limit of 500. Review measured a 3.5 KB alias bomb at 334 MB before rejection under the second
rule. Review also showed that PyYAML's recursive composer overflows the stack at about 495 levels, so the depth limit
of 500 never fired. The measurements in Decision 3 replace the estimates that both earlier revisions used.

## Goals / Non-Goals

**Goals:**

1. Implement `parse_oscal_yaml`, `parse_oscal_yaml_file`, and `serialize_oscal_yaml` so they conform to YML-005,
   YML-006, and YML-008, and so the 23 YAML corpus cases pass.
2. Convert a YAML document to the JSON value that the existing JSON parser accepts. The YAML parse result then equals
   the JSON parse result for the JSON text of the input (YML-005).
3. Impose and document an alias-expansion budget and a nesting-depth limit, per the spec. Each documented limit is the
   check that rejects an input past it.
4. Keep the base install at one runtime dependency. YAML is an optional extra.

**Non-Goals:**

1. Typed YAML parsers (out of scope, [issue #31](https://github.com/cairn-proofs/oscal-bindings-python/issues/31)).
2. A YAML-specific validity check. `validate_oscal` already satisfies ERR-002.
3. Any change to `models.py`, codegen, or the JSON parser's behavior.
4. A limit on the size of input that no alias repeats. The memory that such input uses is linear in the input size, and
   the caller controls the input size. The JSON path applies no such limit either. The factor is larger than the JSON
   path's factor, because the YAML path holds a node tree and the JSON text at the same time. The README states the
   measured factor, and a test keeps it from growing unnoticed.

## Decisions

### Decision 1: Convert YAML to JSON text, then reuse the JSON parser

The YAML operation writes the JSON text of the input and passes the text to `parse_oscal`. YML-005
defines the YAML parse result as the result the JSON parse operation gives for the JSON text of the input. So this
pipeline matches the contract by construction. Pydantic then validates the JSON and rejects an unknown field (PRS-004).
So the YAML path inherits the JSON path's validation and error detail.

The converter decides each scalar's JSON type by the schema type at the scalar's location, not by the YAML loader's own
typing. YML-005 states the rule: each number is "written as the text of its scalar." So a number at a number location
becomes a bare JSON number token, and a scalar at a string location becomes a quoted JSON string.

OSCAL does not write a `type` keyword at a scalar location. Each location is a `$ref` to a datatype definition. The
definition itself is often an `allOf` or an `anyOf` with no top-level `type`. Three contract locations show the shapes.
A port `start` is a `$ref` to `NonNegativeIntegerDatatype`, an `allOf` over `IntegerDatatype`. A `last-modified` is a
double `$ref` to `DateTimeWithTimezoneDatatype`, whose `type` is `string`. A hash `algorithm` is an `anyOf` over a
string datatype and a string enum. So the converter resolves the base JSON type of a location by:

1. Following each `$ref` to the datatype definition.
2. Folding an `allOf` to the single base JSON type its members agree on. `NonNegativeIntegerDatatype` folds to a
   number location.
3. Treating an `anyOf` of a string datatype and a string enum, the shape of every OSCAL open enum, as a string
   location.

The resolver has two order-dependent tie-breaks. A key that two object branches of a union declare resolves to the
first branch. A location with more than one base type folds by priority. Against the pinned schema neither tie-break
decides a result. A test scans the schema and fails when a pin move makes either tie-break decide a result.

The base JSON type is string, number, integer, or boolean. The converter then emits:

1. At a string location: a quoted JSON string that holds the scalar's text. A float-shaped `1.0` stays `"1.0"`, and
   `yes` stays `"yes"` (YML-004.01, YML-004.03). The plain scalar `null`, the plain scalar `~`, and an empty scalar
   keep their text, so they become `"null"`, `"~"`, and `""`, never a JSON `null` (YML-004.04).
2. At a number or integer location: a bare JSON number token when the text matches the JSON number grammar of
   RFC 8259. A quoted `"443"` becomes the token `443` (YML-004.06). Text that is not a JSON number, such as `+443`,
   `007`, or `0x1BB`, is a located grammar error (YML-004.07, YML-004.10, YML-010). The converter writes the token
   into the JSON text as the scalar's text, and never converts it to a Python number. So a token that the JSON parser
   rejects, such as an integer past CPython's digit limit, gives the parse error that the JSON path gives.
3. At a boolean location: the token `true` or `false` when the text is exactly `true` or `false`. Any other text, such
   as `yes`, is a located grammar error (YML-004.08).

The schema type, not the loader, decides the JSON type, and the JSON number grammar is the gate. A bare
"every scalar becomes a JSON string" rule does not meet the contract. Pydantic's lax coercion would accept `yes` at a
boolean location and `+443` at a number location, which YML-004.08 and YML-004.10 make parse errors. So the converter
emits a typed JSON token at a number or boolean location rather than deferring the type decision to lax coercion.

**Error entries.** A failure that the YAML layer finds surfaces as `OscalParseError` with one entry in `errors`. The
entry has the keys that a Pydantic entry has, so one loop handles both kinds:

1. `type`: a string that starts with `yaml_`, for example `yaml_number_grammar` or `yaml_alias_budget`.
2. `loc`: a tuple of the JSON path to the failing node, keys as strings and sequence indexes as integers. This is the
   location that YML-010.01 and PRS-006 ask for.
3. `msg`: the message.
4. `input`: the scalar text for a scalar failure, else `None`.

The entry also has `line` and `column`, both 1-based, from the YAML source mark. A Pydantic entry does not have these
two keys. A failure that Pydantic finds keeps the Pydantic entry unchanged.

The message quotes at most 40 characters of input text, followed by an ellipsis when the binding shortens it. The
`input` key holds the whole text, as a Pydantic entry does. So a large hostile scalar cannot make the message, and any
log that writes it, as large as the input.

A scalar at a location whose schema names no scalar type, such as `metadata: 5`, becomes the JSON string `"5"`, because
YML-004 makes its value its text. Pydantic then reports a type error whose `input` is the string `"5"`. The JSON path
reports the number `5` for the same document. This is the one difference between the entries of the two paths.

**Alternatives considered.** (1) Emit every leaf as a JSON string and let Pydantic's lax mode coerce each value to the
schema type. This is simpler, but lax coercion is not the JSON number grammar. It accepts `yes` as a boolean and `+443`
and `007` as numbers, so it fails YML-004.08 and YML-004.10 and the matching corpus cases. Rejected. (2) Construct
Pydantic models straight from the YAML object graph, with no JSON text step. This skips one serialize-and-reparse, but
it forks the validation path. The YAML path and the JSON path would report errors through different code, and YML-005
ties the two results together. Rejected.

### Decision 2: PyYAML's event parser with the binding's own iterative composer

The loader is PyYAML's event parser, not `safe_load` and not PyYAML's composer. PyYAML's parser is a state machine with
an explicit stack, in both the libyaml C parser and the pure-Python parser. PyYAML's composer and PyYAML's constructor
recurse once or twice per nesting level. So the binding reads the event stream and builds its own node tree with an
explicit stack. The binding then walks that tree with an explicit stack. No step of the YAML path recurses per nesting
level, so the documented depth limit of Decision 3 is the only check that rejects deep input.

The binding uses libyaml's `CSafeLoader` when the installed PyYAML provides it, and `SafeLoader` when it does not. Both
emit the same events with the same source marks. Review measured composition at 0.79 s for a 0.72 MiB catalog with the
pure-Python parser and 0.09 s with libyaml. The tests run the YAML unit tests and the YAML corpus cases with both
parsers.

PyYAML's defaults break the contract in five ways. The binding corrects each one:

1. PyYAML follows YAML 1.1. Its implicit resolver turns `yes` into a boolean and `1.0` into a float. The composer keeps
   every scalar as its text, and Decision 1 types it (YML-004).
2. PyYAML silently overwrites a duplicate mapping key. The walk detects a repeated key and reports a parse error
   (YML-003).
3. PyYAML treats `<<` as a merge key. The walk keys a mapping on the `<<` text, so a merge key reaches Pydantic as an
   unknown field and is rejected (YML-009).
4. PyYAML's composer rejects a second anchor with the name of an earlier anchor. YAML 1.2 allows it, and an alias then
   refers to the most recent node with that anchor. The binding's composer follows YAML 1.2.
5. PyYAML's scanner reads U+0085, U+2028, and U+2029 as line breaks, as YAML 1.1 defines. YAML 1.2 defines only LF and
   CR as line breaks, so these three characters are content. A raw U+0085 in a quoted scalar folds to a space, and in
   a plain scalar it causes a syntax error. The scanner does this below the event layer. So before the binding parses
   the text, it replaces each raw occurrence of the three characters with a placeholder character. The composer then
   restores the original character in each scalar's text. The placeholders are three private-use characters
   (U+E000 to U+F8FF) that the input does not hold. PyYAML reads a private-use character as printable content. A
   placeholder must also be a character that no escape in the input can produce. So the binding excludes each code
   point that a `\x`, `\u`, or `\U` escape sequence in the text names. An input that leaves fewer than three free
   placeholders is a parse error. This needs an input that holds or names more than 6,000 distinct private-use
   characters and also holds one of the three characters. The binding skips the replacement when the input holds none
   of the three characters.

The binding creates the event parser inside its error handling. Both parsers can reject the text when the binding
creates them: the pure-Python parser rejects a NUL character, and libyaml rejects a lone surrogate when it encodes the
text. Each such failure is a parse error.

A `%YAML` directive names the YAML version of the document. YAML 1.2.2 section 6.8.1 requires a 1.2 processor to
accept a `%YAML 1.1` document and to read it as 1.2. So the binding accepts `%YAML 1.1` and `%YAML 1.2`, and reads
both as YAML 1.2. The two parsers disagree on other versions: libyaml rejects `%YAML 1.3`, and the pure-Python parser
accepts it. So the binding rejects every other version as a parse error, and the result does not depend on the
installed parser.

PyYAML's two parsers also disagree on a surrogate-pair escape such as `"\ud83d\ude00"`. libyaml rejects it, and the
pure-Python parser joins it to one character. YAML 1.2 defines an escape as a Unicode scalar value, which a surrogate is
not, so the binding rejects the escape with both parsers. The JSON path accepts the same pair. This is a documented
divergence from YML-005, beside the datetime defect of issue #19. The escape `"\U0001F600"` gives the same character
on both paths.

The composer maps each anchor to its node. An alias to an anchor that is not defined is a parse error. An alias to a
node that is still open on the composer's stack is an alias inside its own anchored node, which is a parse error
(YML-009.02). The composer finds this at the alias event, so the walk never meets a cycle.

The walk ignores a node's tag. A tag does not change a value (YML-009 item 2). So `!!int 7` at a string location keeps
the text `"7"` (YML-004.05), and a sequence tagged `!!omap` reads as an array (YML-009.03).

The walk is the single place that enforces four rules:

1. The schema-driven scalar typing of Decision 1.
2. The duplicate-key check and the non-scalar-key check.
3. The `<<` rule.
4. The alias budget and the depth limit of Decision 3.

**Alternatives considered.** (1) `ruamel.yaml` follows YAML 1.2 and raises on a duplicate key, so it meets two of the
five rules out of the box. PyYAML 6.0.3 declares no runtime dependency, and `ruamel.yaml` 0.19.1 declares none either.
So "lighter" is not the reason. Three narrower reasons favor PyYAML. First, PyYAML is classed Production/Stable and
ships libyaml in its wheels. `ruamel.yaml` 0.19.1 is a 0.x Beta whose newest line replaced its prebuilt C wheel with one
that compiles from source at install time through ziglang. Second, `ruamel.yaml` still needs the string-preserving and
alias-budget hooks, so it saves one custom rule, not the walk. Third, PyYAML's event API is the exact surface the
composer uses. Risk 2 records the move to `ruamel.yaml` if the custom rules prove fragile. (2) PyYAML's composer with a
recursive walk, and a mapping of `RecursionError` to the parse error. The second implementation did this. The composer
overflows the stack at about 495 levels under the default recursion limit, and the depth at which it overflows changes
with the caller's own stack depth. So an undocumented limit rejects the input, which YML-011 forbids. Rejected.
(3) Raise the recursion limit around the composer. This trades a catchable error for a possible C-stack crash, and it
changes interpreter-wide state. Rejected. (4) Reject the three YAML 1.1 line-break characters as a documented
deviation. This is simpler, but it rejects valid YAML 1.2 input and breaks YML-003. Rejected, because the placeholder
method gives the YAML 1.2 result.

### Decision 3: Budget the content that aliases add, and cap the nesting depth

The binding enforces two documented limits during the walk.

1. **An alias budget.** Each use of an alias charges the budget with the size of the value that the alias expands to
   at its location. The size has two parts, and each part has its own limit:
   1. Nodes: each scalar, each sequence, each mapping, and each mapping key in the expanded value. The limit is
      **100,000 nodes**.
   2. Characters: the characters of the scalar text and the key text in the expanded value. The limit is
      **1,000,000 characters**.
   An alias inside a value that an outer alias repeats charges the budget each time the outer alias repeats it, because
   the walk charges every node it emits while it is inside an alias. Content that the input writes out, and that no
   alias repeats, does not charge the budget. The walk raises `OscalParseError` when either count passes its limit.
2. **A nesting-depth limit.** The depth of a node is the number of sequences and mappings that hold it. The limit
   applies to the value after alias expansion, because `json.dumps` and Pydantic receive the expanded value. The limit
   is **128 levels**. The composer checks the written depth, and the walk checks the expanded depth. Neither recurses,
   so the limit is the check that rejects deep input.

No alias kind is exempt. A scalar alias repeated many times grows the value linearly in anchor length times alias
count. The character limit bounds this. A collection alias that repeats other collection aliases grows the value
exponentially. The node limit bounds this.

**Why the budget charges only alias content.** The second implementation charged every emitted node. A total budget
must admit the largest honest document, so it cannot also stay small. The measurements below show that SP 800-53 rev5
has 322,628 nodes. A total budget that admits it with margin admits an alias bomb of the same size. Aliases are the only
YAML feature that makes the value larger than the input. So the budget charges aliases only, and the memory that a YAML
input uses stays linear in the input size plus a fixed bound.

**Measurements.** These values come from the cached corpus at the pinned artifact, measured with `hatch run python`:

1. The largest real document is SP 800-53 rev5 (10.4 MB of JSON). It has 322,628 nodes and 3,963,105 characters of
   scalar and key text. These counts use the definitions of item 1 above.
2. The deepest of the 307 real documents in the corpus nests 21 levels.
3. The JSON path rejects nesting at about 200 levels, because Pydantic's JSON parser applies its own recursion limit.

**Why these numbers.** 128 levels is six times the deepest real document and below the JSON path's limit of about 200.
So the YAML limit, not the JSON parser's limit, rejects deep YAML input. 100,000 nodes is about one third of the whole
SP 800-53 rev5 catalog, far more than honest reuse of a shared `props` or `parties` list. 1,000,000 characters is about
1 MB of repeated text. The tests measure the peak memory of an alias bomb at each limit, and the gate keeps each peak
below 100 MB above the baseline. Both limits are fixed in this release, not configurable, and both are published in
the README and DEVELOPING (YML-011). A test ties the published values to the constants.

**Alternatives considered.** (1) Count alias resolutions or alias edges, as js-yaml and SnakeYAML do. An edge count does
not bound the size an alias to a large collection expands to, and it misses a scalar-alias bomb entirely. The first
implementation did this. Rejected. (2) A budget on total emitted nodes. The second implementation did this. A node count
does not bound scalar size, and a total budget large enough for SP 800-53 rev5 admits a large bomb. Rejected.
(3) A limit on the ratio of expanded size to input size, as libxml2 applies to entity expansion. This also works, but
a ratio is harder to state and to test than two fixed limits on alias content. Rejected. (4) A configurable limit. It is
a public option that needs its own binding-local requirement and traceability entry, and the need is unproven. A later
change can add one.

### Decision 4: Serialize through the JSON value, then dump to YAML

`serialize_oscal_yaml` reuses the JSON serialization path. It dumps the model to the JSON value with the existing
rules (OSCAL property keys, no null), then writes that value as YAML. YML-008 states that SER-003 does not apply to
YAML. So the serializer takes no pretty or compact option, and the binding chooses the style, quoting, indentation, and
key order. SER-001, SER-002, SER-004, and SER-005 still apply, and routing through the JSON value inherits them.

The serializer forces block style. The YAML emitter quotes a scalar whose text would read back as a number or a
boolean. So a round-trip keeps a string-shaped value a string (YML-008.02). A string `"1.0"` is written quoted, so the
next parse reads it as the string `"1.0"`, not a float. The `yaml-round-trip` corpus cases check this, so the quoting
is verified rather than assumed.

PyYAML's emitter writes U+0085 as a raw line break inside a single-quoted scalar, and a YAML 1.1 reader folds it. So
the serializer writes a string that holds U+0085, U+2028, or U+2029 in double-quoted style, where the emitter writes the
escapes `\N`, `\L`, and `\P`. Every YAML reader reads these escapes as the original characters.

The serializer uses libyaml's emitter (`CSafeDumper`) when PyYAML has it, else the pure-Python emitter, as the parser
does. libyaml's emitter is about three times faster on a large catalog. The two emitters can fold long lines
differently, but their output reads back as the same value. The tests run the serializer with both emitters.

**Alternatives considered.** Serialize the Pydantic model straight to YAML with a YAML representer per model type. This
duplicates the no-null and key rules that the JSON path already enforces, and risks a YAML path that disagrees with the
JSON path. Rejected for the same reason as Decision 1.

### Decision 5: The optional extra, bound at call time

The extra `oscal-bindings[yaml]` adds the YAML library. The module `v1/extensions/yaml_io.py` holds the three public
functions and does not import PyYAML at module level. Each function imports the private module
`v1/extensions/_yaml_loader.py` inside its body and calls it. `_yaml_loader.py` holds the composer, the walk, and the
serializer, and imports PyYAML. `v1/extensions/__init__.py` re-exports the three functions from `yaml_io`, and
`v1/__init__.py` re-exports them from `.extensions`, as the standard extension pattern does. So the three names appear
in one list, and each import path gives the same function object.

A base install without the extra keeps every non-YAML import path working: `import oscal_bindings`,
`from oscal_bindings import *`, `import oscal_bindings.extensions`, and a star import of each. Only a call to a YAML
operation raises `ImportError` with a message that names the extra to install. The base install keeps `pydantic[email]`
as its one runtime dependency.

The three limit constants stay in `yaml_io` and are not in any `__all__`. The README and DEVELOPING state each value
in prose, and a test ties the prose to the constants. An exported constant is public API that the binding must keep
stable, and no caller needs to read the value at run time.

The three functions carry the real type signatures and the full docstrings. So a type checker resolves them through
every documented import path, and pdoc publishes their contract. The binding does not re-export the YAML names through
a module `__getattr__` or a `globals()` loop. Either one erases the static types and forces a star import to resolve
every name, which imports the YAML library on a base install.

**Alternatives considered.** (1) Resolve the YAML names lazily through a module `__getattr__`. A star import resolves
every name in `__all__`, so `from oscal_bindings import *` imports the library on a base install, and a type checker
sees the names as `Any`. Rejected. (2) Define the call-time wrappers in `v1/__init__.py` only. The second
implementation did this. It leaves `oscal_bindings.extensions.parse_oscal_yaml` undefined and puts a definition in a
module that re-exports only. Rejected.

### Decision 6: One UTF-8 document, decoded by the binding

The input is one YAML 1.2 document in UTF-8 (YML-002). The binding decodes bytes as UTF-8 itself and maps a decode
failure to the binding's parse error, the same as the JSON path (PRS-001.03). The error entry gives the line and the
character column of the first invalid byte. The binding counts LF, CR, and CRLF as line breaks, as YAML 1.2 does. It
does not pass raw bytes to the YAML library. The library decodes bytes on its own and honors a UTF-16 byte-order mark.
Passing raw bytes would accept a UTF-16 input that YML-002.04 requires the binding to reject.

The binding reads the event stream and requires exactly one document. A stream with no document and a stream with more
than one document are both parse errors (YML-002.02, YML-002.03). A syntax error from the parser is a parse error
(YML-002.01).

### Decision 7: The file parser keeps the JSON path's not-found behavior

`parse_oscal_yaml_file` reads the file and parses its content as `parse_oscal_yaml` does. A missing file reports the
not-found condition, the same behavior that `parse_oscal_file` has today. That condition names the path and is distinct
from the parse error (YML-006, PRS-002, ERR-001.03). The file parser does not collapse not-found into the parse error.

## Risks / Trade-offs

1. The binding's composer depends on PyYAML's event API (the event classes, `check_event`, `get_event`, and the source
   marks). → The event API is public and stable across PyYAML 5 and 6. The corpus cases and the unit tests run with
   both parsers. A PyYAML upgrade that changed the API would fail them, not pass silently. The dependency is pinned in
   the lockfiles.
2. The binding hand-rolls rules that `ruamel.yaml` gives for free (YAML 1.2 typing, duplicate-key rejection, and
   anchor redefinition). → The rules are small, and each maps to a corpus case or a unit test. If the rules prove
   fragile, Decision 2 can move to `ruamel.yaml` without changing the public API or the specs.
3. The placeholder method of Decision 2 depends on PyYAML reading a private-use character as content. → A unit test
   parses each of the three characters in a plain scalar, a quoted scalar, a block scalar, and a key, and compares the
   result with the JSON path. A PyYAML change would fail it.
4. The alias budget could reject an honest document with heavy aliasing. → 100,000 nodes is about one third of the
   largest real catalog. The limits are documented, so a caller that meets one can see why. A later change can add an
   option.
5. The pin moves from 0.3.0 to 0.5.1, which also brings the `binding-surface` obligation from 0.4.0. → The traceability
   record is part of this change (proposal item 7). CI checks `models.py` for drift, so a model change from the new
   release cannot land silently. The 0.5.1 patch over 0.5.0 carries only a corpus known-defect fix, so it adds no
   model drift.

## Migration Plan

1. Move the pin in `scripts/spec_artifact.py` to `0.5.1+oscal.1.2.3` with sha256
   `33a14ab00fcbc049934ad217989452896b74a1bb215bbd4f132ca3b81c8dfd8f`. Run generation. Check for no `models.py` drift.
2. Add the `yaml` extra and the dev and test dependencies. Re-lock and commit the lockfiles.
3. Add `v1/extensions/yaml_io.py` and `v1/extensions/_yaml_loader.py`, and re-export per the standard extension pattern.
4. Add the traceability record for the whole public surface, and validate it against the store schema.
5. Wire the `yaml-round-trip` and `yaml-parse` operations into the conformance runner.
6. Run the full gate. The 23 YAML corpus cases and the whole matrix pass.

Rollback: revert the pin and the new modules. The base install and the JSON path are unchanged, so a revert affects
only the YAML surface and the pin.

## Open Questions

None. The four decisions that are easy to get wrong are all resolved here:

1. The type of a scalar at a number or boolean location. Decision 1 resolves it. The schema type at the location drives
   a bare JSON number or boolean token, gated by the JSON grammar, not by Pydantic's lax coercion.
2. How the converter learns the type at a location, given that OSCAL writes no `type` keyword at a scalar site.
   Decision 1 resolves it. The converter follows each `$ref`, folds an `allOf` to one base JSON type, and treats a
   string open-enum `anyOf` as a string location.
3. The resource limits and their values. Decision 3 resolves them: an alias budget of 100,000 nodes and 1,000,000
   characters, and a depth limit of 128 levels.
4. How deep input avoids an undocumented stack limit. Decision 2 resolves it. No step of the YAML path recurses per
   nesting level.
