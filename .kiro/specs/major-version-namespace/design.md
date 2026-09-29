# Design Document

## Overview

Two coupled changes, plus one bug fix that fell out of designing them.

1. **Relocate** the public API into `oscal_bindings.v1`, leaving the top level as a pure re-export shim. The namespace is scoped to the OSCAL *major* version, matching the actual compatibility boundary.
2. **Parameterize** the codegen pipeline on schema and output paths, and vendor schemas under release-versioned directories, so a 1.x refresh is a path change rather than a script edit.
3. **Fix** the positional `Model1..Model8` → `*Document` mapping in the post-processor, replacing it with content-based derivation.

### Why major-version granularity

The repo's existing compatibility argument (now recorded under Key Design Decisions in `DEVELOPING.md`) is that OSCAL 1.x is backward-compatible within the major version, so one binding set covers every 1.x producer. A `v1_2` namespace would contradict that argument in its own naming — it encodes a break at each minor bump that the argument says does not exist, and would force a new package plus dispatch logic on every routine schema refresh.

NIST's own schema `$id` supports the same split. From `schemas/oscal_complete_schema.json`:

```
http://csrc.nist.gov/ns/oscal/1.0/1.2.2/oscal-complete-schema.json
                            ^^^        ^^^^^
                            namespace  release
```

The namespace is major-scoped; the release hangs off it as metadata. `oscal_bindings.v1` + `__oscal_schema_version__ = "1.2.3"` mirrors that structure exactly.

### The honesty problem, and how we handle it

All 183 model classes in `models.py` carry `extra='forbid'`. So `v1` bindings generated from release 1.2.3 will *reject* a hypothetical 1.3 document that uses a new field, even though both are nominally "v1". The namespace promises major-version coverage; the models deliver coverage up to the generated release.

We do not paper over this. Options considered:

| Option | Verdict |
|---|---|
| Relax to `extra='ignore'` | Rejected. Unknown fields would be silently dropped, so `serialize_oscal` would lose data the input carried — a worse failure than a loud validation error. |
| Strict default + opt-in lenient mode | Deferred. Correct, but it is real API design work with no current consumer demand. |
| Track the current release, expose the version | **Chosen.** Purely additive, makes the gap visible instead of hidden, costs one constant. |

Hence Requirements 6 and 7: expose `__oscal_schema_version__`, and refresh to the current release as part of this work.

### Key design decisions

| Decision | Choice | Rationale |
|---|---|---|
| Namespace granularity | `v1` (major only) | Matches the compatibility boundary and NIST's `$id` structure. Minor refreshes cause zero consumer churn. |
| Hand-written layer placement | **Move bodily into `v1/`** | See below — the alternative is speculative. |
| Shared abstraction between versions | None built now | There is one major version. Extracting a version-agnostic core requires knowing what differs at 2.0, which is unknowable today. Req 10.5 forbids it explicitly. |
| Top-level back-compat | Pure re-export shim, no deprecation warning | The move is not a deprecation; the flat paths stay supported. A warning would be noise. |
| Wrapper name derivation | Content-based, from the body field | Positional mapping is a latent correctness bug (see below). |
| Post-processor failure mode | Exit non-zero, loudly | Silent mis-renaming is the failure we are eliminating; a hard stop is the point. |
| Guard granularity | Ambiguity fails fast; collisions accumulate | Deliberately asymmetric — see "Why the two guards differ". |
| Schema directory naming | Full release (`schemas/1.2.3/`) | The bundle is a release artifact even though the package is major-scoped. Keeps provenance reviewable in git. |

### Why the hand-written layer moves rather than being parameterized

`parser.py`, `extensions/document.py`, and `extensions/validate_element.py` are all bound to `models.py` at import time — `parser.py` imports the 8 wrappers directly, `document.py` builds `_WRAPPER_TO_BODY_ATTR` and the `OscalBody`/`OscalWrapper` unions from concrete classes, and `validate_element.py` builds `_ELEMENT_MAP` at import from `dir(_models)`.

None of that logic is version-specific in *content*, only in *binding*. So one could invert the dependency: keep the modules at the top level and have them take a models module. That is the wrong call right now. It would mean converting import-time module state into factories (the `_ELEMENT_MAP` construction especially) to serve a second major version that does not exist, guessing at the seam before knowing where 2.0 actually differs.

Moving the files is a `git mv` plus import-path rewrites. When 2.0 arrives we will duplicate roughly 500 lines once, *then* factor out whatever genuinely turns out to be shared — with the differences in hand instead of imagined. Recording that as a deliberate deferral is the point of Req 10.5.

### The positional rename bug

