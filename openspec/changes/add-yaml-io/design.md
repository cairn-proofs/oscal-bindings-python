# Design

## Context

See [proposal.md](proposal.md#why) for motivation and
[issue #7](https://github.com/cairn-proofs/oscal-bindings-python/issues/7). This design covers how to implement the
three YAML operations and the resource limit, and how to move the pin.

The contract fixes the observable behavior of YAML input. The governing capability is `yaml-documents`
(YML-001 to YML-011) in the store `oscal-bindings-specs`, pinned at `0.5.0+oscal.1.2.3`. The binding-owned behavior is
the resource limit, specified in [specs/yaml-resource-limit/spec.md](specs/yaml-resource-limit/spec.md).

Three contract rules shape every loader decision below:

1. YML-002: the input is one YAML 1.2 document in UTF-8.
2. YML-003: two keys of the same text in one mapping are a parse error.
3. YML-004: the schema decides the type of each scalar at its location, so a scalar keeps its text until the schema
   coerces it. A number or boolean form at a string location stays a string.
4. YML-009: `<<` is an ordinary key, and an alias adds no meaning beyond the value of its anchored node.

The existing JSON parser is `parse_oscal` in `v1/parser.py`. It validates with Pydantic, which coerces each JSON
value to the schema type and rejects an unknown field. The YAML operations reuse it.

## Goals / Non-Goals

**Goals:**

1. Implement `parse_oscal_yaml`, `parse_oscal_yaml_file`, and `serialize_oscal_yaml` so they conform to YML-005,
   YML-006, and YML-008, and so the 23 YAML corpus cases pass.
2. Convert a YAML document to the JSON value that the existing JSON parser accepts. The YAML parse result then equals
   the JSON parse result for the JSON text of the input (YML-005).
3. Impose and document a limit on collection-alias expansion, per the spec.
4. Keep the base install at one runtime dependency. YAML is an optional extra.

**Non-Goals:**

1. Typed YAML parsers (out of scope, [issue #31](https://github.com/cairn-proofs/oscal-bindings-python/issues/31)).
2. A YAML-specific validity check. `validate_oscal` already satisfies ERR-002.
3. Any change to `models.py`, codegen, or the JSON parser's behavior.

## Decisions

### Decision 1: Convert YAML to a JSON value, then reuse the JSON parser

The YAML operation builds a plain JSON value, serializes it to JSON text, and passes the text to `parse_oscal`. YML-005
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

The base JSON type is string, number, integer, or boolean. The converter then emits:

1. At a string location: a quoted JSON string that holds the scalar's text. A float-shaped `1.0` stays `"1.0"`, and
   `yes` stays `"yes"` (YML-004.01, YML-004.03). The plain scalar `null`, the plain scalar `~`, and an empty scalar
   keep their text, so they become `"null"`, `"~"`, and `""`, never a JSON `null` (YML-004.04).
2. At a number or integer location: a bare JSON number token when the text matches the JSON number grammar of
   RFC 8259. A quoted `"443"` becomes the token `443` (YML-004.06). Text that is not a JSON number, such as `+443`,
   `007`, or `0x1BB`, is a located grammar error (YML-004.07, YML-004.10, YML-010).
3. At a boolean location: the token `true` or `false` when the text is exactly `true` or `false`. Any other text, such
   as `yes`, is a located grammar error (YML-004.08).

The schema type, not the loader, decides the JSON type, and the JSON number grammar is the gate. A bare
"every scalar becomes a JSON string" rule does not meet the contract. Pydantic's lax coercion would accept `yes` at a
boolean location and `+443` at a number location, which YML-004.08 and YML-004.10 make parse errors. So the converter
emits a typed JSON token at a number or boolean location rather than deferring the type decision to lax coercion.

A located grammar error surfaces as the binding's parse error with one structured entry at the scalar's location
(YML-010, PRS-006). Because the converter emits the failing scalar at its true location, the entry names that location.

**Alternatives considered.** (1) Emit every leaf as a JSON string and let Pydantic's lax mode coerce each value to the
schema type. This is simpler, but lax coercion is not the JSON number grammar. It accepts `yes` as a boolean and `+443`
and `007` as numbers, so it fails YML-004.08 and YML-004.10 and the matching corpus cases. Rejected. (2) Construct
Pydantic models straight from the YAML object graph, with no JSON text step. This skips one serialize-and-reparse, but
it forks the validation path. The YAML path and the JSON path would report errors through different code, and YML-005
ties the two results together. Rejected.

### Decision 2: PyYAML with a custom string-preserving composer, not the default loader and not ruamel

The loader is PyYAML, driven through its node layer (`compose`), not through `safe_load`, and with a custom composer
and constructor. PyYAML's default behavior breaks the contract in three ways, so the binding does not use it as shipped:

1. PyYAML follows YAML 1.1. Its implicit resolver turns `yes` into a boolean and `1.0` into a float. The binding
   bypasses the resolver and keeps every scalar as its text (YML-004).
2. PyYAML silently overwrites a duplicate mapping key. The binding detects a repeated key at the node layer and reports
   a parse error (YML-003).
3. PyYAML treats `<<` as a merge key. The binding treats `<<` as an ordinary key, so a merge key reaches Pydantic as an
   unknown field and is rejected (YML-009).

The binding composes the node graph and walks it once per structural position, building the JSON value. A shared node
reached through an alias is visited once per position, so the walk sees each alias resolution. The walk is the single
place that enforces four rules:

1. The schema-driven scalar typing of Decision 1.
2. The duplicate-key check.
3. The `<<` rule.
4. The alias-expansion limit of Decision 3.

An alias is a shared node reference in the composed graph, not an expanded copy, and `compose` does not raise on a
cycle. So the walk carries the set of nodes on its current ancestor path. A node that re-enters its own ancestor path
is an alias inside its own anchored node, which is a parse error (YML-009.02). The walk keys a mapping on the `<<` key
node's scalar value, not on its merge tag, so `<<` reaches Pydantic as an ordinary unknown field (YML-009.04).

The walk ignores a node's tag. A tag does not change a value (YML-009 item 2). So `!!int 7` at a string location keeps
the text `"7"` (YML-004.05), and a sequence tagged `!!omap` reads as an array (YML-009.03). The walk reads a scalar
node's text, not its resolved tag. It builds an array from any sequence node and an object from any mapping node,
whatever the tag.

**Alternatives considered.** (1) `ruamel.yaml` follows YAML 1.2 and raises on a duplicate key, so it meets two of the
three rules out of the box. The two libraries weigh almost the same at the level that matters here. PyYAML 6.0.3
declares no runtime dependency, and `ruamel.yaml` 0.19.1 declares none either. Its `ruamel.yaml.clib` and
`ruamel.yaml.clibz` dependencies sit behind optional extras, so a plain install of either is one pure-Python package
with no transitive closure. So "lighter" is not the reason. Three narrower reasons favor PyYAML. First, PyYAML is
already in the environment and is classed Production/Stable. `ruamel.yaml` 0.19.1 is a 0.x Beta whose newest line
replaced its prebuilt C wheel with one that compiles from source at install time through ziglang. Second, `ruamel.yaml`
still needs the string-preserving and alias-counting hooks, so it saves one custom rule, not the walk. Third, its
round-trip types add surface the binding does not need, while PyYAML's node API is the exact surface the walk uses. If the three custom rules prove fragile, Risk 2 records the move to `ruamel.yaml`. (2) The
default `safe_load` with a post-parse pass to re-type scalars and find duplicate keys. The duplicate keys are already
lost once `safe_load` returns, so this cannot meet YML-003. Rejected.

### Decision 3: Count collection-alias resolutions against a fixed limit of 100

A collection-alias resolution is one traversal edge that the walk follows into a shared mapping node or sequence node.
The limit counts these edges. The count accumulates across the whole document, because a billion-laughs expansion grows
multiplicatively, so a per-branch count would not catch it. A scalar alias does not count, because an edge into a shared
scalar node cannot expand exponentially. The binding reports a parse error once the cumulative count passes the limit.
An honest OSCAL document with a small, fixed number of collection aliases stays far under the limit and is not rejected,
as the spec requires.

The limit is a fixed constant of 100, not configurable. The contract names no number, and the corpus has no
resource-limit case, so the number is a free choice. The bound is only "small enough to stop a billion-laughs
expansion, large enough not to reject an honest document." Comparable parsers cluster in this range. SnakeYAML and
Symfony use 128, Apple pkl uses 50, and js-yaml uses 100. A value of 100 sits in the middle and matches a widely used
default.

The limit is not configurable in this change. A configurable limit is a public option that needs its own binding-local
requirement and its own traceability entry. OSCAL documents do not use collection aliases in normal authoring, so the
need is unproven. A later change can add an option if a real document needs one.

**Alternatives considered.** (1) A limit that scales with input size, as Hugo does (100 for small files, more for
large). This is more forgiving for large honest documents. But the scaling rule is itself a design surface to specify
and test, and OSCAL documents rarely use collection aliases at all. Rejected as unneeded complexity. (2) No limit, with
documentation that none applies. YML-011 permits this. But it leaves the billion-laughs exposure open, and the proposal
already decided to impose a limit. Rejected.

### Decision 4: Serialize through the JSON value, then dump to YAML

`serialize_oscal_yaml` reuses the JSON serialization path. It dumps the model to the JSON value with the existing
rules (OSCAL property keys, no null), then writes that value as YAML. YML-008 states that SER-003 does not apply to
YAML. So the serializer takes no pretty or compact option, and the binding chooses the style, quoting, indentation, and
key order. SER-001, SER-002, SER-004, and SER-005 still apply, and routing through the JSON value inherits them.

The serializer forces block style. The YAML emitter quotes a scalar whose text would read back as a number or a
boolean. So a round-trip keeps a string-shaped value a string (YML-008.02). A string `"1.0"` is written quoted, so the
next parse reads it as the string `"1.0"`, not a float. The `yaml-round-trip` corpus cases check this, so the quoting
is verified rather than assumed.

**Alternatives considered.** Serialize the Pydantic model straight to YAML with a YAML representer per model type. This
duplicates the no-null and key rules that the JSON path already enforces, and risks a YAML path that disagrees with the
JSON path. Rejected for the same reason as Decision 1.

### Decision 5: The optional extra and the import guard

The extra `oscal-bindings[yaml]` adds the YAML library. `v1/extensions/yaml_io.py` imports the library at module import
time. An import without the extra installed raises `ImportError` with a message that names the extra to install. The
base install keeps `pydantic[email]` as its one runtime dependency.

### Decision 6: One UTF-8 document, decoded by the binding

The input is one YAML 1.2 document in UTF-8 (YML-002). The binding decodes bytes as UTF-8 itself and maps a decode
failure to the binding's parse error, the same as the JSON path (PRS-001.03). It does not pass raw bytes to the YAML
library. The library decodes bytes on its own and honors a UTF-16 byte-order mark. Passing raw bytes would accept a
UTF-16 input that YML-002.04 requires the binding to reject.

The binding composes the stream and requires exactly one document. A stream with no document and a stream with more
than one document are both parse errors (YML-002.02, YML-002.03). A syntax error during the compose is a parse error
(YML-002.01).

### Decision 7: The file parser keeps the JSON path's not-found behavior

`parse_oscal_yaml_file` reads the file and parses its content as `parse_oscal_yaml` does. A missing file reports the
not-found condition, the same behavior that `parse_oscal_file` has today. That condition names the path and is distinct
from the parse error (YML-006, PRS-002, ERR-001.03). The file parser does not collapse not-found into the parse error.

## Risks / Trade-offs

1. A custom composer depends on PyYAML's node API (`compose`, `ScalarNode`, `MappingNode`, `SequenceNode`, the
   composer's anchor map). → The node API is stable and public, and the corpus cases exercise the behavior that depends
   on it. A PyYAML upgrade that changed the node API would fail the corpus, not pass silently. The dependency is pinned
   in the lockfiles.
2. The binding hand-rolls two rules that `ruamel.yaml` gives for free (YAML 1.2 typing and duplicate-key rejection). →
   The rules are small, and each maps to a corpus case. The choice rests on PyYAML's stability and node API, not on
   dependency weight, since both libraries install as one pure-Python package (Decision 2). If the rules prove fragile,
   Decision 2 can move to `ruamel.yaml` without changing the public API or the specs.
3. A fixed limit of 100 could reject an honest document that uses many collection aliases. → OSCAL authoring does not
   use collection aliases this way, the number matches common parsers, and a later change can add an option. The limit
   is documented, so a caller that hits it can see why.
4. The pin moves two minor versions (0.3.0 to 0.5.0), which also brings the `binding-surface` obligation from 0.4.0. →
   The traceability record is part of this change (proposal item 7). CI checks `models.py` for drift, so a model change
   from the new release cannot land silently.

## Migration Plan

1. Move the pin in `scripts/spec_artifact.py` to `0.5.0+oscal.1.2.3` with its sha256. Run generation. Check for no
   `models.py` drift.
2. Add the `yaml` extra and the dev and test dependencies. Re-lock and commit the lockfiles.
3. Add `v1/extensions/yaml_io.py` and re-export per the standard extension pattern.
4. Add the traceability record for the whole public surface, and validate it against the store schema.
5. Wire the `yaml-round-trip` and `yaml-parse` operations into the conformance runner.
6. Run the full gate. The 23 YAML corpus cases and the whole matrix pass.

Rollback: revert the pin and the new module. The base install and the JSON path are unchanged, so a revert affects only
the YAML surface and the pin.

## Open Questions

None. The three decisions that are easy to get wrong are all resolved here:

1. The type of a scalar at a number or boolean location. Decision 1 resolves it. The schema type at the location drives
   a bare JSON number or boolean token, gated by the JSON grammar, not by Pydantic's lax coercion.
2. How the converter learns the type at a location, given that OSCAL writes no `type` keyword at a scalar site.
   Decision 1 resolves it. The converter follows each `$ref`, folds an `allOf` to one base JSON type, and treats a
   string open-enum `anyOf` as a string location.
3. The limit number. Decision 3 fixes it at 100.
