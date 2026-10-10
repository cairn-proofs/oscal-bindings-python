# OSCAL Default Serialization Fix Bugfix Design

## Overview

Generated models subclass `pydantic.BaseModel` directly with only `ConfigDict(extra='forbid')`. Pydantic's serialization defaults (`by_alias` unset → field names, `exclude_none=False` → `null`s) therefore apply to every path that doesn't pass both kwargs explicitly. That covers argument-less `model_dump*()`, `pydantic_core.to_json`, and `TypeAdapter.dump_python`. The same missing configuration rejects Python field names as constructor kwargs, which is why `make_rlink` / `make_resource` carry workarounds.

The fix gives every generated object model a hand-written base class, `OscalBaseModel`, wired in through datamodel-codegen's own `--base-class` flag. The base:

1. sets `serialize_by_alias=True`, so aliases are the default on every path;
2. adds a wrap `model_serializer` that omits None-valued fields, so no path can emit `null`;
3. overrides `__init__` to map Python field-name kwargs to aliases, marked so pydantic doesn't route validation through it. Keyword construction accepts names (2.9). Validation keeps today's behavior exactly: name-keyed dict input is rejected at every nesting level, and name-keyed JSON keys are never populated (3.3, 3.4). Config-level `validate_by_name` (Option A) was re-probed and rejected (Root Cause 4).

`models.py` stays a pristine `hatch run generate` output. The post-processor needs no change. The pydantic floor moves to `>=2.11`.

The wrap `model_serializer` is the chosen None-omission mechanism. Per-field `exclude_if` is recorded only as a measured fallback (§11).

With by-name construction in place, `make_resource` passes `document_ids` to the constructor, so it is validated like `rlinks` and invalid input raises `ValidationError` (1.7, 2.13).

