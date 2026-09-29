# AGENTS.md

Navigation guide for AI agents working in **oscal-bindings** — typed Python data bindings for OSCAL (Open Security Controls Assessment Language) v1.2.3, generated from the NIST JSON Schema with Pydantic v2.

## Table of Contents

- [Orientation](#orientation) — what this repo is, in one screen
- [Directory & Component Map](#directory--component-map) — where code lives
- [Critical Convention: `models.py` is generated](#critical-convention-modelspy-is-generated) — the #1 gotcha
- [Public API Pattern](#public-api-pattern) — re-export-only packaging
- [Code Generation Pipeline](#code-generation-pipeline) — schema → models
- [Repo-Specific Patterns & Gotchas](#repo-specific-patterns--gotchas)
- [Config-Derived Facts](#config-derived-facts) — things only visible in config files
- [Deeper Documentation](#deeper-documentation) — the `.agents/summary/` knowledge base
- [Custom Instructions](#custom-instructions) — human/agent-maintained

<!-- meta: orientation -->
## Orientation

A **data-binding library** (no server, no persistence). It converts OSCAL JSON ⇄ typed Python objects and adds convenience layers. The implementation lives in `oscal_bindings.v1`; the top-level `oscal_bindings` package re-exports it, so both import paths resolve to the same objects. Only runtime dependency is Pydantic v2. Supports all 8 OSCAL document types: Catalog, Profile, Component Definition, System Security Plan, Assessment Plan, Assessment Results, Plan of Action and Milestones, Mapping Collection.

<!-- meta: directory-map -->
## Directory & Component Map

```
src/oscal_bindings/
  __init__.py          # Re-exports oscal_bindings.v1, defines nothing
  models.py            # Alias module → v1.models
  parser.py            # Alias module → v1.parser
  extensions/
    __init__.py        # Alias module → v1.extensions
  v1/                  # OSCAL 1.x Version Package — the implementation lives here
    __init__.py        # Public API — RE-EXPORTS ONLY + __oscal_schema_version__
    models.py          # GENERATED Pydantic models — DO NOT hand-edit
    parser.py          # parse_oscal / parse_oscal_file / serialize_oscal /
                       # validate_oscal + 8 typed parse_* functions; OscalParseError
    extensions/        # Hand-written helpers layered on generated models
      __init__.py      # Re-exports extension symbols
      document.py      # OscalDoc facade (uniform metadata/uuid/oscal_version/body;
                       # assessment_period() for AP/AR); OscalAccessError
      builders.py      # make_hash / make_rlink / make_resource (back-matter)
      validate_element.py # validate_element / get_supported_element_types
scripts/
  postprocess_models.py# Renames + cleans up datamodel-codegen output
schemas/<release>/     # Release-versioned OSCAL JSON Schema bundles (codegen INPUT);
                       # oscal_complete_schema.json in the active release is the one used
tests/                 # One test module per source module + import smoke test
requirements.txt       # Lockfile for the default env (hatch-pip-compile output)
requirements/          # Lockfiles for hatch-test (per Python) and hatch-build
```

**Entry points to read first for a task:** `src/oscal_bindings/v1/__init__.py` (full API surface), then `v1/parser.py` or the relevant `v1/extensions/*.py`. The top-level `__init__.py` only re-exports and tells you nothing about behavior.

<!-- meta: generated-code -->
## Critical Convention: `models.py` is generated

`src/oscal_bindings/v1/models.py` is produced by `datamodel-code-generator` and rewritten by `scripts/postprocess_models.py`. **Never hand-edit it.** To change models, edit the schema or the post-processor and run `hatch run generate`. The file carries a codegen banner at the top. Downstream code must use the post-processed names (`OscalDocument`, `CatalogDocument`, …), never raw generator names (`Model`, `Model1..8`, `OscalComplete*`). `src/oscal_bindings/models.py` is a one-line alias module over it — not a second copy.

<!-- meta: api-pattern -->
## Public API Pattern

Neither `v1/__init__.py` nor the top-level `__init__.py` defines symbols — both **only re-export**. The public surface is auditable in `v1/__all__`, which the top level reuses verbatim. To add a helper (see [DEVELOPING.md](DEVELOPING.md)):
1. Add `v1/extensions/foo.py`.
2. Re-export its public symbols from `v1/extensions/__init__.py`.
3. Re-export from `src/oscal_bindings/v1/__init__.py`. The top-level path picks it up automatically — no top-level edit needed.
4. Add tests under `tests/`.

<!-- meta: codegen -->
## Code Generation Pipeline

`hatch run generate` runs `datamodel-codegen --input ./schemas/<release>/oscal_complete_schema.json --output src/oscal_bindings/v1/models.py ... && python scripts/postprocess_models.py --schema <same> --models <same>`. Both paths are explicit arguments; the post-processor's `--schema`/`--models` each fall back to their own default independently when omitted, and a missing path is a non-zero exit.

The post-processor (in order): collapses scalar `RootModel`s to `TypeAlias`es (keeping `PRESERVE_AS_ROOTMODEL = {Model, Mappings}`), strips `pattern=` from non-string fields (`AwareDatetime`/`AnyUrl`/numeric/`EmailStr`), renames wrapper classes to `*Document` using a map **derived from the generated source** (`derive_document_renames` reads each wrapper's single body field, excluding `field_schema`, and publishes `<RootKey→PascalCase>Document`), renames `Model` → `OscalDocument`, applies `VARIANT_RENAMES` and namespace-prefix stripping, and resolves cross-type name collisions via `COLLISION_OVERRIDES` (e.g. `SspControlImplementation` vs `ComponentDefinitionControlImplementation`). Three guards abort the run: an ambiguous wrapper (fails fast on the first offender), a derived-vs-schema wrapper count mismatch, and any duplicate `class <Name>(` left after renaming (accumulates all collisions into one report). See `.agents/summary/workflows.md` for the full phase list.

**Active bundle selection is by explicit path only** — `ACTIVE_SCHEMA_RELEASE` in the post-processor plus the `generate` script's paths. Nothing scans or globs `schemas/`, so adding a bundle directory changes nothing on its own.

<!-- meta: patterns-gotchas -->
## Repo-Specific Patterns & Gotchas

- **Parsers accept `str | bytes`.** Passing `bytes` (from HTTP/S3/file) skips a UTF-8 decode; `parse_oscal_file` reads bytes deliberately. Invalid UTF-8 surfaces as `OscalParseError`, not `UnicodeDecodeError`.
- **Typed parsers return the wrapper, not the body.** `parse_catalog()` returns `CatalogDocument` (access `.catalog.metadata...`). It `hasattr`-checks `doc.root` and raises `OscalParseError("Document is not a Catalog")` on mismatch.
- **`OscalDoc` collapses per-type dispatch.** Use it when you don't want to branch on document type — `doc.metadata`, `doc.uuid`, `doc.oscal_version`, `doc.body` work uniformly via the `_WRAPPER_TO_BODY_ATTR` map. `assessment_period()` is defined **only** for Assessment Plan / Assessment Results (raises `OscalAccessError` otherwise).
- **Models forbid extras and don't populate-by-name.** JSON aliases are kebab/camelCase (`media-type`, `oscal-version`, `document-ids`). `make_rlink` therefore builds via `Rlink.model_validate({"media-type": ...})`, and `make_resource` sets `document_ids` **post-construction** (the alias + `extra='forbid'` block passing it as a kwarg).
- **`validate_element` type names are derived from model class names** (PascalCase → kebab-case, introspected at import). Use `get_supported_element_types()` for the live list; unknown types raise `OscalParseError`.
- **Major-version namespace, single active release.** The implementation lives in `oscal_bindings.v1` — named for the OSCAL **major** version, no minor/patch component — and is generated from exactly one vendored release at a time (`__oscal_schema_version__`, currently `1.2.3`). A 1.x refresh regenerates `v1` in place; only OSCAL 2.0 justifies a second version package. Minor-version namespacing (`v1_2`) was considered and rejected — read the "Major-version namespace" and "Strict models" entries under Key Design Decisions in `DEVELOPING.md` before proposing either.
- **Top level re-exports; it is not the implementation.** `oscal_bindings/__init__.py` plus the alias modules `oscal_bindings/models.py`, `parser.py`, `extensions/__init__.py` are pure re-exports of their `v1` counterparts (explicit modules, not `sys.modules` tricks). Edit the `v1` copies; the top level takes its `__all__` from `oscal_bindings.v1.__all__`, so the surfaces can't drift. Names reached through either path are the same objects.
- **The wrapper rename map is schema-derived, not positional.** Don't key renames on the generator's `Model1..8` ordinals. `POSITIONAL_DOCUMENT_RENAMES_SNAPSHOT` in the post-processor is a frozen parity expectation for tests, not a live map.
- **Extensions are never injected into generated code.** Convenience layers live in `extensions/` so the codegen output stays a pristine generate + rename pass.

<!-- meta: config-facts -->
## Config-Derived Facts

- **Build/tooling is Hatch-based** (`hatchling` backend). Non-obvious scripts (from `pyproject.toml`): `hatch run generate` (regenerate models), `hatch run release` (generate + `hatch test --all --cover` + docs), `hatch run docs` (pdoc over `oscal_bindings` **and** `oscal_bindings.v1` → `build/api-docs`), `hatch run typing` (mypy over `src/oscal_bindings`, which includes `v1`). Test matrix is Python 3.11 + 3.12, parallel.
- **Requires Python ≥3.11**; codegen targets 3.11 syntax. Local toolchain (Python 3.12, uv, Hatch) pinned via `mise.toml`/`mise.lock`; the default hatch env also targets 3.12.
- **Every Hatch env is locked.** `type = "pip-compile"` (uv resolver/installer, hashes) on `default` → `requirements.txt`, `hatch-test` → `requirements/requirements-hatch-test.py3.{11,12}.txt` (constrained by `default`), `hatch-build` → `requirements/requirements-hatch-build.txt`. The `[build-system]` backend is exact-pinned. There is no `uv.lock`; don't add one (two lock systems drift). Commit lockfile changes alongside dependency changes; see DEVELOPING.md "Locked Environments".
- **`pytest` is not in the default env** on purpose: Hatch's built-in `hatch-test` pins its own pytest range, and listing pytest in `default` makes the constrained resolve fail.
- **Coverage HTML** (`htmlcov/`) comes from the overridden `cov-report` script in `[tool.hatch.envs.hatch-test.scripts]`. That table replaces Hatch's built-in scripts wholesale, so it must restate `run`, `run-cov`, and `cov-combine`. Only `hatch test --cover` writes it. It is git-ignored; don't commit it. No JUnit or Cobertura XML is produced.
- **Hatch comes from mise, locally and in CI.** `mise.toml` pins Python, uv, and `"pypi:hatch"` (with `hatch-pip-compile` injected via `with`). `mise.lock` plus the `.mise/locks/` sidecar record the full hashed dependency graph, and CI's `jdx/mise-action` installs with `--locked`. Don't install Hatch via pip/pipx/brew: a bare `hatch==X` pin let `virtualenv` float to 21.x and broke Hatch 1.15, and a second Hatch on the machine is a trap. The standalone `github:pypa/hatch` binary was also rejected: 1.18.1's PyApp build can't install env plugins (pypa/hatch#2390, fixed after 1.18.1). Bumping Hatch changes the `hatch-test` lockfiles (Hatch supplies that env's pytest/coverage ranges), so re-lock and commit them together.
- **CI** (`.github/workflows/build.yml`) runs `hatch run release`, then `hatch build`, and uploads `api-docs`, `coverage-html`, and `python-packages` (wheel + sdist) artifacts. On a `v*` tag push it first checks the tag equals `v$(hatch version)`, and a `draft-release` job attaches the `python-packages` artifact to a **draft** GitHub release. Publishing the draft (manual) triggers `release.yml`, which downloads those assets, verifies their filenames match the tag, and uploads them to PyPI via trusted publishing. **Nothing rebuilds after CI**: PyPI gets the exact files CI tested. Release flow: bump `version` in `pyproject.toml`, commit, push tag `v<version>`, review the draft, publish.
- **Runtime dependency is only `pydantic[email]>=2.0`;** `datamodel-code-generator[http]` is a dev/codegen-only extra.

<!-- meta: deeper-docs -->
## Deeper Documentation

A detailed knowledge base lives in `.agents/summary/`. Start with `index.md`, which routes to:

| File | For questions about |
|------|---------------------|
| `codebase_info.md` | Stack, layout, structure map |
| `architecture.md` | Layering, design patterns, codegen architecture |
| `components.md` | Per-file responsibilities and symbols |
| `interfaces.md` | Public API signatures, error contract, sequences |
| `data_models.md` | Document types, wrapper→body map, naming/collisions |
| `workflows.md` | Codegen, parse, facade, builder, validation, release flows |
| `dependencies.md` | External deps, toolchain, version support |
| `review_notes.md` | Consistency/completeness audit |

## Custom Instructions
<!-- This section is for human and agent-maintained operational knowledge.
     Add repo-specific conventions, gotchas, and workflow rules here.
     This section is preserved exactly as-is when re-running codebase-summary. -->
