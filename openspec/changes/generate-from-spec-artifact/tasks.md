## 1. Scripts read the schema from the artifact

- [ ] 1.1 In `scripts/manifest.py`, remove `VENDORED_SCHEMA`. Let `load_validated_manifest` take the schema bytes from
      its caller, or read `schema_path` one time (default `None`, which means `paths.schema`) and give the bytes back
      (design.md D1, items 1 and 2). Keep the comparison of `schema.sha256` with those bytes. Update the module
      docstring and `main`. Verify with `hatch test tests/test_manifest.py` that a schema whose sha256 differs from
      `schema.sha256` still fails, and that the default reads the artifact schema.
- [ ] 1.2 In `scripts/hoist_names.py`, read the schema from `paths.schema` one time, and parse the same bytes that the
      manifest check hashed (D1, items 2 and 3). Replace "vendored schema" in the docstrings with "artifact schema".
      Verify with `hatch test tests/test_hoist_names.py`.
- [ ] 1.3 In `scripts/postprocess_models.py`, remove `ACTIVE_SCHEMA_RELEASE` and `DEFAULT_SCHEMA_PATH`. Default
      `--schema` to `None`, and resolve `None` in `main` to `artifact_paths(ensure_spec_artifact()).schema`. Read the
      schema bytes one time for the manifest check and the scalar names (D1, items 2 and 4). Keep the non-zero exit for
      a missing explicit `--schema`. Update `tests/test_postprocess.py`: remove
      `test_active_schema_release_is_the_release_of_the_pin`, and replace each use of `DEFAULT_SCHEMA_PATH` with the
      artifact schema path. Verify with `hatch test tests/test_postprocess.py`.
- [ ] 1.4 In `pyproject.toml`, remove `--schema ./schemas/1.2.3/oscal_complete_schema.json` from the `generate` script
      (D1, item 5). In `scripts/spec_artifact.py`, change the docstring of `ArtifactPaths.schema` from "the vendored
      schema" to "the complete schema". Add a test to `tests/test_spec_artifact_script.py` that the URL of the pin
      starts with `https://github.com/cairn-proofs/oscal-bindings-specs/releases/download/` (D6, item 2). Verify with
      `hatch test tests/test_spec_artifact_script.py`, then run `hatch run generate` and verify that
      `git diff --exit-code -- src/oscal_bindings/v1/models.py` exits 0.

## 2. Tests read the schema from the artifact

- [ ] 2.1 In `tests/support/spec_artifact.py`, add `schema_path()` beside `corpus_root()` (D3, item 1). In
      `tests/support/version_package.py`, make `active_schema_path()` return `schema_path()`, and remove the load of the
      post-processor. Verify that `git grep -n "DEFAULT_SCHEMA_PATH\|postprocess" -- tests/support/version_package.py`
      prints nothing.
- [ ] 2.2 In `tests/test_oscal_bindings.py` and `tests/test_prop_version_package.py`, assert that
      `__oscal_schema_version__` equals `OSCAL_RELEASE`, and that `OSCAL_RELEASE` equals the release in the `$id` of the
      artifact schema (D2). Verify with `hatch test tests/test_oscal_bindings.py tests/test_prop_version_package.py`,
      and verify that a test fails when `__oscal_schema_version__` is set to a different release in a temporary edit.
- [ ] 2.3 In `tests/support/oscal_shape.py`, compute the schema property names in a `functools.cache` function on
      first use, not at import (D3, item 2). In `tests/test_schema_validation.py`, remove `SCHEMA_PATH` and read
      `schema_path()` inside `_schema()` (D3, item 3). Verify with
      `hatch test tests/test_schema_validation.py tests/test_serialization_defaults.py tests/test_prop_serialization_defaults.py`.

## 3. CI drift check

- [ ] 3.1 In `.github/workflows/build.yml`, add a step after `hatch run release` and before `hatch build` that runs
      `git diff --exit-code -- src/oscal_bindings/v1/models.py` (D5). Give the step a name that states its purpose. Keep
      the existing permissions and action pins. Verify that the file parses with
      `hatch run python -c "import sys, yaml; yaml.safe_load(open(sys.argv[1]))" .github/workflows/build.yml`, and that
      the step order is `hatch run release`, the drift check, `hatch build`. The first CI run of the pull request
      verifies the step itself.

## 4. Remove the vendored schemas