`scripts/postprocess_models.py` currently hardcodes:

```python
DOCUMENT_RENAMES = {
    "Model1": "CatalogDocument",
    "Model2": "MappingCollectionDocument",
    ...
}
```

Those ordinals are an artifact of the order `datamodel-codegen` walks the schema's top-level `oneOf`. If a schema revision adds a document type or reorders that list, the map still applies cleanly and produces **wrong names** — `Model2` becomes `MappingCollectionDocument` regardless of what `Model2` now contains. Nothing fails; the output is just silently mislabelled, and the mislabelling propagates into `parser.py`'s `hasattr` checks and `document.py`'s dispatch map.

There is a robust signal available in the generated source. Every wrapper class has exactly one `$schema` directive field plus exactly one body field named for its root key:

```python
class CatalogDocument(BaseModel):          # generated as Model1
    model_config = ConfigDict(extra='forbid')
    field_schema: Annotated[str | None, Field(alias='$schema', ...)] = None
    catalog: Catalog                        # <- the signal
```

So: for each `Model<N>` class, take its single non-`field_schema` field name, PascalCase it, append `Document`. `catalog` → `CatalogDocument`. `system_security_plan` → `SystemSecurityPlanDocument`. No ordering assumption anywhere, and it self-corrects when the schema changes.

**Verified against the committed 1.2.2 output**, not just assumed. All eight wrappers have exactly two fields, and PascalCasing the body field reproduces the current published name in every case:

| Wrapper | Fields | Derived name |
|---|---|---|
| `CatalogDocument` | `field_schema`, `catalog` | `CatalogDocument` ✓ |
| `ProfileDocument` | `field_schema`, `profile` | `ProfileDocument` ✓ |
| `ComponentDefinitionDocument` | `field_schema`, `component_definition` | `ComponentDefinitionDocument` ✓ |
| `SystemSecurityPlanDocument` | `field_schema`, `system_security_plan` | `SystemSecurityPlanDocument` ✓ |
| `AssessmentPlanDocument` | `field_schema`, `assessment_plan` | `AssessmentPlanDocument` ✓ |
| `AssessmentResultsDocument` | `field_schema`, `assessment_results` | `AssessmentResultsDocument` ✓ |
| `PlanOfActionAndMilestonesDocument` | `field_schema`, `plan_of_action_and_milestones` | `PlanOfActionAndMilestonesDocument` ✓ |
| `MappingCollectionDocument` | `field_schema`, `mapping_collection` | `MappingCollectionDocument` ✓ |

The parity gate (Req 3.7) therefore has a known-good expected result, and task 3's byte-identical regeneration check should hold.

The guards matter as much as the derivation. Ambiguity (a wrapper with two body fields) and count mismatch (derived wrappers ≠ document types in the schema) both hard-stop, because the whole purpose is converting a silent-wrong-output failure into a visible one.

### Why the two guards differ

The ambiguity guard (Req 3.5) stops at the first offender; the collision guard (Req 7.3) finishes the run and reports every offender. That asymmetry is intentional, not an oversight.

An ambiguous wrapper means the derivation's core assumption — one `$schema` field plus exactly one body field — no longer holds for this schema. Everything downstream of Phase 2 is built on the rename map, so continuing produces output whose meaning is undefined, and the first offending class is already the entire diagnosis: the maintainer needs to go look at the schema, not at a list. Scanning on would only add noise to a report nobody can act on incrementally.

Collisions are the opposite shape. Each one is independent of the others, and the fix is a line in `COLLISION_OVERRIDES`. A maintainer resolving them wants the complete list from one regeneration so they can add all the overrides at once, rather than rediscovering the next collision on each of N re-runs.

## Architecture

### File layout

Before:

```
schemas/
  oscal_complete_schema.json           # 1.2.2, flat
  oscal_catalog_schema.json
  ...
src/oscal_bindings/
  __init__.py                          # re-exports + `from .models import *`
  models.py                            # generated
  parser.py
  extensions/{__init__,document,builders,validate_element}.py
```

After:

```
schemas/
  1.2.3/                               # release-versioned Schema_Bundle
    oscal_complete_schema.json
    oscal_catalog_schema.json
    ...
src/oscal_bindings/
  __init__.py                          # Compat_Shim — pure re-exports from v1
  v1/
    __init__.py                        # Version_Package surface + __oscal_schema_version__
    models.py                          # generated
    parser.py
    extensions/{__init__,document,builders,validate_element}.py
```

The old `schemas/*.json` files move into `schemas/1.2.3/` as part of the refresh. Only `oscal_complete_schema.json` is a codegen input; the per-model schemas are vendored for reference and move with it.

