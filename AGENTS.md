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
    _base.py           # OscalBaseModel — hand-written base of every generated object
                       # model (alias keys, no nulls, by-name constructor kwargs)
    models.py          # GENERATED Pydantic models — DO NOT hand-edit
    parser.py          # parse_oscal / parse_oscal_file / serialize_oscal /
                       # validate_oscal + 8 typed parse_* functions; OscalParseError
    extensions/        # Hand-written helpers layered on generated models
      __init__.py      # Re-exports extension symbols
      document.py      # OscalDoc facade (uniform metadata/uuid/oscal_version/body;
                       # assessment_period() for AP/AR); OscalAccessError
      builders.py      # make_hash / make_rlink / make_resource (back-matter)
      validate_element.py # validate_element / get_supported_element_types
scripts/               # Not a package: scripts import siblings by plain name
  spec_artifact.py     # Pin (version + sha256) of the spec artifact; shared by generate + tests.
                       # The artifact supplies the OSCAL schema, names.json, and the corpus
  pinned_archive.py    # Locked, sha256-checked fetch + safe extraction of a pinned .tar.gz
  manifest.py          # Validates names.json of the pinned artifact (jsonschema-rs + rules)
  hoist_names.py       # Writes build/codegen/oscal_complete_schema.json: each manifest
                       # site becomes definitions/<CanonicalName>
  postprocess_models.py# Structure fixes, adds unions/root models, guards against manifest
tests/                 # One test module per source module + import smoke test
  support/scripts.py   # load_script(): how tests import modules from scripts/
