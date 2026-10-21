## Why

The spec store is the authority for the OSCAL schema and the naming manifest (#18). Since #22, `hatch run generate`
reads `names.json` from the pinned, sha256-checked spec artifact. It still reads the schema from the vendored
`schemas/1.2.3/` directory of this repo. That directory is a second copy of a file that the artifact already holds,
byte for byte. The release `1.2.3` is also written in three places: the pin, `ACTIVE_SCHEMA_RELEASE` in the
post-processor, and a literal path in the `generate` script. A test exists only to keep two of them equal. This change
makes the pin the only source of the schema and of the release, and it closes #18.

## What Changes

1. `hatch run generate` reads `schemas/<release>/oscal_complete_schema.json` from the pinned spec artifact. The hoist,
   the manifest check, and the post-processor read the same artifact file.
2. The pin `SPEC_ARTIFACT_VERSION` in `scripts/spec_artifact.py` is the only identifier of the OSCAL release that the
   build uses. `ACTIVE_SCHEMA_RELEASE` and the `--schema` literal of the `generate` script are removed.
3. The manifest check keeps the comparison of `schema.sha256` in `names.json` with the sha256 of the schema bytes that
   codegen reads ([NAM-002]).
4. `__oscal_schema_version__` stays a hand-written string in `src/oscal_bindings/v1/__init__.py`. Tests check that it
   equals the release of the pin, and that the release of the pin equals the release in the `$id` of the artifact
   schema.
5. Tests that read `schemas/1.2.3/` read the artifact schema.
6. The `schemas/` directory is removed: `schemas/1.2.3/` and the unused `schemas/1.2.2/`. The sdist no longer includes
   `schemas/1.2.3`.
7. `NOTICE` keeps the attribution to NIST, and it states that the models are generated from the OSCAL JSON Schema. It no
   longer states that the schemas are vendored.
8. `src/oscal_bindings/v1/models.py` does not change. A clean checkout generates it byte for byte.
9. CI fails when the regenerated `models.py` differs from the committed file. After this change, the committed
   `models.py` is the only reviewable record of what the pin generates.
10. `DEVELOPING.md` describes how to move the pin and what a reviewer checks. A test checks the URL prefix of the pin.

The public API, the wheel contents, and the package version do not change.

The open question of #18 has an answer: the manifest generator is already in the store (`scripts/names.ts`), and the
store CI checks `names.json` against it. No store-side issue is necessary.

## Capabilities

### New Capabilities

None. The contract is in the `schema-versioning` ([VER-002], [VER-005]) and `naming-manifest` ([NAM-002])
capabilities of the oscal-bindings-specs store.

### Modified Capabilities

None. This repo holds no main specs. The change sets `skip_specs: true`.

## Impact

1. Code: `scripts/manifest.py`, `scripts/hoist_names.py`, `scripts/postprocess_models.py`, `scripts/spec_artifact.py`
   (docstrings only), and `pyproject.toml` (`generate` script, sdist `only-include`).
2. CI: `.github/workflows/build.yml` adds a drift check of `models.py` after `hatch run release`.
3. Tests: `tests/test_schema_validation.py`, `tests/test_hoist_names.py`, `tests/test_manifest.py`,
   `tests/test_postprocess.py`, `tests/test_oscal_bindings.py`, `tests/test_prop_version_package.py`,
   `tests/test_spec_artifact_script.py`, `tests/support/oscal_shape.py`, `tests/support/spec_artifact.py`, and
   `tests/support/version_package.py`.
4. Removed files: every file under `schemas/`.
5. Network: a test that reads the schema needs the spec artifact. On a cold cache, it downloads the artifact. `hatch
   test` already needs the artifact for the corpus, so the network requirement of the suite does not change.
6. sdist: a build from the sdist can no longer generate the models without network access. A wheel build from the sdist
   does not change.
7. Docs: `NOTICE`, `README.md`, `DEVELOPING.md`, `AGENTS.md`, and `.agents/summary/`.
8. Users: none. The import surface, the models, and the serialized output do not change.

[VER-002]: https://github.com/cairn-proofs/oscal-bindings-specs/blob/main/openspec/specs/schema-versioning/spec.md#requirement-ver-002-a-binding-is-generated-from-exactly-one-active-oscal-release
[VER-005]: https://github.com/cairn-proofs/oscal-bindings-specs/blob/main/openspec/specs/schema-versioning/spec.md#requirement-ver-005-spec-artifacts-are-distributed-pinned-and-hash-verified
[NAM-002]: https://github.com/cairn-proofs/oscal-bindings-specs/blob/main/openspec/specs/naming-manifest/spec.md#requirement-nam-002-the-manifest-records-each-canonical-type-with-its-name-kind-and-kind-data
