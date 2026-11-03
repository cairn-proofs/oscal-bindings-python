# Tasks

## 1. Move the pin

- [x] 1.1 Set `SPEC_ARTIFACT_VERSION` to `0.6.0+oscal.1.2.3` and `SPEC_ARTIFACT_SHA256` to
  `612d1463e385ff948cfea8871b9dbc1e670a9ee0fcc3d0334744b535a12537fe` in `scripts/spec_artifact.py`, and update the
  two assertions in `tests/test_spec_artifact_script.py`. Verify with `hatch test tests/test_spec_artifact_script.py`.
- [x] 1.2 Run `hatch run generate` and verify that `git diff --exit-code -- src/oscal_bindings/v1/models.py` reports no
  change.
- [x] 1.3 Run `hatch test tests/test_conformance.py tests/test_traceability.py tests/test_corpus_coverage.py` and
  verify that each passes, including the case `parse/many-failures`. If a new case fails, stop and report it before
  you add an entry to `tests/support/expected_failures.py`.

## 2. JSON limits

- [x] 2.1 Add `JSON_DEPTH_LIMIT = 200` and `JSON_DIGIT_LIMIT = 4300` to `v1/parser.py`, outside `__all__`. Add the
  error mapping of design D2 to `parse_oscal`, raised `from None`. State the byte-offset column in the docstring of
  `OscalParseError`. Verify with `hatch run typing` and `hatch run lint`.
- [x] 2.2 Add the digit check of design D2a to the scalar step in `v1/extensions/_yaml_loader.py`. Import
  `JSON_DIGIT_LIMIT` from `v1/parser.py`. Verify with `hatch run typing` and `hatch run lint`.
- [x] 2.3 Add the tests of design D4, items 1 to 7: the JSON tests to `tests/test_parser.py`, and the YAML tests to
  `tests/test_yaml_io.py`. Cover each scenario of `specs/json-resource-limit/spec.md`. Verify with
  `hatch test tests/test_parser.py tests/test_yaml_io.py`.
- [x] 2.4 Document the limits per design D6. Add a "Resource limits" section to the README. It lists the two JSON
  limits and the four YAML limits, each with its value, its measure, and its operations. The operations include
  `validate_oscal` for the JSON limits. The section names the two new entry types. Add D1, D2, and D2a to Key Design
  Decisions in DEVELOPING.md. Extend `tests/test_lint_config.py` so that it ties the two JSON values to the constants,
  and checks that the README section names `validate_oscal`, `parse_oscal_yaml`, and `parse_oscal_yaml_file`. Verify
  with `hatch test tests/test_lint_config.py`.

## 3. Retired YML-011 and the YAML docs

- [ ] 3.1 Replace each citation of YML-011 with PRS-010 in `src/oscal_bindings/v1/extensions/yaml_io.py`,
  `src/oscal_bindings/v1/extensions/_yaml_loader.py`, `tests/test_yaml_io.py`, `tests/test_lint_config.py`, and
  `DEVELOPING.md`. Change the range "YML-001 to YML-011" in the `yaml_io.py` docstring and in `tests/test_yaml_io.py`
  to "YML-001 to YML-010". The YAML limits number four. So in the `yaml_io.py` docstring, change "three documented
  limits" to four, add the line-break placeholder limit, and state the operations of each limit. Make the same count
  change to the DEVELOPING.md heading "Three documented YAML resource limits". Verify with
  `git grep -n YML-011 -- . ':!openspec/changes/' ':!drafts/' ':!.agents/'`, which must find nothing.
- [ ] 3.2 Replace the second sentence of the Purpose in `openspec/specs/yaml-resource-limit/spec.md` so that it places
  the limits under the store's PRS-010 rule in the `document-parsing` capability. Do not change a requirement. Verify
  with `openspec validate --specs --strict`.
- [ ] 3.3 Update the stale docs. Change the pin in DEVELOPING.md (it names `0.3.0+oscal.1.2.3`) and in `AGENTS.md`.
  Replace "below the JSON path's own limit of about 200" in DEVELOPING.md with the documented JSON depth limit of 200.
  Update `.agents/summary/` where it names an old pin or YML-011. Verify with
  `git grep -n -e 0.3.0+oscal -e 0.5.1+oscal -e "about 200" -- DEVELOPING.md AGENTS.md .agents/summary/`, which must
  find nothing.

## 4. Full gate

- [ ] 4.1 Run `hatch run release > ./tmp/release.log 2>&1; echo "EXIT: $?"` and verify `EXIT: 0`. Then verify that
  `git diff --exit-code -- src/oscal_bindings/v1/models.py` reports no change and that
  `openspec validate move-pin-to-0-6-0 --strict` passes.

## Workflow follow-up

- After approval, create the feature branch from issue #35 with `gh issue develop 35 --checkout`. Commit the change
  artifacts first. Then commit each task group as a checkpoint, with the updated `tasks.md`. Before each checkpoint
  commit, run `hatch test --all > ./tmp/test.log 2>&1; echo "EXIT: $?"` and verify `EXIT: 0`.
- Push only after explicit approval. Then open a pull request that references issue #35, once `hatch run release`
  passes. The pull request carries the implementation only, not the archive.
- After the pull request review approves, archive the change on the branch with `openspec archive move-pin-to-0-6-0 -y`.
  This creates `openspec/specs/json-resource-limit/spec.md`.
- Verify the archive on the branch: `openspec validate --specs --strict` passes, `openspec list --specs` shows
  `json-resource-limit` and `yaml-resource-limit`, and `hatch run release` passes on the archived tree. After explicit
  approval, push the archive as a follow-up commit on the same pull request.
- Merge the pull request once it is approved and the archive commit is in it.
