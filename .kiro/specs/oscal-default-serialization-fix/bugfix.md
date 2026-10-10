# Bugfix Requirements Document

## Introduction

GitHub issue #5: "Serialize to valid OSCAL JSON by default (aliases, no nulls)."

The generated OSCAL models serialize to invalid OSCAL unless the caller passes `by_alias=True, exclude_none=True` on every call. Default `model_dump()` / `model_dump_json()` emit Python field names (`incorporates_components`) instead of OSCAL names (`incorporates-components`), and emit unset optional fields as `null`, which the OSCAL JSON Schema forbids for every property. Only `serialize_oscal()` produces valid output, and only for whole documents.

Framework serializers that never see caller kwargs inherit the defect: `pydantic_core.to_json(obj)` (MCP Python SDK text content), `TypeAdapter(...).dump_python(..., by_alias=True)` (MCP structured content; aliases applied, nulls kept), and argument-less `model.model_dump_json()` (Strands Agents tool results). Downstream consumers (dfkunstler/mcp-server-for-oscal#26) must remember both kwargs at every call site, and a miss is silently wrong.

Byte-exact datetime round-trips (e.g. `.000000-04:00` → `-04:00`, `-00:00` → `Z`) are out of scope; those outputs are equivalent, valid OSCAL.

### Decision: name-keyed input (resolved)

Accepting Python field names on construction (populate-by-name) is the natural companion to alias-by-default serialization, and it lets the `make_resource` / `make_rlink` workarounds simplify. Applied naively, though, it would also make the JSON/dict validation entry points accept name-keyed input (`{"incorporates_components": ...}`) that they reject today, which conflicts with "validation unchanged."

Resolved: OSCAL input stays alias-only. Python keyword construction accepts field names (2.9). Name-keyed OSCAL input keeps today's behavior exactly (3.3, 3.4). Dict input (`model_validate` on any generated model, `validate_element`) is rejected with `extra_forbidden` at every nesting level. JSON input (`parse_oscal`, `parse_oscal_file`, `validate_oscal`, the typed `parse_*` functions, `model_validate_json`) never populates a field from a name-keyed key. Accepting name-keyed input everywhere was considered and rejected.

Known pre-existing defect, out of scope for #5: on pydantic 2.13.x the JSON path doesn't reject a name-keyed key. It silently drops it, so `parse_oscal` accepts the document with that optional field unset, or reports only `missing` at the alias for a required field. Dict input with the same key is rejected. Pydantic 2.11.0 rejects the same JSON with `extra_forbidden` (observed in the task 3.6 floor check; 2.12.x untested), so the drop is an upstream regression after 2.11.0. This fix preserves the installed pydantic's behavior unchanged. Follow-up: [#6](https://github.com/cairn-proofs/oscal-bindings-python/issues/6).

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN any generated model (document or element) is serialized with `model_dump()`, `model_dump(mode="json")`, or `model_dump_json()` and no keyword arguments THEN the system emits Python field names (e.g. `incorporates_components`, `media_type`) instead of OSCAL names (`incorporates-components`, `media-type`)

1.2 WHEN any generated model with unset optional fields is serialized with `model_dump()`, `model_dump(mode="json")`, or `model_dump_json()` and no keyword arguments THEN the system emits those fields as `null`, producing output that fails OSCAL JSON Schema validation

1.3 WHEN a generated model, or a plain dict/list containing one, is serialized with `pydantic_core.to_json(...)` THEN the system emits Python field names and `null` values

1.4 WHEN a plain dict/list containing a generated model is serialized with `TypeAdapter(...).dump_python(..., mode="json")` with or without `by_alias=True` THEN the system emits `null` values for unset optional fields (and Python field names when `by_alias` is not passed)

1.5 WHEN a document is parsed and re-serialized with `doc.model_dump_json()` THEN the system produces JSON that differs from `serialize_oscal(doc)` and fails validation against the vendored OSCAL JSON Schema

1.6 WHEN a caller constructs a model in Python by keyword using a field name whose OSCAL alias differs (e.g. `Resource(document_ids=...)`, `Rlink(media_type=...)`) THEN the system rejects the keyword, forcing helpers such as `make_rlink` / `make_resource` to build from alias-keyed dicts or assign fields after construction

1.7 WHEN `make_resource` is called with `document_ids` THEN the system assigns them to the constructed `Resource` after construction without validation (`validate_assignment` is off), so `make_resource(document_ids=[])` returns a model that serializes to invalid OSCAL (`"document-ids": []` violates `minItems: 1`), and items that are not `DocumentId` are stored unchecked, contradicting the module docstring's "raises `pydantic.ValidationError` on invalid input"

### Expected Behavior (Correct)

2.1 WHEN any generated model is serialized with `model_dump()`, `model_dump(mode="json")`, or `model_dump_json()` and no keyword arguments THEN the system SHALL emit OSCAL (alias) key names at every nesting level

2.2 WHEN any generated model with unset (None-valued) optional fields is serialized with `model_dump()`, `model_dump(mode="json")`, or `model_dump_json()` and no keyword arguments THEN the system SHALL omit those fields, so no `null` appears anywhere in the output

2.3 WHEN a generated model, or a plain dict/list containing one, is serialized with `pydantic_core.to_json(...)` THEN the system SHALL emit OSCAL key names and no `null` values for model fields

2.4 WHEN a plain dict/list containing a generated model is serialized with `TypeAdapter(dict[str, Any]).dump_python(..., mode="json")` THEN the system SHALL emit OSCAL key names and no `null` values for model fields

2.5 WHEN any document in the pinned NIST and AWS corpora is parsed and serialized with `doc.model_dump_json()` THEN the system SHALL produce JSON where `json.loads(doc.model_dump_json()) == json.loads(serialize_oscal(doc))` and which validates against the vendored OSCAL JSON Schema

2.6 WHEN an element model is constructed with only its required fields (e.g. `Capability` with only `uuid`, `name`, `description`) and serialized via any path in 2.1–2.4 THEN the system SHALL produce output with OSCAL key names only and no `null` values

2.7 WHEN arbitrary valid instances of generated models are serialized via the default paths THEN the system SHALL never emit `null`, and every emitted key SHALL be the OSCAL name from the schema (no `_` where the schema uses `-`) (property-tested)

2.8 WHEN a caller explicitly passes `by_alias=False` THEN the system SHALL emit Python field names; WHEN a caller explicitly passes `exclude_none=False` THEN the system SHALL either emit None-valued fields as `null` or the documented behavior SHALL state precisely which opt-out is supported and how

2.9 WHEN a caller constructs a model in Python by keyword using either the Python field name or the OSCAL alias THEN the system SHALL accept it and produce an equivalent model (this applies to the constructor's own keyword arguments; plain dicts nested inside them are OSCAL data and stay alias-only per 3.3)

2.10 WHEN the package is installed THEN the system SHALL declare a pydantic floor at the minimum version that supports the required configuration (pydantic>=2.11), replacing `pydantic[email]>=2.0`

2.11 WHEN users read the README THEN the system SHALL document the default serialization behavior (aliases on, None dropped), the opt-outs from 2.8, the name-keyed input policy (keyword construction accepts field names; OSCAL input stays alias-only per 3.3, including the known JSON-mode silent drop), and the pydantic floor change

2.12 WHEN the fix is complete THEN the system SHALL report parse and serialize time for the NIST SP 800-53 rev5 catalog before and after the change, and document any serialize-time regression

2.13 WHEN `make_resource` is called with `document_ids` THEN the system SHALL validate them as part of `Resource` construction, consistent with `rlinks`, and SHALL raise `pydantic.ValidationError` on invalid input (e.g. `document_ids=[]`, or items that are not `DocumentId`)

### Unchanged Behavior (Regression Prevention)

3.1 WHEN `serialize_oscal(doc)` or `serialize_oscal(doc, indent=...)` is called THEN the system SHALL CONTINUE TO produce the same JSON as before the fix for every corpus document

3.2 WHEN OSCAL JSON (text or bytes) is passed to `parse_oscal`, `parse_oscal_file`, `validate_oscal`, or any typed `parse_*` function THEN the system SHALL CONTINUE TO accept exactly the inputs it accepts today and reject exactly the inputs it rejects today, with the same `OscalParseError` contract and the same parsed values. This covers alias-keyed input and, per 3.3, input that uses Python field names

3.3 WHEN OSCAL input uses a Python field name instead of the OSCAL name of an alias-differing field (e.g. `incorporates_components`, `back_matter`), at the top level or in any nested object, THEN the system SHALL CONTINUE TO behave as it does today:
  - (a) Dict input: `model_validate` on any generated model (including `OscalDocument` and the `*Document` wrappers) SHALL CONTINUE TO reject it with an `extra_forbidden` error at that key, at every nesting depth
  - (b) JSON input: `parse_oscal`, `parse_oscal_file`, `validate_oscal`, the typed `parse_*` functions, and `model_validate_json` SHALL CONTINUE TO never populate the field from the name-keyed value (the value is never kept). On pydantic 2.13.x the key is dropped. The input is accepted with the field unset if the field is optional, and rejected as `missing` at the alias if it's required. Rejection with `extra_forbidden` at the key also satisfies this clause
  - Known pre-existing defect: (b)'s silent drop means `parse_oscal` can lose data from mis-keyed input without an error. It is out of scope for #5, and this fix SHALL NOT change it. Pydantic 2.11.0 rejects the key with `extra_forbidden` instead (task 3.6 floor check), which also satisfies (b). Tracked in [#6](https://github.com/cairn-proofs/oscal-bindings-python/issues/6)

3.4 WHEN dict input with Python field names (at any nesting level) is passed to `validate_element` THEN the system SHALL CONTINUE TO report it as invalid, with an "Extra inputs are not permitted" error at the name-keyed path (3.3(a))

3.5 WHEN input contains unknown keys THEN the system SHALL CONTINUE TO reject it (extra fields forbidden)

3.6 WHEN the existing corpus, mutation, round-trip, and property test suites run THEN they SHALL CONTINUE TO pass without changes to their assertions about validation outcomes

3.7 WHEN `get_supported_element_types()` is called THEN the system SHALL CONTINUE TO return the same set of element type names (no new entries such as a base-class name)

3.8 WHEN `make_hash`, `make_rlink`, or `make_resource` is called with valid arguments THEN the system SHALL CONTINUE TO return models equal to those returned before the fix, with the same signatures, and SHALL CONTINUE TO honor the documented contract of raising `pydantic.ValidationError` on invalid input (2.13 extends that contract to `make_resource`'s `document_ids`, which it previously bypassed)

3.9 WHEN `OscalDoc` facade accessors (`metadata`, `uuid`, `oscal_version`, `body`, `assessment_period()`) are used THEN the system SHALL CONTINUE TO return the same values and raise the same errors

3.10 WHEN code imports public names from `oscal_bindings` or `oscal_bindings.v1` THEN the system SHALL CONTINUE TO expose the same post-processed model names (`OscalDocument`, `CatalogDocument`, …) as the same objects through both paths

3.11 WHEN models are accessed by Python attribute name (e.g. `doc.catalog.metadata.oscal_version`) THEN the system SHALL CONTINUE TO resolve the same attributes and values

3.12 WHEN `hatch run release` runs (generate, lint, typing, security, tests on Python 3.11 and 3.12, docs) THEN it SHALL CONTINUE TO pass, and `models.py` SHALL remain fully reproducible from `hatch run generate` with no hand edits
