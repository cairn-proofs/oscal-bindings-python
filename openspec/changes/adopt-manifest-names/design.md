## Context

See [proposal.md, Why](proposal.md#why). These facts shape the approach:

1. `hatch run generate` runs datamodel-codegen 0.83.0 with `--reuse-model` and `--collapse-root-models`, then
   `scripts/postprocess_models.py` (642 lines). Phase 1 of the post-processor changes structure: it collapses scalar
   root models and strips `pattern=` from non-string fields. Phases 2 and 3 rename classes. Nothing in the pipeline
   records which JSON pointer produced which class.
2. The current output has 210 classes. 113 of their names are manifest names, 97 are not, and 131 manifest names have
   no class. 35 class names end in an ordinal.
3. Closed enums (`allOf` of a base datatype and an `enum`) produce no class today. The field is `str`.
4. datamodel-codegen has `--model-name-map`, keyed by schema ref. A trial run matched definition pointers only. For an
   inline place, codegen checks an internal path such as
   `#/definitions/oscal-complete-oscal-catalog:group#-datamodel-code-generator-#-anyOf-#-special-#/0...`, not the
   JSON pointer. The map also fails when codegen gives a mapped name to an inline type first (`Status`).
5. A second trial copied each manifest site into `definitions/<Name>` and replaced the site with a `$ref` to it. Codegen
   without `--reuse-model` then emitted a class for all 177 `object`, 8 `document`, and 44 `enum` entries, each with
   its manifest name. It also emitted leftovers: the old definition keys as `OscalComplete...` classes, and one extra
   enum class for each closed-enum `allOf` (for example `HowMany` beside `ParameterSelectionHowMany`). Unions,
   `MappingCollectionMappings`, and `OscalDocument` got no class.
6. `tests/support/corpus.py` holds `PinnedArchive` and `ensure_pinned_archive`: a locked, sha256-checked fetch with
   safe extraction. `tests/support/spec_artifact.py` pins `0.1.0+oscal.1.2.3`, which has no manifest. Only tests use
   it.
7. `jsonschema-rs` 0.58.6 is locked in `hatch-test` only. The `default` env, where `generate` runs, has no JSON Schema
   validator.
8. `validate_element` derives its element types from the class names in `models.py`.
   `tests/support/element_types_snapshot.txt` pins the 187 current strings.

## Goals / Non-Goals

**Goals:**

1. Every manifest name is a module-level name of `models.py` with the kind that the manifest records. No other class
   name exists.
2. The post-processor holds no naming rule for manifest types. A guard compares the output with the manifest.
3. A closed enum rejects a value outside the enum.

**Non-Goals:**

1. Field names. They keep the current snake_case names and OSCAL aliases.
2. A corpus case for closed enums. That is cairn-proofs/oscal-bindings-specs#9. This change adds local tests.
3. The two text suggestions of cairn-proofs/oscal-bindings-specs#11. They change no data that this change reads.

## Decisions

### D1 — Name types by hoisting manifest sites into named definitions

`scripts/hoist_names.py` writes `build/codegen/oscal_complete_schema.json`. It reads the vendored schema and the
validated manifest, and it makes these changes in a copy:

1. For each entry, it copies the subschema at the first site to `definitions/<Name>`. It replaces every site of the
   entry with `{"$ref": "#/definitions/<Name>"}`. It processes the deepest sites first, so a hoisted body already holds
   the `$ref`s of its children.
2. For an entry with more than one site, it checks that the bodies are equal after step 1 ([MDL-013]). On a mismatch,
   it fails and names both sites.
3. It rewrites each `$ref` to an old definition key that was a site, and it removes that old key. This removes the
   `OscalComplete...` leftovers.
4. A closed-enum site is the `enum` branch of an `allOf` with a base datatype. The script replaces the whole `allOf`
   with the `$ref`. It first checks that each enum value is valid for the base datatype, so the base constraint holds
   for every value that the enum accepts. This removes the extra enum classes.
5. It leaves scalar definitions and the root `oneOf` as they are.
6. It keeps the `title` and `description` of a property beside the `$ref` that replaces the property schema. A union
   branch without a `description` takes the `description` of its union. Without this step, 27 fields lose their
   documentation and 31 branch classes lose their docstrings.

Codegen then reads the hoisted copy, without `--reuse-model`. The manifest already records every merge, and
`--reuse-model` merges by structure, which [MDL-013] does not allow. The vendored schema stays the source of truth and
the input that `hatch test` validates against. The hoisted copy is a build file and is git-ignored.

- **Why not `--model-name-map`:** it cannot match inline places (Context, item 4). The only key it can match for an
  inline type is an internal path of codegen 0.83.0, which can change in any release.
- **Why not rename after generation:** the generated source does not hold pointers. Matching classes to sites by
  structure is what the current post-processor does, and it is the reason for the ordinals.

### D2 — The post-processor adds the types that codegen does not emit, then checks the result

The post-processor keeps phase 1. It removes phases 2 and 3, `VARIANT_RENAMES`, `COLLISION_OVERRIDES`,
`POSITIONAL_DOCUMENT_RENAMES_SNAPSHOT`, and the unused `ROOT_RENAME`. It reads the manifest and adds:

1. One `TypeAlias` per `union` entry: `CatalogGroup: TypeAlias = CatalogGroupWithControls | CatalogGroupWithGroups`. It
   replaces each inline union of the variant types with the alias.
2. `MappingCollectionMappings` as a `RootModel[Mapping | list[Mapping]]`, the field type of `mappings` ([MDL-003]).
3. `OscalDocument` as the `RootModel` of the eight document types ([MDL-003]).

Then it applies these guards. Each guard reports every failure at once, and the script writes nothing on a failure:

1. Each manifest name occurs exactly once at module level, as a class for `object`, `document`, and `enum`, as a
   `TypeAlias` for `union`, and as a `RootModel` for `single-or-many` and `document-union`.
2. Each other module-level name is a scalar alias (D3). No class has a name outside the manifest.
3. No two module-level names are equal.

datamodel-codegen writes `build/codegen/models.py`. The post-processor reads that file and replaces
`src/oscal_bindings/v1/models.py` atomically only when every guard passes, so a failed run leaves the committed module
as it was.

The post-processor reads the vendored schema, not the hoisted copy. It needs only the definition keys of the scalar
definitions (D3).

The variants of a union alias are in manifest order. When an object matches more than one variant, pydantic selects
the first variant. So a `Parameter` with neither `select` nor `values` parses as `ParameterWithSelect`. The serialized
output does not change.

- **Why aliases for unions:** a union is a choice between classes and not an object. A `TypeAlias` gives the name to
  annotations and `TypeAdapter` without a wrapper object.

### D3 — Scalar aliases keep their current names

A scalar definition has no manifest entry ([NAM-001] rule 4). Phase 1 already collapses it to an `Annotated` alias, for
example `LocationUuid` and `StringDatatype`. These names stay as they are, from the definition key without the
`oscal-complete-oscal-<module>:` prefix. They are binding names, not contract names. Guard 3 of D2 fails if one equals
a manifest name.

- **Alternative considered:** put each scalar type inline at each use. [MDL-003] allows it, but it removes public names
  that the release notes would also have to list, and it repeats each pattern many times in `models.py`. Rejected.

### D4 — One pin of the spec artifact for generation and tests

`scripts/spec_artifact.py` holds the pin (`0.2.0+oscal.1.2.3` and its sha256). `PinnedArchive`, `ensure_pinned_archive`,
and their lock, download, and safe-extraction helpers move from `tests/support/corpus.py` to
`scripts/pinned_archive.py`. `tests/support/corpus.py` and `tests/support/spec_artifact.py` import them from there. The
cache stays `tests/.corpus_cache/`, so `generate` and `hatch test` share one download.

- **Why fetch and not vendor `names.json`:** the issue requires the pinned artifact. A vendored copy is a second copy
  that can drift from the release.

### D5 — The generator validates the manifest before it uses it

`scripts/manifest.py` applies these checks in order, and `hoist_names.py` calls it first:

1. `names.json` against `manifest/names.schema.json` from the same artifact, with `jsonschema-rs` ([NAM-004]).
2. `format` is 1, and `oscal-release` is `1.2.3` ([NAM-003]).
3. `schema.sha256` equals the sha256 of the vendored schema bytes that codegen reads ([NAM-002]).
4. Unique names, pointers that occur once and resolve through own keys only, and type references that name an entry
   ([NAM-001], [NAM-003]).

`jsonschema-rs` moves into the `default` env at 0.58.6, the version that `hatch-test` already locks. The `default`
pins constrain `hatch-test`, so the two envs keep one version.

### D6 — Closed enums are `Enum` classes, as open enums are

A closed-enum field holds the enum class, for example `how_many: ParameterSelectionHowMany | None`. Pydantic accepts
the value string on input and rejects any other string. An open-enum field keeps its current form, the union of the base
alias and the enum class. Serialization writes the value, as it does for open enums today.

### D7 — A clean break, with a full list of names

1. The package version goes from `0.2.1` to `0.3.0`. No deprecated alias stays (proposal, What Changes, item 3).
2. `scripts/name_changes.py` writes `build/name-changes.md`: the removed names, the added names, and the changed
   element-type strings. The README and the GitHub release notes take that list.
3. `tests/support/element_types_snapshot.txt` is regenerated from the new classes.

## Risks / Trade-offs

1. [Codegen output without `--reuse-model` differs in more than names, for example in field order or constraints] →
   `hatch test` runs the full corpus and the schema-validation tests. Task 3.3 reviews the `models.py` diff of field
   types, not only of names.
2. [A hoisted `$ref` changes a field `title` or `description`] → The hoist copies the subschema with its `title` and
   `description`. The diff review of task 3.3 covers this.
3. [Users meet many import errors at once] → The release notes list each name. Version `0.3.0` marks the break.
4. [Strings from the manifest reach generated code] → The manifest is pinned by sha256 and checked against its JSON
   Schema and [NAM-003] before use. Names reach codegen only as definition keys that match `^[A-Z][A-Za-z0-9]*$`.
   Codegen also rejects an invalid class name.
5. [Generation needs the network] → It uses the shared cache. CI already downloads the artifact for `hatch test`.

## Migration Plan

1. Implement on branch `16-names-from-manifest`. `hatch run release` must pass before the final commit.
2. Archive this change on the branch, then merge.
3. Tag `v0.3.0` and publish the draft release with the name list.

**Rollback:** revert the merge before a release. After `v0.3.0` is published, a rollback is a new breaking release.

[MDL-003]: https://github.com/cairn-proofs/oscal-bindings-specs/blob/main/openspec/specs/model-derivation/spec.md#requirement-mdl-003-scalar-root-wrappers-collapse-to-plain-aliased-types
[MDL-013]: https://github.com/cairn-proofs/oscal-bindings-specs/blob/main/openspec/specs/model-derivation/spec.md#requirement-mdl-013-types-deduplicate-only-for-union-branch-copies-and-explicit-merges
[NAM-001]: https://github.com/cairn-proofs/oscal-bindings-specs/blob/main/openspec/specs/naming-manifest/spec.md#requirement-nam-001-a-type-is-identified-by-json-pointers-into-the-complete-schema
[NAM-002]: https://github.com/cairn-proofs/oscal-bindings-specs/blob/main/openspec/specs/naming-manifest/spec.md#requirement-nam-002-the-manifest-records-each-canonical-type-with-its-name-kind-and-kind-data
[NAM-003]: https://github.com/cairn-proofs/oscal-bindings-specs/blob/main/openspec/specs/naming-manifest/spec.md#requirement-nam-003-canonical-names-are-unique-pascalcase-identifiers
[NAM-004]: https://github.com/cairn-proofs/oscal-bindings-specs/blob/main/openspec/specs/naming-manifest/spec.md#requirement-nam-004-the-store-publishes-a-json-schema-for-each-manifest-file