### Module path compatibility

Req 5.5 requires `oscal_bindings.models`, `oscal_bindings.parser`, and `oscal_bindings.extensions` to keep resolving, not just the flat names. Consumers do write `from oscal_bindings.models import Catalog`.

Approach: thin alias modules at the old paths, each re-exporting from its `v1` counterpart. Preferred over `sys.modules` aliasing — it is explicit, greppable, survives static analysis, and keeps `pdoc` and `mypy` working without special cases. Req 5.6 (type identity) falls out for free: re-exporting binds the same class object, so `isinstance` across old and new paths agrees.

`oscal_bindings/__init__.py` currently does `from oscal_bindings.models import *`, which is what makes every generated model name a top-level import. The shim preserves that by star-importing from `oscal_bindings.v1.models`.

### Codegen pipeline

```
hatch run generate
  │
  ├─ datamodel-codegen
  │    --input  schemas/<release>/oscal_complete_schema.json
  │    --output src/oscal_bindings/v1/models.py
  │    (flags unchanged)
  │
  └─ python scripts/postprocess_models.py
       --schema schemas/<release>/oscal_complete_schema.json
       --models src/oscal_bindings/v1/models.py
       │
       ├─ Phase 1  collapse scalar RootModels, fix patterns   (unchanged)
       ├─ Phase 2  derive Document_Rename_Map from source     (CHANGED — was positional)
       │           guard: ambiguous wrapper      → FAIL FAST: report the first
       │             offending class and exit 1 immediately; remaining
       │             candidate wrappers are left unscanned  (Req 3.5)
       │           guard: count mismatch         → exit 1, report both counts
       ├─ Phase 3  rename root Model → OscalDocument          (unchanged)
       ├─ Phase 4  VARIANT_RENAMES                            (unchanged)
       └─ Phase 5  strip namespace prefixes, COLLISION_OVERRIDES (unchanged)
                   guard: unresolved collision   → ACCUMULATE ALL: finish
                     processing every wrapper, collect all uncovered
                     collisions, then exit 1 reporting the complete
                     list                                    (NEW, Req 7.3)
```

Both the codegen step and the post-processor receive the Active_Schema_Bundle path **explicitly** on every invocation (Req 1.3, 1.5). Selection is by that supplied path alone — no directory scan, no "newest wins" ordering, no dependence on how many Schema_Bundles happen to be vendored (Req 1.4). Adding `schemas/1.3.0/` alongside `schemas/1.2.3/` changes nothing until the passed path changes.

`MODELS_PATH` and `SCHEMA_PATH` become argparse-defaulted parameters rather than module constants. Each argument carries its own `default=`, so the two resolve **independently**: omitting `--schema` falls back to the Active_Schema_Bundle schema path whether or not `--models` was supplied, and vice versa (Req 2.3). This is plain argparse default behavior — worth stating because the naive alternative (an `if not args.schema and not args.models:` fallback block) would couple them and break the mixed case. A bare `python scripts/postprocess_models.py` therefore still works, and so does supplying exactly one of the two.

### Sequencing constraint

The schema refresh (Req 7) and the package move (Req 4) must land as **separate commits**, refresh first. Combined, a diff of `models.py` would mix schema-driven content changes with path-driven import changes, and neither would be reviewable. Refreshing first also exercises the new derivation logic against a real schema change before the move adds noise.

This implies the derivation fix (Req 3) lands before the refresh, so the refresh is the first thing validated by it.

## Components and Interfaces

Four components change. Everything else in the package is touched only by import-path rewrites.

### Post_Processor — `scripts/postprocess_models.py`

| Surface | Shape | Notes |
|---|---|---|
| CLI `--schema` | path, `default=` Active_Schema_Bundle schema path | Resolved independently of `--models` (Req 2.2, 2.3) |
| CLI `--models` | path, `default=` Version_Package models path | Resolved independently of `--schema` (Req 2.1, 2.3) |
| Derivation function | generated model source → Document_Rename_Map | Per Wrapper_Class: take the single non-`field_schema` field name, PascalCase, append `Document` (Req 3.1–3.3) |
| Ambiguity guard | first offending Wrapper_Class → exit 1 | Fail-fast; remaining candidates unscanned (Req 3.5) |
| Count guard | derived count vs. schema document-type count → exit 1 | Reports both counts (Req 3.6) |
| Collision guard | accumulated uncovered collisions → exit 1 | Runs to completion first (Req 7.3) |

`MODELS_PATH` and `SCHEMA_PATH` stop being module constants and become argparse defaults. Phases 1, 3, 4 and 5 keep their existing behavior; only Phase 2's map construction and the added guards are new.