Design choices were checked against the locked pydantic 2.13.5 / pydantic-core 2.46.5 and datamodel-code-generator 0.83.0. Throwaway probes regenerated the models with `--base-class` into `./tmp/` and exercised a prototype base against them. The findings that shaped the design are called out inline as **Verified**. Before task 3, the by-name mechanism was re-probed against the real generated models (re-exec'd with each candidate base injected) and a minimal model, in dict and JSON mode. That run corrected Root Cause 4 and surfaced the pre-existing JSON-mode drop (Root Cause 6).

## Glossary

- **Bug_Condition (C)**: A generated model instance serialized through a *default path* (no explicit `by_alias=True, exclude_none=True`) that has at least one alias-differing field set or at least one None-valued optional field. A second clause covers Python-name keyword construction; a third covers `make_resource` called with invalid `document_ids`.
- **Property (P)**: Output carries OSCAL (alias) keys only, contains no `null` for any model field, and equals `serialize_oscal` output for whole documents.
- **Preservation**: Every behavior outside C stays the same. That covers `serialize_oscal` output, parse/validate accept/reject outcomes (including today's handling of name-keyed input: dict rejected, JSON never populated), element-type list, builders, facade, public names, and attribute access.
- **Default path**: Any of `m.model_dump()`, `m.model_dump(mode="json")`, `m.model_dump_json()`, `pydantic_core.to_json(x)`, `TypeAdapter(T).dump_python(x, mode="json")` (with or without `by_alias=True`), where `x` is a model or a plain container holding models.
- **OscalBaseModel**: New hand-written base in `src/oscal_bindings/v1/_base.py`; parent of all 183 generated object models.
- **Object model**: A generated class that would otherwise subclass `BaseModel`. Excludes the two preserved `RootModel`s, `OscalDocument` and `Mappings`.
- **Alias-differing field**: A field whose `FieldInfo.alias` is set and differs from its Python name (e.g. `media_type` / `media-type`).
- **`__pydantic_base_init__`**: Marker attribute pydantic sets on `BaseModel.__init__` and `RootModel.__init__`. When a class's `__init__` carries it, pydantic sets `__pydantic_custom_init__ = False`, and validation never calls `__init__`.
- **Dict mode / JSON mode**: pydantic validation from Python objects (`model_validate`, `validate_element`, constructor kwargs) vs. from JSON text/bytes (`model_validate_json`, and so `parse_oscal`, `parse_oscal_file`, `validate_oscal`, typed `parse_*`). In pydantic-core they're separate code paths.
- **Name-keyed key**: a key equal to the Python name of an alias-differing field of the model being validated (e.g. `media_type` inside an `Rlink`).
- **JSON-mode drop**: pre-existing pydantic-core 2.13.x behavior: in JSON mode with `by_name` off, a name-keyed key is neither used nor reported as extra. It is silently discarded (Root Cause 6). Out of scope; preserved as-is.
- **Option A / Option B**: the two by-name construction mechanisms compared in Root Cause 4/5. A is config `validate_by_name=True` plus per-call `by_alias=True, by_name=False`. B is the `__init__` override marked `__pydantic_base_init__` (chosen).
- **F / F'**: The library before / after the fix.

## Bug Details

### Bug Condition

The bug manifests whenever a generated model reaches a serializer without both `by_alias=True` and `exclude_none=True`, and it has something those kwargs would change. Framework serializers (MCP SDK, Strands) never pass them. The construction-side defect manifests whenever a caller passes a Python field name whose alias differs. The builder defect manifests whenever `make_resource` receives `document_ids` that `Resource` validation would reject, because the post-construction assignment skips validation.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type SerializationCall | ConstructionCall | MakeResourceCall
  OUTPUT: boolean

  IF input IS SerializationCall(value, path, kwargs) THEN
    models := allGeneratedObjectModelsReachableFrom(value)   // nested at any depth, incl. inside dict/list
    RETURN path IN DefaultPaths
           AND NOT (kwargs.by_alias = True AND kwargs.exclude_none = True)
           AND models ≠ ∅
           AND EXISTS m IN models :
                 (EXISTS f IN m.fields : f.alias ≠ NULL AND f.alias ≠ f.name AND f IN m.fields_set_nonNone)
                 OR (EXISTS f IN m.fields : getattr(m, f.name) IS None)
  END IF

  IF input IS ConstructionCall(cls, kwargs) THEN
    RETURN EXISTS k IN keys(kwargs) :
             k = cls.fields[name].name AND cls.fields[name].alias ∉ {NULL, k}
  END IF

  IF input IS MakeResourceCall(kwargs) THEN
    RETURN kwargs.document_ids ≠ NULL
           AND NOT validates(Resource.fields["document_ids"], kwargs.document_ids)
           // e.g. [] (minItems 1) or items that are not DocumentId-valid
  END IF
END FUNCTION
```

Note: `serialize_oscal(doc)` always passes both kwargs, so it lies outside C. It is the reference behavior (Preservation 3.1).

### Examples

- `Capability(uuid=U, name="n", description="d").model_dump_json()`. Actual: `{"uuid":…, "name":"n", "description":"d", "props":null, "links":null, "incorporates_components":null, "control_implementations":null, "remarks":null}`. Expected: `{"uuid":…, "name":"n", "description":"d"}`.
- `pydantic_core.to_json({"result": rlink})` with `media_type` set. Actual: `{"result":{"href":…,"media_type":"text/plain","hashes":null}}`. Expected: `{"result":{"href":…,"media-type":"text/plain"}}`.
- `TypeAdapter(dict[str, Any]).dump_python({"doc": catalog_doc}, mode="json", by_alias=True)`. Actual: aliases, but `null` for every unset optional at every depth. Expected: no `null`.
- `parse_oscal(nist_800_53).model_dump_json()`. Actual: fails OSCAL schema validation (snake_case keys, nulls). Expected: `json.loads(...) == json.loads(serialize_oscal(doc))`.
- `Resource(uuid=U, document_ids=[DocumentId(identifier="x")])`. Actual: `ValidationError` (`document_ids` is an extra input). Expected: an equivalent model to `Resource(uuid=U, **{"document-ids": [...]})`.
- `make_resource(document_ids=[])`. Actual: returns a `Resource` that serializes (`by_alias=True, exclude_none=True`) with `"document-ids": []`, violating `minItems: 1`. Expected: `ValidationError`.
- `make_resource(document_ids=["not-a-document-id"])`. Actual: stored unchecked. Expected: `ValidationError`.
- Edge: `doc.model_dump(by_alias=False)`. Expected: Python field names (explicit opt-out), still no `null`.
- Edge: `OscalDocument.model_validate({"catalog": {..., "back_matter": {...}}})` (name-keyed nested key, dict mode). Expected: still `ValidationError` with `extra_forbidden` at `catalog.back_matter`. Not in C; must be preserved.
- Edge: `parse_oscal('{"catalog": {..., "back_matter": {...}}}')` (same key, JSON mode). Today (2.13.5) it's accepted with `catalog.back_matter is None`: the JSON-mode drop (Root Cause 6). Renaming required `oscal-version` to `oscal_version` fails as `missing` at `oscal-version`. Not in C. The fix leaves it exactly as is; the value is never kept.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- `serialize_oscal(doc)` and `serialize_oscal(doc, indent=N | None)` produce byte-identical JSON for every corpus document (3.1).
- `parse_oscal`, `parse_oscal_file`, `validate_oscal`, typed `parse_*`: identical accept/reject sets, parsed values, and `OscalParseError` contract (3.2).
- Name-keyed input (3.3), unchanged in both modes:
  - Dict mode: `model_validate` on any generated model (`OscalDocument`, `*Document` wrappers, owning model) raises `extra_forbidden` at the name key, at every depth (3.3(a)). Option B leaves model config untouched, so this holds with or without per-call kwargs, including for user code that calls `Model.model_validate` directly.
  - JSON mode: the name-keyed value is never kept (3.3(b)). On 2.13.5 that's the JSON-mode drop: accepted with the optional field unset, or `missing` at the alias for a required field. The fix neither repairs nor widens it. If a future pydantic rejects with `extra_forbidden`, that also satisfies 3.3(b). **Verified**: Option B's JSON outcomes match the current tree case for case.
- `validate_element`: name-keyed dicts at any depth stay invalid (3.4). Unknown keys stay rejected in both modes (3.5).
- `get_supported_element_types()` returns exactly the pre-fix set, today 187 names including the pre-existing `root-model` entry, and gains no `oscal-base-model` (3.7).
- `make_hash` / `make_rlink` / `make_resource`: same signatures, equal models for valid arguments, and the documented "raises `pydantic.ValidationError` on invalid input" contract (3.8). Invalid `document_ids` now raising is the fix for 1.7/2.13, not a preservation break (Fix Implementation §7).
- `OscalDoc` accessors, public names and object identity through both import paths, and attribute access by Python name are unchanged (3.9–3.11).
- `hatch run release` passes. `models.py` is reproducible from `hatch run generate` (3.12).

**Scope:**
All inputs where isBugCondition is false are unaffected. This includes:
- `serialize_oscal` and any explicit `model_dump*(by_alias=True, exclude_none=True)` call
- All validation input (JSON text, bytes, dicts) through every entry point, including name-keyed input and its pre-existing JSON-mode drop
- Keyword construction using aliases (`**{"media-type": ...}`) or fields without aliases
- Builder calls with valid arguments, including `make_resource` with `document_ids=None` or a valid non-empty `list[DocumentId]`
- Attribute reads and writes, `model_copy`, pickling, equality, `repr`

## Hypothesized Root Cause

The probes confirmed each of these against 2.13.5. They are listed with the evidence.

1. **No serialization defaults on the models**: Generated classes carry only `extra='forbid'`. `model_dump(by_alias=None)` resolves to `serialize_by_alias`, which defaults to False. `exclude_none` defaults to False and has no `ConfigDict` equivalent. Framework serializers can't be fixed by changing `serialize_oscal`, because they never call it.
2. **Codegen has no hook for serializers**: datamodel-codegen 0.83.0 can set a base class (`--base-class`, `--base-class-map`) or emit a generated shared base (`--use-generic-base-class`). It can't attach a `model_serializer`. So the behavior must live in hand-written code that generated code inherits from.
3. **No by-name validation**: Without `validate_by_name`, keyword construction rejects field names. That forced `make_rlink` to build from an alias-keyed dict and `make_resource` to assign `document_ids` after construction, skipping validation because `validate_assignment` is off (defect 1.7).
4. **Config-level `validate_by_name` (Option A) makes alias-only validation opt-in per call (Verified, corrected)**: Option A sets `validate_by_name=True, validate_by_alias=True` in the base config and passes `by_alias=True, by_name=False` at each validation call. An earlier version of this section said the per-call override reached only the outermost model. That was wrong. Its evidence was a JSON-mode probe (`Top.model_validate_json('{"document-ids":[{"media_type":"a"}]}', by_alias=True, by_name=False)` "accepted"), which was the JSON-mode drop (Root Cause 6), not a leak. Re-probed on 2.13.5 against the real models (Option A base injected into a re-exec of `models.py`) and a minimal model:

   | Option A | Dict, no kwargs | Dict, `by_alias=True, by_name=False` | JSON, no kwargs | JSON, `by_alias=True, by_name=False` |
   |---|---|---|---|---|
   | `Rlink` top (`media_type`) | accepted, value kept | `extra_forbidden` | accepted, value kept | accepted, value dropped |
   | `Resource.rlinks[0].media_type` | accepted, kept | `extra_forbidden` at `rlinks.0.media_type` | accepted, kept | dropped |
   | `OscalDocument` → `catalog.back-matter.resources[0].rlinks[0].media_type` | accepted, kept | `extra_forbidden` at full path | accepted, kept | dropped |
   | `OscalDocument` → `catalog.back_matter` | accepted, kept | `extra_forbidden` | accepted, kept | dropped |
   | Constructor `Rlink(media_type=...)`, `Resource(document_ids=[...])` | accepted | n/a | n/a | n/a |
   | Constructor `Resource(rlinks=[{"media_type": ...}])` (nested plain dict) | accepted (name kept) | n/a | n/a | n/a |

   The per-call override does propagate to every depth, under the `RootModel` too. But Option A still fails the constraints:
   - Alias-only becomes opt-in. Any call without the kwargs accepts and **populates** name-keyed input at every depth. That includes users calling `Model.model_validate` / `model_validate_json` directly, `TypeAdapter`s over the models, and any future internal call site. Today all of those reject (dict) or never keep the value (JSON). This regresses 3.3 for the direct-call paths the task-2 preservation tests pin, and we can't add kwargs at call sites we don't control.
   - In JSON mode the per-call kwargs give only the drop, not rejection. So A buys nothing over B there.
   - The constructor can't take per-call kwargs, so nested plain dicts in kwargs would accept names. That contradicts 2.9's "nested plain dicts stay alias-only".

   Option A is the documented API, but it can't keep dict-mode OSCAL input alias-only without per-call kwargs at every site. This design doesn't use it. pydantic's suggested pattern for "construct by name, validate by alias" ([pydantic#12129](https://github.com/pydantic/pydantic/issues/12129)) is the same config + per-call override. A per-mode config (`validate_by_name` for Python input only) is proposed upstream in [pydantic#12056](https://github.com/pydantic/pydantic/issues/12056) but doesn't exist yet. Revisit if it lands.
5. **A plain `__init__` override leaks; the `__pydantic_base_init__` marker (Option B) doesn't (Verified, re-confirmed)**: Pydantic marks any class with a user-defined `__init__` as `__pydantic_custom_init__ = True`, and its validator then calls `__init__` for dict *and* JSON input. Re-probe, variant B0 (override, no marker): `__pydantic_custom_init__ is True`, and name-keyed input was accepted with the value kept, top-level and nested and under `OscalDocument`, in both modes, even with `by_alias=True, by_name=False`. Marking the override with `__pydantic_base_init__ = True`, the mechanism pydantic's own `RootModel.__init__` uses, gives `__pydantic_custom_init__ is False` on every subclass. Re-probe, variant B, same cases:
   - Dict mode: `extra_forbidden` at the name key for `Rlink`, `Resource.rlinks[0]`, `CatalogDocument` deep, `OscalDocument` deep and `catalog.back_matter`, and the minimal model. That holds with and without per-call kwargs.
   - JSON mode: identical to the current tree in every case (the drop, value never kept).
   - Construction: `Rlink(href=..., media_type=...)`, `Rlink(**{"media-type": ...})`, and `Resource(uuid=..., document_ids=[DocumentId(...)])` succeed. `Resource(rlinks=[{"media_type": ...}])` raises `extra_forbidden` at `rlinks.0.media_type`. Name + alias of one field raises `extra_forbidden` at the name. An unknown kwarg raises `extra_forbidden`.
   - Validation doesn't route through `__init__`: with the override patched to raise, `model_validate`, `model_validate_json`, `pickle`, and `model_copy` still succeed. Only direct construction raised. `pickle`, `copy.copy`, `copy.deepcopy`, `model_copy(update=...)`, and `model_fields_set` behave as on the current tree.

   **Decision: Option B.** It meets 2.9 and 3.3/3.4 at every depth with no per-call kwargs, so validation sites we don't control are covered. Its cost is reliance on an undocumented underscore attribute. Permanent tripwires make a change loud (Fix Implementation §3).
6. **Pre-existing: pydantic-core's JSON path drops name-keyed keys (Verified; out of scope)**: with `extra='forbid'` and `by_name` off, `model_validate_json` silently discards a key equal to the Python name of an alias-differing field *of the model being validated*. It's neither used nor reported as extra. Characterized on the current tree:
   - It happens only for that exact key. An unknown key, a near-miss (`how-manyy`), or a name belonging to a different model (e.g. `media_type` inside a `DocumentId`) gets `extra_forbidden` in JSON mode as usual.
   - It happens at every depth, including under `OscalDocument`, and for every `extra` setting. Under `extra='allow'` the key doesn't even land in `__pydantic_extra__`.
   - Optional field: accepted, value lost (`M.model_validate_json('{"how_many":"x"}')` → `how_many=None`). Required field: only `missing` at the alias. Name and alias both present: the alias value wins, and the name key is silently ignored.
   - Dict mode and `model_validate_strings` report `extra_forbidden` for the same input.

   Cause, from the pydantic-core source at the `v2.13.5` tag ([`pydantic-core/src/validators/model_fields.rs`](https://github.com/pydantic/pydantic/blob/v2.13.5/pydantic-core/src/validators/model_fields.rs), `validate_json_by_iteration`): the loop sets `handled = true` for every lookup-tree match *before* the `matches_lookup(lookup_type)` filter. So a by-name match that the active lookup type excludes counts as handled and skips the extra check. Upstream PR [pydantic#13275](https://github.com/pydantic/pydantic/pull/13275) ("Make JSON validation by iteration consistent with getitem approach", open at the time of writing) restructures that loop so such keys fall through to extra handling. Its description calls the iteration path new in 2.13. The task 3.6 floor check confirmed the older behavior on 2.11.0: `Rlink.model_validate_json('{"href":"x","media_type":"t"}')` raises `extra_forbidden` at `media_type`. So the drop is a regression between 2.11.0 and 2.13.5 (2.12.x untested). Neither option fixes the drop: A's per-call `by_name=False` is exactly the case that drops, and B leaves JSON validation untouched. It's tracked in [#6](https://github.com/cairn-proofs/oscal-bindings-python/issues/6).

## Correctness Properties

Property 1: Bug Condition - Default serialization paths emit valid OSCAL

_For any_ generated model instance `m`, or any plain dict/list containing generated model instances, serialized through a default path (isBugCondition returns true), the fixed library SHALL emit no `null` for any model field, and every key emitted for a model field SHALL be that field's OSCAL name (alias where one exists). For whole documents, `json.loads(doc.model_dump_json()) == json.loads(serialize_oscal(doc))`, and the output SHALL validate against the vendored OSCAL JSON Schema. An explicit `by_alias=False` SHALL yield Python field names, still without `null`. `exclude_none=False` SHALL have no effect.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8**

Property 2: Preservation - Validation, serialize_oscal, and public surface unchanged

_For any_ input where isBugCondition returns false, the fixed library SHALL produce the same result as the original. That covers `serialize_oscal` output (byte-identical per corpus document and indent setting); accept/reject outcome, parsed values, and `OscalParseError` contract of every parse/validate entry point; for Python-field-name keys at any nesting depth, `extra_forbidden` at that key in dict mode and the value never kept in JSON mode; `validate_element` outcomes; the `get_supported_element_types()` set; builder results for valid arguments; `OscalDoc` accessor values and errors; public names and object identity; and attribute access.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11, 3.12**

Property 3: Bug Condition - Keyword construction accepts field names

_For any_ generated object model class and any valid set of field values, constructing the model with keyword arguments keyed by Python field names SHALL succeed and produce a model equal to the one constructed with the same values keyed by OSCAL aliases. Supplying both the name and the alias of the same field SHALL be rejected.

**Validates: Requirements 1.6, 2.9**

Property 4: Bug Condition - make_resource validates document_ids

_For any_ `document_ids` value that `Resource` validation rejects (e.g. `[]`, or a list containing items that are not valid `DocumentId`s), `make_resource(document_ids=...)` SHALL raise `pydantic.ValidationError`. _For any_ valid non-empty `list[DocumentId]`, it SHALL return a model equal to the pre-fix result.

**Validates: Requirements 1.7, 2.13, 3.8**

## Fix Implementation

### Changes Required

**File**: `src/oscal_bindings/v1/_base.py` (new, hand-written)

**Class**: `OscalBaseModel(BaseModel)`

1. **Alias-by-default**: `model_config = ConfigDict(serialize_by_alias=True)`. Subclass configs (`extra='forbid'`) merge with it. **Verified**: the merged config is `{'serialize_by_alias': True, 'extra': 'forbid'}`. Explicit `by_alias=False` still wins at every depth (2.8).
2. **Omit None on every path**: a wrap serializer.
   ```python
   @model_serializer(mode="wrap")
   def _omit_none(self, handler: SerializerFunctionWrapHandler):  # no return annotation: see below
       data = handler(self)
       if type(data) is dict:
           return {k: v for k, v in data.items() if v is not None}
       return data
   ```
   - Because it's part of each model's core schema, it runs for `model_dump*`, `pydantic_core.to_json`, and `TypeAdapter` alike. **Verified**: all paths emit aliases and no `null`, including models nested in plain dicts/lists and under a `RootModel`.
   - `include` / `exclude` / `exclude_unset` / `exclude_defaults` / `by_alias` / `round_trip` are applied by `handler` first and keep working.
   - Return annotation is omitted on purpose. Pydantic derives the serialization JSON schema from it. **Verified**: `-> Any` collapsed `Rlink.model_json_schema(mode="serialization")` to an empty schema, while the unannotated version keeps the full per-field schema. That matters for MCP SDKs that publish output schemas. The function stays type-checked by mypy because its parameters are annotated; a comment records why.
   - **2.8, settled**: `exclude_none=False` is accepted and has no effect. None-valued fields are always omitted. `SerializationInfo.exclude_none` is a plain bool defaulting to False, so an explicit False can't be told apart from the default. No null-emitting opt-out is provided, because OSCAL forbids `null` everywhere. Callers who need to know which fields are unset use attribute access or `model_fields_set`. The supported opt-out is `by_alias=False`, which emits field names.
3. **By-name keyword construction**:
   ```python
   def __init__(self, /, **data: Any) -> None:
       for name, alias in _kwarg_aliases(type(self)).items():
           if name in data and alias not in data:
               data[alias] = data.pop(name)
       super().__init__(**data)

   # Keep pydantic from treating this as a custom __init__. Otherwise model_validate*
   # would route dict/JSON input through it and accept name-keyed OSCAL input (3.3/3.4).
   __init__.__pydantic_base_init__ = True  # type: ignore[attr-defined]
   ```
   - `_kwarg_aliases(cls)` is a `functools.cache`'d module function that returns `{name: alias}` for alias-differing fields. It's computed lazily on first construction, so classes completed via `model_rebuild()` are handled. It excludes any name that is also some field's alias, which guards against ambiguity.
   - If both name and alias are passed, the name is left in place, so `extra='forbid'` rejects it (`extra_forbidden`). **Verified.**
   - Only the constructor's own kwargs are mapped. Nested plain dicts go through the nested model's validator and stay alias-only, consistent with the decision. Nested model instances are unaffected.
   - `model_validate*`, `model_validate_json`, `model_copy`, and pickling don't call `__init__`. **Verified**: pickle round-trip and `model_copy(update=...)` behave as before.
   - No `validate_by_name` / `validate_by_alias` in the base config, and no per-call `by_alias` / `by_name` at internal call sites. Alias-only dict validation then comes from pydantic's defaults, so it covers call sites we don't control. Option A was re-probed and rejected (Root Cause 4).
   - Risk: `__pydantic_base_init__` is an underscore attribute, not documented API. It has been stable since pydantic 2.0 and is what `RootModel` relies on. Three permanent tripwires make a change loud. Each failure message points at Root Cause 5:
     - Structural: the marker is on `OscalBaseModel.__init__`, and every object model has `__pydantic_custom_init__ is False` and defines no `__init__`.
     - Config: `validate_by_name` and `populate_by_name` are absent or False, and `validate_by_alias` isn't False, in `OscalBaseModel.model_config` and in every object model's merged config. This catches a later "simplification" to Option A.
     - Behavioral: the task-2 name-keyed tests at every depth. Dict mode asserts `extra_forbidden` at the key. JSON mode asserts the value is never kept, which a B0-style regression breaks, since the probe showed it populates by name.
4. **Typing**: mypy (no pydantic plugin) synthesizes `__init__` from `dataclass_transform` using **Python field names**. **Verified**: `reveal_type(Rlink.__init__)` gives `def (self, *, href: str, media_type: str | None =, hashes: ... =)`. Today mypy accepts `Rlink(media_type=...)` while runtime rejects it. After the fix they agree. Subclasses don't define `__init__`, so synthesis continues per subclass. The `typing` gate confirms this, since `builders.py` will use name kwargs. Pyright synthesizes alias-named params; that's unchanged and out of scope.

**File**: `pyproject.toml` (`[tool.hatch.envs.default.scripts].generate`)

5. **Wire the base via codegen**: add `--base-class oscal_bindings.v1._base.OscalBaseModel` to the `datamodel-codegen` invocation, then `hatch run generate`.
   - **Verified**: codegen emits `from oscal_bindings.v1._base import OscalBaseModel` and `class X(OscalBaseModel)` for all 183 object models. It drops the now-unused `BaseModel` import. `RootModel` classes keep `RootModel[...]`. The unmodified post-processor runs cleanly on that output. The only diff against today's `models.py`, after normalizing the base name, is the import block.
   - Why `--base-class` and not post-processor rewriting: it's the generator's supported mechanism. It keeps the post-processor a rename/cleanup pass, avoids new regex over class headers and imports, and stays reproducible (3.12).
   - Why not `--use-generic-base-class`: that base is emitted *inside* the generated file, which can't carry hand-written serializer code.
   - Import cycle: `_base.py` imports only `pydantic`, `functools`, and `typing`, so `models.py → v1._base` is cycle-free whichever package path is imported first.
   - **RootModels** (`OscalDocument`, `Mappings`) intentionally don't get the base. They have no aliased fields and no None-valued optional fields at their own level. Their serialization delegates to children, which carry the base behavior (**Verified**). `RootModel.__init__(root=...)` needs no name mapping. `--base-class-map` is not needed.

**File**: `src/oscal_bindings/v1/extensions/validate_element.py`

**Function**: `_build_element_map`

6. **Exclude the base from element types (3.7)**: `OscalBaseModel` now appears in `dir(models)` and would add `oscal-base-model`. Change the guard to `obj not in (BaseModel, OscalBaseModel)`. Don't switch to a `__module__ == models` filter: that would also drop the pre-existing `root-model` entry (from the `RootModel` import) and change the set. Cleaning up that quirk is out of scope and noted in Follow-ups. `validate_element` keeps calling `model_validate(element)` with no extra kwargs; alias-only behavior comes from the models (item 3).

**File**: `src/oscal_bindings/v1/extensions/builders.py`

7. **Simplify `make_rlink` / `make_resource` (3.8)**: signatures unchanged.
   - `make_rlink` → `Rlink(href=href, media_type=media_type, hashes=hashes)`.
   - `make_resource` → a single `Resource(uuid=..., title=..., description=..., rlinks=..., document_ids=document_ids)`. Drop the post-construction assignment and its comment.
   - Valid arguments produce equal models (3.8).
   - **Decision (1.7, 2.13)**: `document_ids` is validated at construction, like `rlinks`. The post-construction assignment bypassed validation because `validate_assignment` is off, so `make_resource(document_ids=[])` silently produced invalid OSCAL (`"document-ids": []` violates `min_length=1`) and non-`DocumentId` items were stored unchecked. After the fix both raise `ValidationError`, matching the module docstring's "raises `pydantic.ValidationError` on invalid input". Update the `make_resource` docstring to say so.

**File**: `src/oscal_bindings/v1/parser.py`

8. **No logic change.** `serialize_oscal` keeps its explicit `by_alias=True, exclude_none=True`: it's harmless, self-documenting, and protects 3.1 if the base defaults ever change. Update the docstring to say default `model_dump_json()` now gives equivalent output. Parse/validate functions don't add `by_alias=True, by_name=False` per call. Under Option B the config has no `validate_by_name`, so `by_name` already resolves to False. The parse functions are JSON-mode, where the explicit override still gives the drop (Root Cause 6), so it would suggest protection that isn't there. Don't touch the parse docstrings about name-keyed input; README documents the drop (§10).

**File**: `pyproject.toml`, lockfiles

9. **Pydantic floor (2.10)**: `dependencies = ["pydantic[email]>=2.11"]`. `serialize_by_alias` arrived in 2.11. Run `hatch run lock`. Expected lockfile diff: the `# - pydantic[email]>=2.11` header lines in `requirements.txt` and both `hatch-test` lockfiles. Pins stay at 2.13.5. Add test-only deps for schema validation (Testing Strategy) to `[tool.hatch.envs.hatch-test].extra-dependencies` (`jsonschema`, `regex`) and re-lock in the same pass. Run `hatch run security` over the new lockfiles. A one-off floor check runs through hatch: a temporary, uncommitted `type = "virtual"` env in `pyproject.toml` pinning `pydantic[email]==2.11.0` runs the new serialization tests plus `test_parser.py`, then the env is removed and the addition reverted. Report the result; it isn't added to CI.

**Files**: `README.md`, `DEVELOPING.md`, `AGENTS.md`, `.agents/summary/*.md`

10. **Docs (2.11)**:
    - README **Serialization**: aliases on and None omitted by default on all paths (`model_dump*`, `to_json`, `TypeAdapter`); `serialize_oscal` still recommended for documents; opt-outs exactly as settled in item 2; name-keyed policy:
      - Constructor kwargs accept names or aliases. Plain dicts nested in kwargs are alias-only.
      - Dict input (`model_validate`, `validate_element`) rejects name keys at every depth.
      - JSON input to the parse/validate functions never populates a field from a name key. A short "Known issue" note explains that on recent pydantic (observed on 2.13.x; 2.11.0 rejects) such a key is silently dropped rather than rejected, and links [#6](https://github.com/cairn-proofs/oscal-bindings-python/issues/6).

      **Requirements**: Pydantic ≥2.11. **Building back-matter**: drop alias caveats if present.
    - DEVELOPING: `--base-class` in the Code Generation Pipeline. A Key Design Decisions entry "Valid OSCAL by default" covering:
      - the wrap serializer (chosen) and the `exclude_if` fallback (measured, not implemented, needs pydantic ≥2.12);
      - the `__pydantic_base_init__` rationale (Option B), with the B0 leak evidence;
      - why config `validate_by_name` + per-call `by_alias=True, by_name=False` (Option A) was rejected: alias-only becomes opt-in per call, and JSON mode only drops (Root Cause 4);
      - the JSON-mode drop as a known upstream behavior (Root Cause 6).

      Benchmark results (item 11).
    - AGENTS.md: replace the "Models forbid extras and don't populate-by-name" gotcha and mention `_base.py` in the directory map. Update `.agents/summary` (`data_models.md` populate-by-name row, `dependencies.md` floor, `architecture.md` builders paragraph, `components.md` `_build_element_map`).
    - Comments in `tests/strategies.py` and `tests/test_prop_builders.py` that describe the old workaround.

**File**: `scripts/bench_serialization.py` (new, hand-written)

11. **Benchmark (2.12)**: takes `--catalog PATH`, defaulting to the corpus-cache SP 800-53 rev5 catalog. It reports the median of N runs (default 7, after one warm-up) for `parse_oscal(bytes)`, `serialize_oscal(doc, indent=None)`, `serialize_oscal(doc)`, `doc.model_dump_json()`, and `pydantic_core.to_json(doc)`, plus Python/pydantic versions. It only uses API present before and after the fix, so the same script runs on both trees. Procedure: commit the script first and run it on the unfixed tree (`> ./tmp/bench_before.log 2>&1; echo "EXIT: $?"`). Apply the fix and run it again (`bench_after.log`). Record both tables in DEVELOPING.md and the PR description. Note: `hatch run` expands `{...}` in arguments, so probes must live in files, not `python -c`.

   Preliminary numbers from the prototype (2.13.5, Python 3.12, median of 7, compact):

   | Path | Before | After (wrap serializer) |
   |------|--------|-------------------------|
   | `parse_oscal` | ~268 ms | ~270–310 ms (unchanged mechanism; noise) |
   | `serialize_oscal(indent=None)` | ~52 ms | ~125 ms |
   | `model_dump_json()` | invalid OSCAL | ~131 ms |
   | `pydantic_core.to_json(doc)` | invalid OSCAL | ~137 ms |

   That's roughly 2.4× on serialization, from a Python callback per model node; parse is unaffected. The wrap serializer is the final choice and this regression is accepted; the before/after tables document it.

   **Fallback (documented only, not implemented)**: per-field `Field(exclude_if=lambda v: v is None)` on all 698 optional fields measured ~71 ms (~1.35×) with identical output. It was not chosen because it needs the post-processor to rewrite every optional field in generated text, a large regex surface and diff. It would also raise the pydantic floor to 2.12: `exclude_if` was introduced in pydantic 2.12 ([Pydantic v2.12 release notes](https://pydantic.dev/articles/pydantic-v2-12-release), PR #12141 / pydantic-core#1535), so it is unavailable at the 2.11 floor this design sets. Aliases and by-name construction would still come from `OscalBaseModel`.

### Follow-ups (out of scope)
- `root-model` in `get_supported_element_types()` is an artifact of the `RootModel` import; removing it is a separate, deliberate API change.
- A min-deps CI job pinned to `pydantic==2.11.0`.
- Silent JSON-mode drop of name-keyed keys (Root Cause 6; bugfix 3.3(b)). Tracked in [#6](https://github.com/cairn-proofs/oscal-bindings-python/issues/6); pydantic 2.11.0 rejects the key, 2.13.5 drops it. Possible fixes: wait for pydantic#13275, or add a library-side check in the parse entry points that reports name-keyed keys as `extra_forbidden`. The second option changes 3.2/3.3, so it's deliberately not part of #5.
- If pydantic ships per-mode `validate_by_name` (pydantic#12056), re-evaluate replacing the `__pydantic_base_init__` marker with documented config.

## Testing Strategy

### Validation Approach

First, run exploration tests on the unfixed code to surface counterexamples and capture before-state (serialize digests, element-type set, benchmark). Then apply the fix and verify Property 1 and Property 3 (fix checking) and Property 2 (preservation) with unit, property-based, and corpus tests. Slow runs follow the repo rule: `cmd > ./tmp/<name>.log 2>&1; echo "EXIT: $?"`. Commands never start with `cd`; use the tool's `cwd`.

### Exploratory Bug Condition Checking

**Goal**: Demonstrate the defect on F and confirm the root causes above before changing code.

**Test Plan**: Add `tests/test_serialization_defaults.py` with the matrix below and run it on F. Expect failures. Also capture the before-state artifacts in `./tmp/` (gitignored): `serialize_oscal` SHA-256 per corpus doc for `indent=2` and `indent=None`, the sorted `get_supported_element_types()` list, and `bench_before.log`.

**Test Cases**:
1. **Required-only element**: `Capability(uuid, name, description)` via each default path → `null` and snake keys (fails on F).
2. **Framework containers**: `pydantic_core.to_json({"k": [rlink]})` and `TypeAdapter(dict[str, Any]).dump_python({"k": m}, mode="json", by_alias=True)` → `null` present (fails on F).
3. **Corpus document**: `json.loads(doc.model_dump_json()) != json.loads(serialize_oscal(doc))` for the 800-53 catalog (fails on F).
4. **Name kwargs**: `Resource(uuid=U, document_ids=[...])` → `ValidationError` (fails on F).
5. **Unvalidated `document_ids`**: `make_resource(document_ids=[])` and `make_resource(document_ids=["x"])` are expected to raise `ValidationError` but return a model on F (fails on F).
6. **Name-keyed input, top-level and nested** (passes on F; recorded as the preservation baseline):
   - Dict mode: `OscalDocument.model_validate` with `back_matter` raises `extra_forbidden`. So do `validate_element({"href": ..., "media_type": ...}, "rlink")` and nested `rlinks[0].media_type` under `resource`.
   - JSON mode: `parse_oscal` with `back_matter` is accepted with `back_matter is None`, and with `oscal_version` it fails as `missing` at `oscal-version` (the drop, Root Cause 6).

**Expected Counterexamples**:
- `null` values and `_` keys in default-path output at every depth.
- Construction rejects `document_ids` / `media_type` as extra inputs.
- `make_resource` returns a model for `document_ids=[]` and non-`DocumentId` items instead of raising.
- Cause: missing serialization defaults and by-name construction on the models (root causes 1–3).

### Fix Checking

**Goal**: Verify Property 1, Property 3, and Property 4 on F'.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  IF input IS SerializationCall THEN
    out := serialize(input.value, input.path)            // F'
    ASSERT noNullAtModelFields(out)
    ASSERT allModelKeysAreOscalNames(out, schemaPropertyNames)
    IF input.value IS OscalDocument THEN
      ASSERT json.loads(out) = json.loads(serialize_oscal(input.value))
      ASSERT schemaValidate(json.loads(out), vendoredSchema)
  ELSE IF input IS ConstructionCall THEN
    ASSERT construct(cls, byName(values)) = construct(cls, byAlias(values))
  ELSE  // MakeResourceCall
    ASSERT make_resource(**input.kwargs) RAISES pydantic.ValidationError
END FOR
```

### Preservation Checking

**Goal**: Verify Property 2. For all inputs outside C, F' matches F.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT F(input) = F'(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain
- It catches edge cases that manual unit tests might miss
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on F first (digests, element set, existing suites green), then assert it on F'.

**Test Cases**:
1. **serialize_oscal byte-identity (3.1)**: a one-off script compares F' SHA-256 digests against the F digests captured in `./tmp/`, for every NIST/AWS corpus doc at both indent settings. The permanent test asserts `serialize_oscal(doc) == doc.model_dump_json(indent=2, by_alias=True, exclude_none=True)` and keeps the existing round-trip properties.
2. **Name-keyed input at depth (3.3, 3.4)**, in `tests/test_prop_serialization_preservation.py` (task 2, done). Hypothesis picks a corpus doc and a random alias-differing key at a random depth, and renames it to its Python name. Two kinds of assertion:
   - Dict mode, strict: `OscalDocument.model_validate`, the wrapper's `model_validate`, the owning model's `model_validate(subtree)`, and `validate_element` (allow-listed leaf types and nested `resource.rlinks[i]`) must report `extra_forbidden` at the renamed key, not just any error.
   - JSON mode, "never kept": `parse_oscal` (str and bytes), `parse_oscal_file`, the typed `parse_*`, `OscalDocument.model_validate_json`, and the owning model's `model_validate_json`. Rejection must be `extra_forbidden` at the name or, for a required field, `missing` at the alias. Acceptance is allowed only for an optional field, and the field must be `None`. `validate_oscal` must agree with the parse functions on accept/reject.

   This is the behavioral tripwire for the `__pydantic_base_init__` marker. A B0-style regression fails the dict assertions, and it also fails the JSON assertions because the value would now be kept. If pydantic fixes the drop (pydantic#13275), the JSON assertions still pass via `extra_forbidden`.
3. **Element-type set (3.7)**: `get_supported_element_types()` equals a committed snapshot of the pre-fix list. `"oscal-base-model"` is absent.
4. **Structure (3.12)**: every class in `models.py` other than `OscalDocument` / `Mappings` that is a `BaseModel` subclass is an `OscalBaseModel` subclass. `models.py` contains no `(BaseModel)` header. `hatch run generate` leaves `git diff --exit-code src/oscal_bindings/v1/models.py` clean.
5. **Existing suites (3.2, 3.5, 3.6, 3.8–3.11)**: corpus, mutation, round-trip, facade, builder, version-package, and postprocess suites pass with their validation assertions unchanged. Only comments describing the old builder workaround are updated.

### Unit Tests

- Serialization-path matrix in `tests/test_serialization_defaults.py`, parametrized over **models** × **paths**. Models: `Capability` required-only, `Rlink` with and without `media_type`, `Resource` with `document_ids`, a `Metadata` from a corpus doc, a full `CatalogDocument`, and an `OscalDocument`. Paths: `model_dump()`, `model_dump(mode="json")`, `model_dump_json()`, `to_json(m)`, `to_json({"k": [m]})`, `TypeAdapter(dict[str, Any]).dump_python({"k": m}, mode="json")` with `by_alias` omitted and True. Assert no `None`/`null` recursively, and every key ∈ `schemaPropertyNames`, the set of all `properties` keys collected recursively from the vendored schema.
- Opt-outs (2.8): `by_alias=False` gives Python names at depth with no `null`. `exclude_none=False` output equals the default output (documented no-op). `include`/`exclude`/`exclude_unset` still honored.
- Construction smoke cases (2.9): name kwargs, alias kwargs (`**{"media-type": ...}`), mixed fields, unknown kwarg → `ValidationError` (`extra_forbidden`).
- Mechanism tripwires (`tests/test_base_model.py`; Root Causes 4–5, 3.3/3.4). Failure messages name the root cause, so a pydantic change to the mechanism, or a well-meant switch to Option A, fails loudly instead of silently relaxing validation:
  - Structural: `OscalBaseModel.__init__` carries `__pydantic_base_init__`. Every object model and `OscalBaseModel` itself has `__pydantic_custom_init__ is False`. Generated classes define no `__init__`.
  - Config: `validate_by_name` and `populate_by_name` are falsy and `validate_by_alias` is not False on `OscalBaseModel` and every object model.
  - Behavioral canaries:
    - Dict mode: top-level `Rlink.model_validate({"href": ..., "media_type": ...})`, nested `Resource.model_validate({..., "rlinks": [{... "media_type": ...}]})`, and `OscalDocument.model_validate` with a deep name key all raise `extra_forbidden` at the name key. Each is called both with no kwargs and with `by_alias=True, by_name=False`.
    - JSON mode: the same inputs via `model_validate_json` never keep the value. On 2.13.5 that's acceptance with `media_type is None`; `extra_forbidden` is also allowed.
- Exhaustive construction (Property 3; 1.6, 2.9), parametrized over every `(class, field)` with an alias-differing field from `model_fields` across all 183 object models, not a sample. The parameter set is asserted non-empty and the class count pinned so it can't go vacuous. Per field: by-name and by-alias kwargs give the same outcome (equal models, or identical `(type, loc, msg)` error lists, never `extra_forbidden` for the name). Per class with a valid instance harvested from the corpus and leaf strategies: by-name == by-alias == `model_validate(alias dict)` == the instance; coverage gaps must be listed in an explicit constant. Both name and alias of one field → `extra_forbidden`. A nested name-keyed dict passed inside kwargs → `extra_forbidden` at the nested key.
- Copy and pickle (Preservation scope): for every harvested instance and sampled corpus docs, `pickle` round-trip, `copy.copy`, `copy.deepcopy`, `model_copy()`, and `model_copy(update={name: v})` behave as on F, preserving `model_fields_set`. With `OscalBaseModel.__init__` monkeypatched to raise, these and `model_validate*` still succeed, proving they don't route through `__init__`.
- Builders: `make_rlink` / `make_resource` equality with pre-fix construction for valid args. `make_resource(document_ids=[])` and `make_resource(document_ids=[<non-DocumentId item>])` raise `ValidationError` (Property 4; 1.7, 2.13).
- Serialization JSON schema: `Rlink.model_json_schema(mode="serialization")` still lists `href`, `media-type`, `hashes`.
- Validation entry points (covered by the task-2 property tests, plus the canaries above):
  - Dict input (direct `model_validate`, `validate_element`): `extra_forbidden` at the name key, top-level and nested.
  - JSON input (`parse_oscal`, `parse_oscal_file`, `validate_oscal`, typed `parse_*`, `model_validate_json`): value never kept, per 3.3(b).

### Property-Based Tests

- **Property 1** (`tests/test_prop_serialization_defaults.py`): from `all_corpus_docs` via `st.data()`, assert default `model_dump_json()` equals `serialize_oscal` semantically, `to_json` agrees, and there are no nulls or non-schema keys. Using the existing leaf strategies in `tests/strategies.py`, randomly set optional fields to None or values, then assert the same invariants across all default paths.
- **Property 3** (`tests/test_prop_base_model.py`): for a drawn leaf model class and random valid field values, keyword-by-name == keyword-by-alias == `model_validate(alias dict)`, and both name and alias of a drawn field are rejected. This complements the exhaustive unit test above with random values.
- **Property 2**: the name-keyed-at-depth rejection property above, plus reuse of the existing round-trip/mutation properties unchanged. Uses the `ci` Hypothesis profile (≥100 examples).

### Integration Tests

- **Corpus schema validation (2.5)**: for every NIST and AWS corpus doc, validate `json.loads(doc.model_dump_json())` against `schemas/1.2.3/oscal_complete_schema.json`. Use `jsonschema`'s Draft-07 validator extended with a `pattern` keyword backed by the `regex` module (`jsonschema.validators.extend`). OSCAL patterns use `\p{L}` / `\p{N}`, which stdlib `re` rejects. The validator is built once per session. If the runtime proves too slow on the full corpus, switch to `jsonschema-rs` (Unicode-class regex support), with the choice recorded in DEVELOPING.md. Both are well-known packages, locked via hatch-pip-compile.
- **Framework-shaped calls**: MCP text content (`pydantic_core.to_json([doc])`), MCP structured content (`TypeAdapter(dict[str, Any]).dump_python({"result": doc}, mode="json", by_alias=True)`), and a Strands-style argument-less `model_dump_json()`, all re-parsed with `parse_oscal` and compared to `serialize_oscal`.
- **Release gate**: `hatch run release > ./tmp/release.log 2>&1; echo "EXIT: $?"`, covering generate (reproducibility), lint, typing (mypy over `_base.py` and name-kwarg `builders.py`), security (new lockfiles), tests on 3.11 + 3.12, and docs. Then run the benchmark after the fix and compare against `bench_before.log`.
