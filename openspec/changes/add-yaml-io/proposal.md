# Proposal

## Why

OSCAL is published in XML, JSON, and YAML. This binding reads and writes JSON only. A consumer that holds an OSCAL
document in YAML must convert it to JSON with a separate tool before this binding can parse it.
[Issue #7](https://github.com/cairn-proofs/oscal-bindings-python/issues/7) asks for YAML parse and serialize.

The work was blocked on the contract, because YAML changes the format scope of parsing and serialization and needs one
rule for YAML scalar typing. The contract now defines YAML. Spec artifact `0.5.0+oscal.1.2.3` adds the `yaml-documents`
capability (YML-001 to YML-011) and a YAML corpus, from
[specs #16](https://github.com/cairn-proofs/oscal-bindings-specs/issues/16) and
[specs #21](https://github.com/cairn-proofs/oscal-bindings-specs/issues/21). The binding can start the work now.

## What Changes

1. Move the spec artifact pin in `scripts/spec_artifact.py` from `0.3.0+oscal.1.2.3` to `0.5.1+oscal.1.2.3`
   (sha256 `33a14ab00fcbc049934ad217989452896b74a1bb215bbd4f132ca3b81c8dfd8f`). The pin is the one selector of the
   contract, so the jump to YAML is a jump of the whole pin. The `yaml-documents` capability lands in 0.5.0, and the
   0.5.1 patch adds the YAML corpus known-defect entry that this binding needs for its datetime serializer defect
   (issue #19). The OSCAL release stays 1.2.3, so no `models.py` drift is expected. CI checks the drift either way.

2. Add YAML parse and serialize to the public API, as an optional feature. These three operations are defined by the
   store's `yaml-documents` capability, so the binding implements contract behavior, not a binding-local wrapper:
   1. `parse_oscal_yaml(data: str | bytes) -> OscalDocument`, defined by YML-005.
   2. `parse_oscal_yaml_file(path: Path | str) -> OscalDocument`, defined by YML-006.
   3. `serialize_oscal_yaml(model: OscalDocument) -> str`, defined by YML-008.
   YML-001 requires all three together. A binding that offers one YAML operation offers all three, and conforms to
   every requirement of the capability. So this feature commits the binding to YML-001 through YML-011 in full. The
   three functions are the public operations. YML-002, YML-003, YML-004, YML-009, YML-010, and YML-011 are the behavior
   those operations exhibit.

3. Accept one YAML 1.2 document in UTF-8 as input (YML-002). The binding rejects a stream with no document or more than
   one. It rejects invalid UTF-8 as the JSON parsers do. Two keys of the same text in one mapping are a parse error,
   including a plain key and its quoted form (YML-003). The key `<<` is an ordinary field, so a merge key is an unknown
   field and a parse error (YML-009). The schema decides the type of each scalar at its location (YML-004). So a number
   or boolean form at a string location keeps its text. This item states the accepted input grammar. The loader and the
   YAML-to-JSON method are design decisions, not scope.

4. Map every YAML failure to `OscalParseError`, the same error the JSON parsers report. The covered failures are:
   1. Malformed YAML.
   2. A stream that is not one document.
   3. Invalid UTF-8.
   4. A duplicate mapping key.
   5. A scalar whose text does not match the type at its location.
   A schema-conformance failure carries one structured entry per location (YML-010, PRS-006). No YAML-specific validity
   check is in scope. YML-001 names only the three operations, and the existing `validate_oscal` satisfies ERR-002.

5. Apply and document resource limits on YAML input (YML-011). PyYAML's default does not cap alias expansion, which is
   a billion-laughs exposure. PyYAML's composer also recurses per nesting level, so deep input overflows the stack. So
   the binding imposes two documented limits and reports a parse error past either one:
   1. An alias budget. Each use of an alias, of any kind, charges the nodes and the characters of the value it expands
      to. Content that no alias repeats does not charge the budget.
   2. A nesting-depth limit on the value after alias expansion.
   The binding must not reject an input for an undocumented limit, so no step of the YAML path recurses per nesting
   level. The contract names no number, and the corpus has no resource-limit case, so the exact limits are a design
   choice. The design sets them from measurements of the real documents in the corpus. These limits are the one
   behavior the binding itself owns, so they need a binding-local requirement (see Capabilities).

6. Add an install extra `oscal-bindings[yaml]`. The base install keeps `pydantic[email]` as its one runtime
   dependency. Every import path works without the extra. A call to a YAML operation without the extra installed
   reports an error with an install hint.

7. Add a traceability record for the whole public API. The pin at `0.4.0+oscal.1.2.3` and later requires the
   `binding-surface` capability (SRF-001 to SRF-007). The record holds one entry for every public operation, not only
   the YAML ones (SRF-003). The binding has no such record today. The pin move requires one that enumerates every name
   in `v1/__all__`. That surface includes, and is not limited to:
   1. The JSON parsers and the eight typed parsers.
   2. `serialize_oscal` and `validate_oscal`.
   3. The `OscalDoc` facade type, whose entry covers its accessors (SRF-003.03).
   4. The element-validation functions `validate_element` and `get_supported_element_types`, each a standalone entry.
   5. The back-matter builders.
   6. The exported types and exceptions, such as `DocumentId`, `OscalBody`, `OscalWrapper`, `OscalAccessError`,
      `ElementValidationError`, and `ElementValidationResult`.
   Each entry cites the contract requirement that defines the operation. Each cited identifier resolves in
   `openspec/requirements.json` of the pinned 0.5.1 artifact (SRF-004). The three YAML operations cite YML-005,
   YML-006, and YML-008 (SRF-003.01).

8. Wire the two new corpus operations, `yaml-round-trip` and `yaml-parse`, into the conformance runner. The maintainer
   note on issue #7 records 23 cases. The design checks the exact `yaml-*` operation set against the artifact's corpus
   manifest.

Typed YAML parsers (`parse_catalog_yaml`, and one for each of the other seven document types) are out of scope. YML-007
makes them optional, and all-or-nothing: a binding offers one for each of the eight document types, or none.
[Issue #31](https://github.com/cairn-proofs/oscal-bindings-python/issues/31) tracks the set for a later change.

## Capabilities

### New Capabilities

1. `yaml-resource-limit`: the binding's documented resource limits on YAML input. It holds the binding-local
   requirements this change adds: the posture the binding takes on alias expansion and nesting depth, under YML-011.
   This is the project's first local spec. The three YAML parse and serialize operations are not here. The store's
   `yaml-documents` capability defines them, not this project. A YAML parser decides that YAML input is accepted,
   which SRF-002.02 names as not binding-local. So those operations are contract operations, and the traceability record maps them to YML-005,
   YML-006, and YML-008. The `yaml-resource-limit` requirements document a posture, not a public operation, so they earn
   no traceability-record entry. SRF-007.01 forbids an entry that holds both a contract identifier and a binding-local
   identifier, so the `parse_oscal_yaml` entry cites YML-005 only.

### Modified Capabilities

None. The store defines YAML parsing, serialization, and the traceability record. That behavior lives in the
`yaml-documents` and `binding-surface` capabilities of the store, not in a spec of this project. This project has no
local specs today, so there is no local requirement text to change. The new local requirements are in the
`yaml-resource-limit` capability above.

## Impact

1. Source: a new public module `v1/extensions/yaml_io.py`, re-exported from `v1/extensions/__init__.py` and
   `v1/__init__.py` per the standard extension pattern. It imports PyYAML only when an operation is called, through a
   new private module `v1/extensions/_yaml_loader.py`. No change to `models.py`, codegen, or `parser.py`.
2. Dependencies: a new `yaml` optional extra adds a YAML library and its type stubs to the dev and test environments.
   The lockfiles change and ship with it.
3. Pin and generation: `scripts/spec_artifact.py` moves two minor versions. Generation re-fetches the artifact. CI
   checks the committed `models.py` for drift. A model change from the new release, if any, surfaces there.
4. Conformance: the runner in `tests/test_conformance.py` gains handlers for the `yaml-round-trip` and `yaml-parse`
   operations. A traceability record file and its validation against the store schema are new.
5. Public API: three new functions. No change to the JSON functions or to any model type. The YAML serializer takes no
   pretty or compact option. YML-008 states that SER-003 does not apply to YAML. It lets the binding choose the style,
   quoting, indentation, and key order. SER-001, SER-002, SER-004, and SER-005 still apply to the YAML output.
6. Docs: README usage for YAML, a DEVELOPING.md note on the YAML scalar-typing rule (YML-004) and the documented
   resource limits (YML-011).
