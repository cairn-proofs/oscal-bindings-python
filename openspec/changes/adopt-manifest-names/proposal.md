## Why

The spec store publishes the canonical name of every OSCAL type in `names.json` (spec artifact `v0.2.0+oscal.1.2.3`).
The TypeScript spike (cairn-proofs/oscal-bindings-typescript#1) settled its format, and the store archived the change
`define-names-manifest-format`. This binding still derives names from datamodel-codegen heuristics and the naming maps
of `scripts/postprocess_models.py`. So 97 public names, for example `Type3` and `ProfileGroup1`, differ from the
contract ([MDL-009]). Closed enums are plain `str`, so the binding accepts values that the schema rejects ([MDL-011],
#21). This change closes #16 and #21.

## What Changes

1. `hatch run generate` takes every type name from `names.json` of the pinned spec artifact. It checks the archive
   sha256, the manifest JSON Schema, the [NAM-003] rules, and the schema hash before it generates code.
2. The post-processor loses its naming rules: `derive_document_renames`, `VARIANT_RENAMES`, `COLLISION_OVERRIDES`,
   the namespace renames, and the positional snapshot. It keeps its structure phases, and it adds guards that compare
   the output with the manifest.
3. **BREAKING:** about 97 public names go away, and about 131 manifest names are new. Four names now name a
   different type: `Status`, `Origin`, `LocalDefinitions`, and `MergeFlat`. No deprecated aliases stay, because an
   alias for a reused name points at the wrong type.
4. **BREAKING:** each closed enum is an `Enum` type, so a value outside the enum fails validation.
5. **BREAKING:** the strings of `get_supported_element_types()` follow the new class names, for example
   `profile-group-with-groups` for `profile-group1`.
6. The 13 unions get type aliases with their manifest names, for example `CatalogGroup`.
7. The pin of the spec artifact moves from `0.1.0+oscal.1.2.3` to `0.2.0+oscal.1.2.3`, and generation and tests share
   it.
8. The package version goes to `0.3.0`.

## Capabilities

### New Capabilities

None. The contract is in the `naming-manifest` and `model-derivation` capabilities of the oscal-bindings-specs store.

### Modified Capabilities

None. This repo holds no main specs. The change sets `skip_specs: true`.

## Impact

1. Code: `pyproject.toml` (`generate`, version, dependencies), `scripts/postprocess_models.py`, new generate-time
   modules under `scripts/`, `src/oscal_bindings/v1/models.py` (regenerated), `v1/extensions/builders.py`,
   `v1/extensions/__init__.py`, and `tests/support/spec_artifact.py`.
2. Tests: the post-processor tests, `tests/support/element_types_snapshot.txt`, and each test that imports a renamed
   class, for example `Algorithm`.
3. Dependency: `jsonschema-rs` moves into the `default` env at the version that `hatch-test` already locks. The
   lockfiles change.
4. `hatch run generate` needs the network on a cold cache, as `hatch test` already does for the corpus.
5. Docs: `README.md`, `DEVELOPING.md`, `AGENTS.md`, and `.agents/summary/`.
6. Users: every import of a renamed type breaks. The release notes list each removed name and each added name.

[MDL-009]: https://github.com/cairn-proofs/oscal-bindings-specs/blob/main/openspec/specs/model-derivation/spec.md#requirement-mdl-009-the-naming-manifest-is-the-shared-source-of-truth-across-languages
[MDL-011]: https://github.com/cairn-proofs/oscal-bindings-specs/blob/main/openspec/specs/model-derivation/spec.md#requirement-mdl-011-each-enum-site-is-a-named-type-marked-open-or-closed
[NAM-003]: https://github.com/cairn-proofs/oscal-bindings-specs/blob/main/openspec/specs/naming-manifest/spec.md#requirement-nam-003-canonical-names-are-unique-pascalcase-identifiers