### Version_Package — `oscal_bindings.v1`

`v1/__init__.py` carries the Public_Surface: the same `__all__` as the pre-move top level, populated by re-exporting from `v1.parser`, `v1.extensions`, and `from .models import *`, plus one new symbol:

| Symbol | Type | Source |
|---|---|---|
| `__oscal_schema_version__` | `str` | The Active_Schema_Bundle release, e.g. `"1.2.3"` (Req 6.1, 6.2) |

### Compat_Shim — top-level `oscal_bindings`

`oscal_bindings/__init__.py` defines no symbols of its own (Req 5.2). It re-exports the Version_Package surface, star-imports `oscal_bindings.v1.models` to preserve direct model-name imports (Req 5.4), and re-exports `__oscal_schema_version__` (Req 6.4). Three explicit alias modules keep the legacy module paths resolving (Req 5.5):

| Legacy path | Re-exports from |
|---|---|
| `oscal_bindings/models.py` | `oscal_bindings.v1.models` |
| `oscal_bindings/parser.py` | `oscal_bindings.v1.parser` |
| `oscal_bindings/extensions/__init__.py` | `oscal_bindings.v1.extensions` |

Re-export rather than `sys.modules` aliasing, so the bound objects are identical and type identity holds across both paths (Req 5.3, 5.6).

### Generate_Script

`generate` passes the Active_Schema_Bundle path and the Version_Package models path explicitly to both `datamodel-codegen` and the Post_Processor (Req 1.5). Codegen flags are otherwise unchanged.

### Unchanged interfaces

The interfaces of `parser.py`, `extensions/document.py`, `extensions/builders.py`, and `extensions/validate_element.py` are **unchanged** — same function names, same signatures, same return types, same exceptions. Only their import paths move. This is load-bearing: it is what makes the Compat_Shim a pure re-export and Req 5 satisfiable without adaptation code. Any change to these signatures would be out of scope for this feature.

## Data Models

**No OSCAL model class is changed by this design.** `extra='forbid'` stays on all of them (Req 10.3), field sets and aliases are untouched, and the only model *content* change in this work comes from regenerating against the 1.2.3 schema (Req 7) — not from the relocation or the derivation fix.

What this feature does introduce are three small build-time structures plus one runtime constant.

### Document_Rename_Map

| Aspect | Value |
|---|---|
| Shape | `dict[str, str]` — generated wrapper class name → published name |
| Before | Hardcoded positional literal (`"Model1" → "CatalogDocument"`, …) |
| After | Derived at post-process time from the generated source |
| Cardinality | Eight entries against the Active_Schema_Bundle (Req 3.7) |

### Root_Key → published-name derivation rule

`snake_case` Root_Key → PascalCase → `+ "Document"`. `catalog` → `CatalogDocument`; `plan_of_action_and_milestones` → `PlanOfActionAndMilestonesDocument`. The eight verified derivations are tabulated in "The positional rename bug" above and are not repeated here.

### Wrapper_Class shape (the derivation's precondition)

| Field | Role |
|---|---|
| `field_schema` (alias `$schema`) | Directive field — excluded from derivation |
| exactly one body field | The Root_Key — the derivation signal (Req 3.2) |

Any Wrapper_Class with more than one body field violates this shape and triggers the ambiguity guard rather than being guessed at.

### Schema_Version_Constant

| Aspect | Value |
|---|---|
| Name | `__oscal_schema_version__` |
| Location | `oscal_bindings.v1`, re-exported by the Compat_Shim |
| Type | `str`, major.minor.patch (Req 6.2) |
| Source of truth | The release element of the Active_Schema_Bundle schema `$id` (Req 6.3) |

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Derivation is position-independent

*For any* generated model source containing a set of Wrapper_Classes, permuting the ordinal suffixes of those class names leaves the derived Document_Rename_Map's set of published names unchanged.

**Validates: Requirements 3.4**

### Property 2: Derivation parity with the positional map

*For all* eight Wrapper_Classes in the Active_Schema_Bundle output, the derived published name equals the name the positional `DOCUMENT_RENAMES` map produced.

**Validates: Requirements 3.7**

### Property 3: Published surface is preserved by the move

*For all* names in the pre-move top-level `__all__`, that name appears in the Version_Package `__all__`, and the two sets are equal in both directions.

**Validates: Requirements 4.4**

### Property 4: Type identity across the Compat_Shim

*For any* name in the Public_Surface, the object reached through the Compat_Shim is the *same object* as the one reached directly through the Version_Package, so `isinstance` gives the same answer regardless of which path the class was obtained through.

**Validates: Requirements 5.3, 5.6**

### Property 5: Version-constant consistency