- [ ] 4.1 Check that three sha256 values are equal: `schemas/1.2.3/oscal_complete_schema.json`, the artifact schema
      (`hatch run python scripts/spec_artifact.py` prints its path), and `schema.sha256` in the artifact `names.json`
      (D4, item 1). Report the value. The orchestrator puts it in the message of the commit that removes `schemas/`.
      Stop and report if the values differ.
- [ ] 4.2 Run `git rm -r schemas/` (D4, item 2). In `pyproject.toml`, remove `"schemas/1.2.3"` from
      `[tool.hatch.build.targets.sdist].only-include` and the comment text that names `ACTIVE_SCHEMA_RELEASE` (D4,
      item 3). Verify that `git grep -n -E "schemas/|ACTIVE_SCHEMA_RELEASE|VENDORED_SCHEMA|DEFAULT_SCHEMA_PATH" --
      scripts tests src pyproject.toml .github` prints only paths inside the artifact (`artifact_paths`, its tests).
      Verify that `hatch build` succeeds and that the sdist holds no `schemas/` member.
- [ ] 4.3 In `NOTICE`, keep the attribution to NIST. State that the models are generated from the OSCAL JSON Schema,
      which the spec artifact supplies, and remove the statement that the schemas are vendored (D4, item 4). Verify that
      `NOTICE` names NIST and the OSCAL repository, and does not contain the word "vendored".

## 5. Docs

- [ ] 5.1 Update `DEVELOPING.md`: replace the procedure to vendor a new release with the procedure to move the pin and
      the review checks of D6, items 1 to 5. State that `generate` and an sdist need the network on a cold cache.
      Update the pipeline text that names `schemas/<release>/` or `ACTIVE_SCHEMA_RELEASE`. Verify that
      `git grep -n -E "ACTIVE_SCHEMA_RELEASE|schemas/<release>|vendored schema" -- DEVELOPING.md` prints nothing.
- [ ] 5.2 Update `README.md`, `AGENTS.md`, and `.agents/summary/`: remove `schemas/` from the layout and the pipeline
      text, and state that the schema comes from the pinned spec artifact. Do not edit `.kiro/specs/` or
      `openspec/changes/archive/`, which are records. Verify that
      `git grep -n -E "ACTIVE_SCHEMA_RELEASE|VENDORED_SCHEMA|schemas/<release>|schemas/1\.2\." -- README.md AGENTS.md .agents/summary`
      prints nothing.

## 6. Gate

- [ ] 6.1 Run `hatch run release` with an empty `tests/.corpus_cache/` (move the existing cache aside, then restore
      it). Verify that it passes, that `git diff --exit-code -- src/oscal_bindings/v1/models.py` exits 0, and that
      `schemas/` does not exist.
- [ ] 6.2 Reconcile `threat-model.tc.json`: set each mitigation that this change ships to `mitigationResolved`
      (M6, M8, M9, M10, M12, M13). Confirm that no threat with Critical or High residual risk is left without a
      resolved mitigation, and validate the file with the Threat Composer validator.

## Task Dependency Graph

Each wave owns its files. No two waves that can run at the same time own the same file. Group 6 runs on the main
session after all waves.

```yaml
waves:
  - id: W1-scripts
    tasks: ["1.1", "1.2", "1.3", "1.4"]
    owns: [scripts/manifest.py, scripts/hoist_names.py, scripts/postprocess_models.py, scripts/spec_artifact.py,
           pyproject.toml, tests/test_manifest.py, tests/test_hoist_names.py, tests/test_postprocess.py,
           tests/test_spec_artifact_script.py]
    dependsOn: []
  - id: W2-tests
    tasks: ["2.1", "2.2", "2.3"]
    owns: [tests/support/spec_artifact.py, tests/support/version_package.py, tests/support/oscal_shape.py,
           tests/test_oscal_bindings.py, tests/test_prop_version_package.py, tests/test_schema_validation.py]
    dependsOn: []
  - id: W3-ci
    tasks: ["3.1"]
    owns: [.github/workflows/build.yml]
    dependsOn: []
  - id: W4-remove
    tasks: ["4.1", "4.2", "4.3"]
    owns: [schemas/, pyproject.toml, NOTICE]
    dependsOn: [W1-scripts, W2-tests, W3-ci]
  - id: W5-docs
    tasks: ["5.1", "5.2"]
    owns: [DEVELOPING.md, README.md, AGENTS.md, .agents/summary/]
    dependsOn: [W1-scripts]
```
