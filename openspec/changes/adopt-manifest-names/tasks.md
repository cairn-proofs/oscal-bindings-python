## 1. Pinned artifact and manifest validation

- [x] 1.1 Move `PinnedArchive`, `ensure_pinned_archive`, and their lock, download, and safe-extraction helpers from
      `tests/support/corpus.py` to `scripts/pinned_archive.py` (design.md D4). Import them from there in
      `tests/support/`. Verify that `hatch test tests/test_corpus_fetcher.py tests/test_spec_artifact.py` passes with
      no test change.
- [x] 1.2 Add `scripts/spec_artifact.py` with the pin `0.2.0+oscal.1.2.3` and its sha256
      `3bc746e8a6182a612c2a8f397e0ee7a47b2d777108f93df81dcd139ee59b271e`. Point `tests/support/spec_artifact.py` at it.
      Verify that `hatch test tests/test_conformance.py` passes against the new artifact.
- [x] 1.3 Add `jsonschema-rs==0.58.6` to the `default` env and run `hatch run lock`. Verify that only `requirements.txt`
      changes and that `hatch run python -c "import jsonschema_rs"` succeeds.
- [x] 1.4 Add `scripts/manifest.py` with the checks of design.md D5. Verify that the released manifest passes. Also
      verify with tests that a changed copy of the manifest fails for each of these changes:
      1. A name `Bad-Name`, a name with a final newline, and a duplicate name.
      2. A reference to no entry, `format` 2, and another `oscal-release`.
      3. A wrong `schema.sha256`, an unresolvable pointer, and a `__proto__` pointer.

## 2. Hoisted schema

- [x] 2.1 Add `scripts/hoist_names.py` with steps 1 to 5 of design.md D1. Verify these results with tests:
      1. Every site of the released manifest becomes a `$ref`.
      2. The copy holds no definition key of an old site.
      3. Two runs give byte-identical copies.
- [x] 2.2 Verify the guards of the hoist with tests. A merge with different bodies fails and names both sites. A closed
      enum with a value that its base datatype rejects fails and names the site.
- [x] 2.3 Verify that the hoisted copy accepts and rejects the same documents as the vendored schema. Run both schemas
      through `jsonschema-rs` on every valid and invalid corpus document, and compare the results.

## 3. Generation

- [x] 3.1 Change the `generate` script to three steps: the hoist, datamodel-codegen on
      `build/codegen/oscal_complete_schema.json` without `--reuse-model`, and the post-processor. Remove phases 2 and 3
      and the naming constants from `scripts/postprocess_models.py`. Add the union aliases, `MappingCollectionMappings`,
      and `OscalDocument` (design.md D2). Verify that `hatch run generate` succeeds.
- [x] 3.2 Add the three guards of design.md D2. Verify with tests on changed copies of the output that each guard fails
      and lists every offender. The cases are a missing manifest name, a class outside the manifest, a scalar alias
      equal to a manifest name, and a duplicate name.
- [x] 3.3 Review the `models.py` diff for changes other than names: field types, constraints, titles, and descriptions.
      Verify that each change is a rename, a closed enum in place of `str`, or a union alias in place of an inline
      union. Record each other change in the PR description.
- [x] 3.4 Replace the tests of the removed phases in `test_postprocess.py` and `test_prop_postprocess.py` with tests of
      the hoist and the guards. Verify that `hatch test tests/test_postprocess.py tests/test_prop_postprocess.py`
      passes.

## 4. Hand-written code and tests

- [x] 4.1 Update `v1/extensions/builders.py`, `v1/extensions/__init__.py`, and each test that imports a renamed class,
      for example `Algorithm` to `HashAlgorithm`. Verify that `hatch run typing` and `hatch run lint` pass.
- [x] 4.2 Regenerate `tests/support/element_types_snapshot.txt` from the new classes. Verify that the snapshot test
      passes and that each string is the kebab-case form of a manifest class name.
- [x] 4.3 Add tests for closed enums (design.md D6). Verify with `hatch test` these results:
      1. `ParameterSelectionHowMany` accepts `one` and `one-or-more`.
      2. A document with `how-many` set to `many` fails with `OscalParseError`.
      3. A parsed closed-enum value serializes back to its string.

## 5. Docs, version, and gate

- [x] 5.1 Add `scripts/name_changes.py` (design.md D7, item 2). Verify that `build/name-changes.md` lists the four
      reused names `Status`, `Origin`, `LocalDefinitions`, and `MergeFlat`, each with its old and its new type.
- [x] 5.2 Update `README.md`, `DEVELOPING.md`, `AGENTS.md`, and `.agents/summary/` for the new pipeline and the names.
      Set `version` to `0.3.0`. Verify that no doc names a removed constant or phase.
- [x] 5.3 Run `hatch run release` from a clean clone with an empty `tests/.corpus_cache`. Verify that it passes and
      that `models.py` holds no class name outside the manifest.

## Task Dependency Graph

Each wave owns its files. No two waves that can run at the same time own the same file. Task 5.3 runs on the main
session after all waves.

```yaml
waves:
  - id: W1-artifact
    tasks: ["1.1", "1.2"]
    owns: [scripts/pinned_archive.py, scripts/spec_artifact.py, tests/support/corpus.py, tests/support/spec_artifact.py]
    dependsOn: []
  - id: W2-deps
    tasks: ["1.3"]
    owns: [pyproject.toml, requirements.txt]
    dependsOn: []
  - id: W3-manifest
    tasks: ["1.4"]
    owns: [scripts/manifest.py, tests/test_manifest.py]
    dependsOn: [W1-artifact, W2-deps]
  - id: W4-hoist
    tasks: ["2.1", "2.2", "2.3"]
    owns: [scripts/hoist_names.py, tests/test_hoist_names.py, .gitignore]
    dependsOn: [W3-manifest]
  - id: W5-generate
    tasks: ["3.1", "3.2", "3.3", "3.4", "4.1"]
    owns: [pyproject.toml, scripts/postprocess_models.py, scripts/hoist_names.py, src/oscal_bindings/v1/models.py,
           src/oscal_bindings/v1/extensions/, tests/test_postprocess.py, tests/test_hoist_names.py,
           tests/test_prop_postprocess.py]
    dependsOn: [W4-hoist, W2-deps]
  - id: W6-callers
    tasks: ["4.2", "4.3"]
    owns: [tests/ (except the files of W5 and W7), tests/support/element_types_snapshot.txt]
    dependsOn: [W5-generate]
  - id: W7-name-list
    tasks: ["5.1"]
    owns: [scripts/name_changes.py, tests/test_name_changes.py]
    dependsOn: [W5-generate]
  - id: W8-docs
    tasks: ["5.2"]
    owns: [README.md, DEVELOPING.md, AGENTS.md, .agents/summary/, pyproject.toml]
    dependsOn: [W6-callers, W7-name-list]
```