*For any* Active_Schema_Bundle, the Schema_Version_Constant equals the release version parsed out of that bundle's schema `$id`.

**Validates: Requirements 6.3**

### Property 6: Namespace stability across 1.x

*For any* Active_Schema_Bundle within OSCAL 1.x, the Version_Package name is unchanged — it carries a major component only, so no minor or patch bump can perturb it.

**Validates: Requirements 4.6**

### Property 7: All uncovered collisions are reported

*For any* generated source introducing k uncovered class-name collisions, the Post_Processor exits non-zero and its single report names all k of them.

**Validates: Requirements 7.3**

## Error Handling

All failure modes introduced by this feature are **build-time/codegen** failures in the Post_Processor. The library's runtime error contract is unchanged: `OscalParseError` and `OscalAccessError` keep their existing triggers, messages, and call sites.

Governing principle, already stated in the design decisions: the Post_Processor exits non-zero and loudly rather than writing questionable output. Silent mis-renaming is precisely the failure class this feature eliminates, so a hard stop is the feature, not a rough edge.

| Trigger | Exit behavior | Message must identify | Req |
|---|---|---|---|
| Supplied `--schema` or `--models` path does not exist | Exit non-zero before any processing | The missing path, as supplied | 2.4 |
| A candidate Wrapper_Class has more than one body field besides `$schema` | Exit non-zero **immediately**; remaining candidates left unscanned | The first offending class | 3.5 |
| Derived Wrapper_Class count ≠ document-type count in the Active_Schema_Bundle | Exit non-zero after derivation | Both counts | 3.6 |
| Class-name collisions not covered by `COLLISION_OVERRIDES` | Complete all wrappers, accumulate, then exit non-zero | Every accumulated collision, complete list | 7.3 |

The asymmetry between the second and fourth rows — fail-fast versus accumulate-all — is deliberate and argued in "Why the two guards differ" above.

In every case `models.py` is left in whatever state the failing phase found it; the guards prevent *committing* wrong names, and the remedy is to fix the schema or the overrides and regenerate.

## Testing Strategy

| Requirement | Verification |
|---|---|
| 2.3 independent defaults | Invoke the post-processor four ways — both args, `--schema` only, `--models` only, neither — and assert each omitted argument resolves to its own default regardless of the other. |
| 3.1–3.4 derivation | Unit-test the derivation against a synthetic generated-source fixture with deliberately shuffled ordinals; assert names track content, not position. |
| 3.5 ambiguity guard (fail-fast) | Fixture with two ambiguous wrappers; assert non-zero exit, that the message names the *first* one, and that the second is absent from the report — i.e. the scan stopped rather than continuing. |
| 3.6 count-mismatch guard | Fixture whose derived wrapper count differs from the schema's document-type count; assert non-zero exit and that both counts appear in the message. |
| 3.7 parity | Run derivation against the real Active_Schema_Bundle output; assert the eight names equal the current positional map's output. This is the regression gate for the whole fix. |
| 4.4 surface parity | Snapshot the pre-move top-level `__all__`; assert the Version_Package exposes the same set. |
| 5.1–5.5 back-compat | Import every pre-move public name from `oscal_bindings`, and import each of the three legacy module paths. |
| 5.6 type identity | Assert `oscal_bindings.Catalog is oscal_bindings.v1.models.Catalog`. |
| 6.1–6.3 version constant | Assert the constant is present, semver-shaped, and equals the release parsed out of the schema `$id`. |
| 7.2 refresh | Existing suite passes post-refresh with all eight wrappers intact. |
| 7.3 collision guard (accumulate-all) | Fixture introducing several uncovered collisions in one run; assert non-zero exit and that *every* collision is named in the single report, not just the first. |
| 9.1 matrix | Full `hatch test --all` on 3.11 + 3.12. |

The existing `tests/test_oscal_bindings.py` import smoke test is the natural home for the back-compat assertions.

## Risks

| Risk | Mitigation |
|---|---|
| 1.2.3 introduces new name collisions the overrides do not cover | Req 7.3 guard hard-stops rather than emitting duplicate class definitions, and reports *all* uncovered collisions from a single run so they can be added to `COLLISION_OVERRIDES` in one pass. |
| Derivation parity gate fails because the current positional map is *already* subtly wrong | That would be a find, not a blocker. Investigate before assuming the new logic is at fault. |
| `pdoc`/`mypy` behave oddly across the alias modules | Explicit alias modules chosen partly for this reason. Reqs 9.3 and 9.5 verify both tools directly. |
| Star-import shim masks a name that moved | Req 4.4's snapshot comparison catches surface drift in either direction. |
