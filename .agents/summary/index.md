# Knowledge Base Index — oscal-bindings

> **For AI assistants:** This file is the primary entry point for understanding the `oscal-bindings` codebase. Load it first. Each entry below summarizes a companion document and tells you when to open it. In most cases you can answer from this index plus one targeted document — you rarely need to read source files directly, though the cited source paths are authoritative when you do.

## How to Use This Knowledge Base

1. Read this index to understand the codebase shape and locate the right document.
2. Open the specific document that matches the question domain (see routing table).
3. Only open source files when you need exact current signatures or the answer isn't in the docs. `src/oscal_bindings/v1/__init__.py` is the authoritative public-API list; `src/oscal_bindings/v1/models.py` is GENERATED (do not edit).

## What This Codebase Is

Typed Python data bindings for **OSCAL** (Open Security Controls Assessment Language), currently generated from release **1.2.3**. Pydantic v2 models are **generated** from the NIST JSON Schema and post-processed for clean names; a runtime layer adds parse/serialize/validate; a hand-written `extensions/` package adds a uniform facade, back-matter builders, and element validation. Single runtime dependency: Pydantic v2.

The implementation lives in the major-version package **`oscal_bindings.v1`**; the top-level `oscal_bindings` re-exports it, so both `from oscal_bindings.v1 import ...` (preferred) and the flat `from oscal_bindings import ...` work and yield the same objects.

## Document Routing Table

| Document | Read it when you need… | Key contents |
|----------|------------------------|--------------|
| **codebase_info.md** | High-level orientation: stack, layout, languages | Directory tree, tech stack table, structure Mermaid map, design principles, testing setup |
| **architecture.md** | The "why" and layering; design patterns; codegen architecture | Layered diagram, Facade/Adapter/generated-code patterns, post-processor phases, architectural decision table |
| **components.md** | What each source file does and its public symbols | Per-file responsibilities for `v1/models.py`, `v1/parser.py`, the 3 extensions, the version-package surface, the top-level re-exports, the post-processor, tests |
| **interfaces.md** | The public API, signatures, error contract | Full symbol list, function signatures, interaction sequence diagrams, error-handling table, codegen contract |
| **data_models.md** | Model structure, wrappers vs bodies, naming/collisions | Document-type class diagram, wrapper→body map, shared elements, conventions, collision overrides, enums |
| **workflows.md** | Step-by-step processes (build & runtime) | Codegen flow + post-processor phases, parse flow, `OscalDoc`/`assessment_period` flows, builder & validation flows, dev/release workflow |
| **dependencies.md** | External deps and toolchain, version support | Runtime (Pydantic only), codegen extra, dev tools, Python version matrix, risk notes |
| **review_notes.md** | Consistency/completeness audit of these docs | Findings, gaps, recommendations |

## Question → Document Cheat Sheet

- "Which import path should I use — `oscal_bindings` or `oscal_bindings.v1`?" → **architecture.md** (version package + top-level re-exports) + **interfaces.md**
- "Which OSCAL release are the bindings generated from / how do I refresh it?" → **workflows.md** (codegen + schema refresh) + `DEVELOPING.md`
- "How do I parse / serialize / validate an OSCAL document?" → **interfaces.md**, then **workflows.md** (parse flow)
- "What does `OscalDoc` do / how does `assessment_period()` work?" → **components.md** + **workflows.md**
- "How are the models generated? Why is `v1/models.py` huge / not to be edited?" → **architecture.md** + **workflows.md** (codegen)
- "Why are there names like `SspControlImplementation`?" → **data_models.md** (collision handling)
- "What are the document types and their body fields?" → **data_models.md** (wrapper→body map)
- "How do I build a back-matter resource / hash / rlink?" → **interfaces.md** (builders) + **workflows.md** (builder flow)
- "What exceptions can be raised and when?" → **interfaces.md** (error-handling table)
- "What does the library depend on / what Python versions?" → **dependencies.md**
- "How do I add a new helper?" → **workflows.md** (adding an extension) / **components.md**
- "How do I run tests / the release pipeline?" → **workflows.md** (dev/release) + `DEVELOPING.md`

## Core Facts (quick reference)

- **8 OSCAL document types:** Catalog, Profile, Component Definition, System Security Plan, Assessment Plan, Assessment Results, Plan of Action and Milestones, Mapping Collection.
- **Layout:** implementation under `src/oscal_bindings/v1/`; top-level package re-exports it through explicit alias modules at `oscal_bindings/models.py`, `oscal_bindings/parser.py`, `oscal_bindings/extensions/__init__.py`.
- **Active schema:** `schemas/1.2.3/oscal_complete_schema.json`. Bundles are vendored one directory per OSCAL release (`schemas/1.2.2/` is retained); the active one is selected by the explicitly passed path only — no glob, no "newest wins".
- **`__oscal_schema_version__`** (`"1.2.3"`) on `oscal_bindings.v1`, re-exported at the top level, records the exact release the models came from.
- **Entry points:** `parse_oscal`, `parse_oscal_file`, 8 typed `parse_*` functions, `serialize_oscal`, `validate_oscal`, `OscalDoc`, `make_hash`/`make_rlink`/`make_resource`, `validate_element`/`get_supported_element_types`.
- **Parsers accept `str | bytes`;** bytes skips a UTF-8 decode (useful for HTTP/S3/file byte-sources).
- **`v1/models.py` is GENERATED** by `datamodel-codegen` + `scripts/postprocess_models.py`. Change the schema/post-processor and run `hatch run generate` — never hand-edit. (`oscal_bindings/models.py` at the top level is a hand-written alias module, not generated.)
- **`v1/__init__.py` only re-exports** — the entire public API is visible there; the top level derives its `__all__` from it.
- **Extensions pattern:** new helpers go in `src/oscal_bindings/v1/extensions/`, re-exported up through `v1/extensions/__init__.py` then `v1/__init__.py`.
- **Wrapper rename map is schema-derived**, not positional: each wrapper is found by its `$schema` field and named from its single body field, with guards for ambiguous wrappers, count mismatch against the schema's top-level `oneOf`, and uncovered class-name collisions.
- **Namespaces are major-scoped** (`v1`); minor-version namespacing was considered and rejected on compatibility-boundary grounds. OSCAL 2.0 is the trigger for a second version package (see `DEVELOPING.md` Key Design Decisions).
- **Exceptions:** `OscalParseError` (has `.errors`), `OscalAccessError`.

## Source-of-Truth Files (when docs aren't enough)

| File | Authoritative for |
|------|-------------------|
| `src/oscal_bindings/v1/__init__.py` | The exact public API (`__all__`) + `__oscal_schema_version__` |
| `src/oscal_bindings/__init__.py` | The top-level re-export behavior |
| `src/oscal_bindings/v1/parser.py` | Parser/serializer/validator behavior |
| `src/oscal_bindings/v1/extensions/document.py` | `OscalDoc` facade + `assessment_period()` |
| `src/oscal_bindings/v1/extensions/builders.py` | Back-matter builders |
| `src/oscal_bindings/v1/extensions/validate_element.py` | Element validation |
| `scripts/postprocess_models.py` | Wrapper-name derivation, class renaming, codegen guards |
| `pyproject.toml` | Deps, hatch envs, scripts |
| `DEVELOPING.md` | Dev workflow & design rationale |

## Maintenance

These docs are generated by the `codebase-summary` process. Regenerate them after significant structural changes (new extensions, schema/OSCAL version bumps, changes to the codegen pipeline or public API). The consolidated `AGENTS.md` in the repo root is derived from these files; its `Custom Instructions` section is human-maintained and preserved across regenerations.