requirements.txt       # Lockfile for the default env (hatch-pip-compile output)
requirements/          # Lockfiles for hatch-test (per Python) and hatch-build
```

**Entry points to read first for a task:** `src/oscal_bindings/v1/__init__.py` (full API surface), then `v1/parser.py` or the relevant `v1/extensions/*.py`. The top-level `__init__.py` only re-exports and tells you nothing about behavior.

<!-- meta: generated-code -->
## Critical Convention: `models.py` is generated

`src/oscal_bindings/v1/models.py` is produced by `datamodel-code-generator` and rewritten by `scripts/postprocess_models.py`. **Never hand-edit it.** To change models, edit the hoist or the post-processor and run `hatch run generate`. The file carries a codegen banner at the top. Every type name is a canonical name from the naming manifest (`names.json`) of the pinned spec artifact: `OscalDocument`, `CatalogDocument`, `BackMatterResourceRlink`, `HashAlgorithm`, `CatalogGroup` (a union `TypeAlias`). The only other module-level names are scalar aliases such as `LocationUuid`. Downstream code uses these names; no deprecated aliases exist. `src/oscal_bindings/models.py` is a one-line alias module over it — not a second copy.

<!-- meta: api-pattern -->
## Public API Pattern

Neither `v1/__init__.py` nor the top-level `__init__.py` defines symbols — both **only re-export**. The public surface is auditable in `v1/__all__`, which the top level reuses verbatim. To add a helper (see [DEVELOPING.md](DEVELOPING.md)):
1. Add `v1/extensions/foo.py`.
2. Re-export its public symbols from `v1/extensions/__init__.py`.
3. Re-export from `src/oscal_bindings/v1/__init__.py`. The top-level path picks it up automatically — no top-level edit needed.
4. Add tests under `tests/`.

<!-- meta: codegen -->
## Code Generation Pipeline

Names come from the store's naming manifest. The binding holds no naming rule for a manifest type. `hatch run generate` runs three steps:

1. **Hoist.** `python scripts/hoist_names.py` fetches the spec artifact pinned in `scripts/spec_artifact.py` (`0.3.0+oscal.1.2.3`, sha256-checked, cached in `tests/.corpus_cache/`), validates its `names.json` with `scripts/manifest.py` (manifest JSON Schema via `jsonschema-rs`, format and release, artifact-schema sha256, unique names, resolvable pointers), reads the complete OSCAL schema of the same artifact one time (the manifest check hashes the bytes that the hoist parses), and writes `build/codegen/oscal_complete_schema.json` (git-ignored). In that copy each manifest site is `definitions/<CanonicalName>` with a `$ref` at the site. A merge with different bodies, or a closed-enum value that its base datatype rejects, fails the run.
2. **Codegen.** `datamodel-codegen --input ./build/codegen/oscal_complete_schema.json --output ./build/codegen/models.py --base-class oscal_bindings.v1._base.OscalBaseModel --collapse-root-models ... --formatters black isort` (see DEVELOPING "Names reach codegen through the hoisted schema" for the flag choices). Each `object`, `document`, and `enum` class takes its name from its definition key. `--base-class` makes all 185 object models subclass `OscalBaseModel`; the two `RootModel`s (`OscalDocument`, `MappingCollectionMappings`) don't.
3. **Post-process.** `python scripts/postprocess_models.py --models ./build/codegen/models.py --output src/oscal_bindings/v1/models.py`. Phase 1 collapses scalar `RootModel`s to `Annotated` aliases and strips `pattern=` from non-string fields (`AwareDatetime`/`AnyUrl`/numeric/`EmailStr`). Then it adds the 13 union `TypeAlias`es (`CatalogGroup`), the `MappingCollectionMappings` root model, and the `OscalDocument` root model, and names each scalar alias from its definition key without the `oscal-complete-oscal-<module>:` prefix. Three guards compare the result with the manifest and the artifact schema and report every offender: each manifest name is defined once in the form of its kind, each other name is a scalar alias named for a scalar definition of the schema, no name is defined twice, and no manifest name or scalar alias is bound by a module-level import. The manifest must record the sha256 of the `--schema` bytes. The completed module goes to `--output` through a temp file + `os.replace`; on a failure nothing is written to `--output`, so a failed `generate` leaves the committed `models.py` untouched. `generate` passes no `--schema`: an omitted `--schema` resolves at call time to `artifact_paths(ensure_spec_artifact()).schema`, and an explicit one (a candidate schema, or a small test schema) must still match `schema.sha256` of the manifest. `--models` falls back to its own default, `--output` defaults to `--models`; a missing path is a non-zero exit.

See `.agents/summary/workflows.md` for the flow diagram.

**The pin is the only selector of the schema.** The repo holds no copy of the OSCAL schema. `SPEC_ARTIFACT_VERSION` and `SPEC_ARTIFACT_SHA256` in `scripts/spec_artifact.py` select the artifact, and the `+oscal.<release>` build metadata of the version selects the release (`OSCAL_RELEASE`). The hoist, the manifest check, the post-processor, and the tests all read `artifact_paths(ensure_spec_artifact()).schema`, resolved at call time and never at import. The hand-written `__oscal_schema_version__` is the one other copy of the release; tests assert that it equals `OSCAL_RELEASE` and that `OSCAL_RELEASE` equals the release in the schema `$id`. To move the pin, follow DEVELOPING.md "Moving the pin to a new spec artifact".

<!-- meta: patterns-gotchas -->
## Repo-Specific Patterns & Gotchas

- **Parsers accept `str | bytes`.** Passing `bytes` (from HTTP/S3/file) skips a UTF-8 decode; `parse_oscal_file` reads bytes deliberately. Invalid UTF-8 surfaces as `OscalParseError`, not `UnicodeDecodeError`.
- **Typed parsers return the wrapper, not the body.** `parse_catalog()` returns `CatalogDocument` (access `.catalog.metadata...`). It `hasattr`-checks `doc.root` and raises `OscalParseError("Document is not a Catalog")` on mismatch.
- **`OscalDoc` collapses per-type dispatch.** Use it when you don't want to branch on document type — `doc.metadata`, `doc.uuid`, `doc.oscal_version`, `doc.body` work uniformly via the `_WRAPPER_TO_BODY_ATTR` map. `assessment_period()` is defined **only** for Assessment Plan / Assessment Results (raises `OscalAccessError` otherwise).
- **Valid OSCAL by default; construct by name, validate by alias.** `OscalBaseModel` (`v1/_base.py`) gives every object model alias keys (`media-type`, `document-ids`) and no `null` on all serialization paths (`model_dump*`, `to_json`, `TypeAdapter`); `exclude_none=False` is a no-op, `by_alias=False` emits names. Constructor kwargs accept field names or aliases (`BackMatterResourceRlink(media_type=...)`), so the builders construct directly. OSCAL input stays alias-only: dict input rejects name keys with `extra_forbidden` at every depth (`extra='forbid'`). **Don't add `validate_by_name`/`populate_by_name` to the base config**, and don't remove `__pydantic_base_init__` from its `__init__`: either makes `model_validate*` accept name-keyed OSCAL (DEVELOPING "Valid OSCAL by default"; tripwire tests guard both). Known upstream gap: on pydantic 2.13.x JSON input silently **drops** a name key instead of rejecting it (2.11.0 rejects); tracked in [#6](https://github.com/cairn-proofs/oscal-bindings-python/issues/6).
- **`validate_element` type names are derived from model class names** (PascalCase → kebab-case, introspected at import), so they follow the manifest names (`back-matter-resource-rlink`). Use `get_supported_element_types()` for the live list; unknown types raise `OscalParseError`. `tests/support/element_types_snapshot.txt` pins the list.
- **Closed enums are `Enum` classes.** A closed-enum field holds its enum class (`ParameterSelectionHowMany`) and rejects any other value. An open-enum field is the union of its base datatype alias and its enum class.
- **Major-version namespace, single active release.** The implementation lives in `oscal_bindings.v1` — named for the OSCAL **major** version, no minor/patch component — and is generated from exactly one OSCAL release at a time, the release of the spec artifact pin (`__oscal_schema_version__`, currently `1.2.3`). A 1.x refresh regenerates `v1` in place; only OSCAL 2.0 justifies a second version package. Minor-version namespacing (`v1_2`) was considered and rejected — read the "Major-version namespace" and "Strict models" entries under Key Design Decisions in `DEVELOPING.md` before proposing either.
- **Top level re-exports; it is not the implementation.** `oscal_bindings/__init__.py` plus the alias modules `oscal_bindings/models.py`, `parser.py`, `extensions/__init__.py` are pure re-exports of their `v1` counterparts (explicit modules, not `sys.modules` tricks). Edit the `v1` copies; the top level takes its `__all__` from `oscal_bindings.v1.__all__`, so the surfaces can't drift. Names reached through either path are the same objects.
- **Names come only from `names.json`.** To change a type name, change the manifest in the store (`cairn-proofs/oscal-bindings-specs`), release a new spec artifact, and move the pin in `scripts/spec_artifact.py`. Never rename a manifest type in the post-processor or in the hoist; the guards fail on any class name outside the manifest. Scalar alias names are binding names, not contract names.
- **Scripts share one pin and one cache.** `scripts/spec_artifact.py` is the only pin of the spec artifact; `tests/support/spec_artifact.py` reads it. Tests import script modules through `tests/support/scripts.py` (`load_script`), not via `sys.path` hacks of their own.
- **Extensions are never injected into generated code.** Convenience layers live in `extensions/` so the codegen output stays a pristine generate + post-process pass.

<!-- meta: config-facts -->
## Config-Derived Facts

- **Build/tooling is Hatch-based** (`hatchling` backend). Non-obvious scripts (from `pyproject.toml`): `hatch run generate` (regenerate models), `hatch run release` (generate + lint + typing + security + `hatch test --all --cover` + docs), `hatch run security` (bandit over `src`/`scripts` + pip-audit (OSV) over every committed lockfile, run in the detached `security` env), `hatch run docs` (pdoc over `oscal_bindings` **and** `oscal_bindings.v1` → `build/api-docs`), `hatch run typing` (mypy over `src/oscal_bindings`, which includes `v1`). Test matrix is Python 3.11–3.14, parallel.
- **Requires Python ≥3.11**; codegen, ruff (`target-version`), and mypy (`[tool.mypy] python_version`) all target 3.11, the floor, not the toolchain. Local toolchain (Python 3.14, uv, Hatch) pinned via `mise.toml`/`mise.lock`; the `default` and `security` hatch envs also run on 3.14. Changing an env's Python doesn't recreate or re-lock it; see DEVELOPING.md "Locked Environments".
- **Every Hatch env is locked.** `type = "pip-compile"` (uv resolver/installer, hashes) on `default` → `requirements.txt`, `hatch-test` → `requirements/requirements-hatch-test.py3.{11,12,13,14}.txt` (constrained by `default`), `hatch-build` → `requirements/requirements-hatch-build.txt`, `security` → `requirements/requirements-security.txt` (detached, unconstrained; kept out of `default` so the scanners' deps don't leak into `hatch-test`). The `[build-system]` backend is exact-pinned. There is no `uv.lock`; don't add one (two lock systems drift). Commit lockfile changes alongside dependency changes. `hatch run lock` re-locks every stale env (no upgrades); `hatch run upgrade` re-resolves all of them to the newest allowed versions, `default` first. Neither moves exact `==` pins. The `lock` script names each env explicitly (including each `hatch-test.py3.X`; plain `hatch-test` isn't a runnable env name), so update it, and the lockfile list in `security:scan-deps`, when the matrix or env set changes. See DEVELOPING.md "Locked Environments".
- **`jsonschema-rs` is in both `default` and `hatch-test`** at the same version (`==0.58.6` in `default`, which constrains `hatch-test`). `generate` uses it to validate the manifest; tests use it to validate serialized output and the hoisted schema.
- **`hatch run generate` needs the network on a cold cache.** It downloads the pinned spec artifact into `tests/.corpus_cache/`, the cache that `hatch test` uses for the schema and the corpus, so one download serves both. An sdist checkout needs the network too: the sdist ships `models.py` but not the schema.
- **`pytest` is not in the default env** on purpose: Hatch's built-in `hatch-test` pins its own pytest range, and listing pytest in `default` makes the constrained resolve fail.
- **Coverage HTML** (`htmlcov/`) comes from the overridden `cov-report` script in `[tool.hatch.envs.hatch-test.scripts]`. That table replaces Hatch's built-in scripts wholesale, so it must restate `run`, `run-cov`, and `cov-combine`. Only `hatch test --cover` writes it. It is git-ignored; don't commit it. No JUnit or Cobertura XML is produced.
- **Hatch comes from mise, locally and in CI.** `mise.toml` pins Python, uv, and `"pypi:hatch"` (with `hatch-pip-compile` injected via `with`). `mise.lock` plus the `.mise/locks/` sidecar record the full hashed dependency graph, and CI's `jdx/mise-action` installs with `--locked`. Don't install Hatch via pip/pipx/brew: a bare `hatch==X` pin let `virtualenv` float to 21.x and broke Hatch 1.15, and a second Hatch on the machine is a trap. The standalone `github:pypa/hatch` binary was also rejected: 1.18.1's PyApp build can't install env plugins (pypa/hatch#2390, fixed after 1.18.1). Bumping Hatch changes the `hatch-test` lockfiles (Hatch supplies that env's pytest/coverage ranges), so re-lock and commit them together.
- **CI triggers:** once per PR update (on the trial merge into `main`), pushes to `main`, and `v*` tags. Branches without a PR run only via `workflow_dispatch`. Keep `tags: ["v*"]` under `push`: with a `branches` filter, tags don't trigger unless listed. `main` is branch-protected and requires the `build` check.
- **CI** (`.github/workflows/build.yml`) runs `hatch run release`, then the drift check `git diff --exit-code -- src/oscal_bindings/v1/models.py` (the committed `models.py` must be what the pin generates), then `hatch build`, and uploads `api-docs`, `coverage-html`, and `python-packages` (wheel + sdist) artifacts. On a `v*` tag push it first checks that the tagged commit is on `main` (`git merge-base --is-ancestor`) and that the tag equals `v$(hatch version)`, and a `draft-release` job attaches the `python-packages` artifact to a **draft** GitHub release. Publishing the draft (manual) triggers `release.yml`, which downloads those assets, verifies their filenames match the tag, and uploads them to PyPI via trusted publishing. **Nothing rebuilds after CI**: PyPI gets the exact files CI tested. Release flow: bump `version` in `pyproject.toml`, commit, push tag `v<version>`, review the draft, publish.
- **CodeQL** (`.github/workflows/codeql.yml`) is separate from CI: `python` + `actions` languages, `security-extended` queries, `build-mode: none`, on PR/main plus a weekly schedule. It holds `security-events: write`, which is why it isn't a job in `build.yml`. It's not a Hatch task and doesn't gate `release`.
- **Runtime dependency is only `pydantic[email]>=2.0`;** `datamodel-code-generator[http,black,isort]` is a dev/codegen-only extra, exact-pinned in two places (`[project.optional-dependencies].codegen` and the default env) that must move together. `generate` passes `--formatters black isort` explicitly: that's the output format `models.py` is committed in, and it keeps upstream's planned switch to a builtin formatter from reformatting the file.

<!-- meta: deeper-docs -->
## Deeper Documentation

A detailed knowledge base lives in `.agents/summary/`. Start with `index.md`, which routes to:

| File | For questions about |
|------|---------------------|
| `codebase_info.md` | Stack, layout, structure map |
| `architecture.md` | Layering, design patterns, codegen architecture |
| `components.md` | Per-file responsibilities and symbols |
| `interfaces.md` | Public API signatures, error contract, sequences |
| `data_models.md` | Document types, wrapper→body map, naming manifest, enums |
| `workflows.md` | Codegen, parse, facade, builder, validation, release flows |
| `dependencies.md` | External deps, toolchain, version support |
| `review_notes.md` | Consistency/completeness audit |

## Custom Instructions
<!-- This section is for human and agent-maintained operational knowledge.
     Add repo-specific conventions, gotchas, and workflow rules here.
     This section is preserved exactly as-is when re-running codebase-summary. -->
