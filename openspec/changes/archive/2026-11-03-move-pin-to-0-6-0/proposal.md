# Proposal

## Why

Spec artifact `0.6.0+oscal.1.2.3` lets a binding limit the resources that a parse uses, and sets rules for each limit
([specs #24](https://github.com/cairn-proofs/oscal-bindings-specs/issues/24)). The new requirement PRS-010 replaces
YML-011 and applies to every parse operation, JSON and YAML. A binding documents each limit with what it measures and
the operations that it applies to. An input over a documented limit is a parse error that identifies the limit. A
binding does not reject an input for a limit that it does not document.
[Issue #35](https://github.com/cairn-proofs/oscal-bindings-python/issues/35) asks to move the pin to this release.

The issue assumes that only the YAML limits need work. A probe of the JSON path on the locked pydantic 2.14.2
(pydantic-core 2.50.2) found two limits that the binding applies and does not document. pydantic-core's JSON parser
rejects these inputs:

1. A value that more than 200 arrays and objects hold. The parser reports `recursion limit exceeded`. A valid catalog
   with groups nested 100 levels deep is rejected.
2. A number whose integer part has more than 4,300 digits. The parser reports `number out of range`. `PortRange.start`
   is a non-negative integer with no maximum in the schema, so a valid document can hold such a number.

Under the 0.5.1 contract, no requirement prevented these limits on JSON input. Under 0.6.0, each one breaks PRS-010.
No corpus case covers them, so the conformance run cannot find them.

## What Changes

1. Move the spec artifact pin in `scripts/spec_artifact.py` from `0.5.1+oscal.1.2.3` to `0.6.0+oscal.1.2.3`
   (sha256 `612d1463e385ff948cfea8871b9dbc1e670a9ee0fcc3d0334744b535a12537fe`). The OSCAL release stays 1.2.3, so
   `models.py` does not change. The CI drift check verifies this.
2. Document the two JSON parser limits as binding limits. The limits stay at the values of pydantic-core, because the
   binding cannot change them. The documentation states each value, what it measures, and the operations that it
   applies to.
3. Make a parse error over a JSON limit identify the limit. Today the error is a generic `json_invalid` entry, and its
   `input` key holds the whole document text. The new error carries one entry whose `type` names the limit, and no
   entry quotes the whole input. On the YAML path, the error gives the location in the YAML source. This changes the
   error entry for these two inputs only. Other parse errors do not change.
4. State, for each of the four documented YAML limits, the operations that it applies to. The YAML limits are the alias
   node limit, the alias character limit, the depth limit, and the line-break placeholder limit. Their values, their
   measures, and their parse errors do not change.
5. Replace each citation of the retired YML-011 with PRS-010 in source, tests, and docs. Correct the Purpose of the
   local spec `yaml-resource-limit`, which names the retired requirement without its identifier.
6. The binding keeps no cap on the structured entries of a parse error. PRS-011 makes a cap optional. The new corpus
   case `parse/many-failures` (PRS-012.01) expects 100 entries or more. The JSON step gives one entry for each schema
   failure, and the case passes on the JSON and YAML paths. The YAML reader stops at the first scalar grammar failure
   of YML-010, which is a separate gap that this change does not fix
   ([issue #36](https://github.com/cairn-proofs/oscal-bindings-python/issues/36)).

These items are out of scope:

1. A limit on input size, or a cap on error entries. The memory that a small invalid document uses does not change.
2. Any change to the YAML limit values.
3. A release of the package. A later version bump ships this change.

## Capabilities

### New Capabilities

1. `json-resource-limit`: the binding's documented limits on the JSON text that a parse operation reads. The JSON
   parse operations read that text directly. The YAML parse operations read the JSON text that they build from the
   YAML value. The limits come from pydantic-core, and the binding documents them and reports them as its own. The
   capability sits beside `yaml-resource-limit`, which holds the limits of the YAML reader. The requirements document a
   posture, not a public operation, so they get no traceability-record entry.

### Modified Capabilities

None. No requirement of `yaml-resource-limit` changes. Its Purpose names the retired YML-011, and the implementation
corrects that text directly in `openspec/specs/yaml-resource-limit/spec.md`, because a delta changes requirements only.

## Impact

1. Source: `v1/parser.py` gets the two limit values as module constants and maps the two pydantic-core errors to an
   error that names the limit. The JSON parse operations share `parse_oscal`, so the mapping reaches each of them. The
   YAML reader in `v1/extensions/_yaml_loader.py` checks the digit limit at each number location, so that its error
   gives the YAML location. `validate_oscal` returns `False` for these inputs, as it does today.
   No change to `models.py`, codegen, or the public API names.
2. Pin: `scripts/spec_artifact.py` and the pin assertions in `tests/test_spec_artifact_script.py`.
3. Tests: new tests for each JSON limit at and past its value, on each operation that it applies to. A test ties the
   documented values to the constants.
4. Docs: README, DEVELOPING.md, AGENTS.md, and the module docstrings of `yaml_io.py` and `_yaml_loader.py`.
5. Traceability: no change. `openspec/traceability.json` cites no retired identifier.
6. Dependencies: no change. The runtime range stays `pydantic[email]>=2.14.2,<3`. A later pydantic-core can move
   either JSON limit. The design states how the binding finds such a move.
