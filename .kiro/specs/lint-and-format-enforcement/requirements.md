# Requirements Document

## Introduction

The repository carries Ruff configuration but no enforcement path: no pinned Ruff version, no explicit rule selection, and no command in the release chain that fails on lint or format findings. The effective ruleset today is whatever Hatch's bundled static-analysis default happens to be, so the finding count drifts with tooling updates rather than with the source (~61 findings at baseline commit `da4be27`, 136 at present). The `hatch-static-analysis` environment additionally has a broken Python symlink, so the default Hatch `fmt` path is not usable as-is.

This feature makes lint and format enforcement reproducible and self-governed. Ruff becomes an explicitly pinned development dependency with a rule selection owned by `pyproject.toml`. Pre-existing findings are accepted through narrow path-scoped ignores rather than source rewrites. The generated model module is excluded from both the linter and the formatter through configuration only, preserving byte-identical regeneration. Enforcement runs as a local Hatch script gated by the existing `release` chain — the repository adds no CI workflow and no pre-commit hook.

Reformatting is a mechanical change: roughly ten files (after excluding the generated module) will be rewritten by the formatter, and the existing test suite and type check are the evidence that behavior is unchanged.

## Glossary

- **Linter**: The Ruff lint engine, invoked as `ruff check`, that reports rule violations.
- **Formatter**: The Ruff format engine, invoked as `ruff format`, that rewrites source layout.
- **Ruff_Config**: The `[tool.ruff]`, `[tool.ruff.lint]`, `[tool.ruff.format]`, and `[tool.ruff.lint.per-file-ignores]` tables in `pyproject.toml`.
- **Dev_Dependencies**: The dependency list of the default Hatch environment in `pyproject.toml` (`[tool.hatch.envs.default]`).
- **Lint_Script**: The Hatch script that runs the Linter and the Formatter in check mode, named `lint`.
- **Release_Chain**: The existing `release` Hatch script, which today runs `generate`, `typing`, `hatch test --all --cover`, and `docs`.
- **Generated_Models**: The file `src/oscal_bindings/v1/models.py`, produced by `datamodel-code-generator` and rewritten by `scripts/postprocess_models.py`.
- **Pinned_Ruff_Version**: A single exact Ruff version recorded in Dev_Dependencies.
- **Baseline_Findings**: The Linter findings present in the repository before this feature is implemented, specifically `T201` and `INP001` in `scripts/`, `INP001` in `tests/`, `PLR0912` and `PLR0915` in `scripts/postprocess_models.py`, `EM101`, `EM102`, and `TRY003` in the hand-written modules under `src/oscal_bindings/v1/`, `PLC0414` in `src/oscal_bindings/__init__.py`, and `RUF100` on the unused `# noqa: F401` directives in the compatibility shim. A measurement over `scripts/`, `src/`, and `tests/` with Generated_Models excluded reported 418 findings under Ruff 0.4.5 from the Hatch static-analysis environment; the count under the Pinned_Ruff_Version may differ.
- **Test_Suite**: The tests under `tests/`, executed by `hatch test --all` across the Python 3.11 and 3.12 matrix cells. The pre-feature baseline is 261 tests per matrix cell; this feature adds test modules, so the post-feature count is expected to be higher.
- **Type_Check**: The existing `typing` Hatch script, which runs mypy over `src/oscal_bindings`.

## Requirements

### Requirement 1: Self-owned Ruff version and ruleset

**User Story:** As a maintainer, I want the Ruff version and ruleset owned by this repository, so that lint results are reproducible across machines and unaffected by changes to Hatch's bundled defaults.

#### Acceptance Criteria

1. THE Dev_Dependencies SHALL declare Ruff at a Pinned_Ruff_Version using an exact version specifier.
2. THE Ruff_Config SHALL declare an explicit `lint.select` value that defines the active rule set.
3. WHEN the Linter runs, THE Linter SHALL apply the rule set from `lint.select` in Ruff_Config rather than a rule set supplied by the Hatch static-analysis environment.
4. THE Ruff_Config and Dev_Dependencies together SHALL leave no input to the Linter machine-dependent: the Pinned_Ruff_Version, `lint.select`, `lint.ignore`, the exclusion patterns, and `per-file-ignores` SHALL all be read from `pyproject.toml` at the commit under test. *(Structurally held, not empirically verified. Reporting the same findings on two machines at the same commit follows from this criterion together with 1.1, 1.2, and 1.3; observing it directly would require provisioning a second environment, which is out of proportion to the risk. No task claims to verify it empirically.)*
5. THE Ruff_Config SHALL retain `line-length = 88`, `target-version = "py311"`, `format.quote-style = "double"`, `format.indent-style = "space"`, and `lint.isort.known-first-party = ["oscal_bindings"]`.
6. THE Ruff_Config SHALL retain the per-file ignore list `["PLR2004", "S101", "TID252", "PLC0415"]` for `tests/**/*`.
7. THE Ruff_Config SHALL apply the existing exclusion of `./build` and `.hatch` at the table where Ruff reads it for both the Linter and the Formatter.
8. THE Ruff_Config SHALL exclude Markdown files from both the Linter and the Formatter, so that the enforcement scope is the hand-written Python source and not the repository's documentation. *(Added during review. The Pinned_Ruff_Version includes `*.md` in its default `include` list and formats Python code blocks in Markdown by default, so without this exclusion `ruff check .` and `ruff format .` would lint and rewrite code samples in `README.md`, `.agents/summary/*.md`, and the untracked `.kiro/specs/**/*.md`.)*

### Requirement 2: Baseline findings accepted through configuration

**User Story:** As a maintainer, I want pre-existing findings accepted through configuration, so that enabling enforcement does not require rewriting working source code.

#### Acceptance Criteria

1. THE Ruff_Config SHALL allow `T201` and `INP001` for files under `scripts/` through a `per-file-ignores` entry. *(`INP001` added during implementation on measured findings under the Pinned_Ruff_Version: `scripts/` is intentionally not a package, for the same reason as `tests/` in criterion 2.2.)*
2. THE Ruff_Config SHALL allow `INP001` for files under `tests/` through a `per-file-ignores` entry.
3. THE Ruff_Config SHALL allow `EM101`, `EM102`, and `TRY003` for files matching `src/oscal_bindings/v1/**` through a single `per-file-ignores` entry, and SHALL name no code other than those three in that entry. *(Widened during review on measured findings. Under the selected rule set with Generated_Models excluded, the three codes occur in three hand-written modules, not one: `v1/parser.py` (8x `EM101`, 4x `EM102`, 12x `TRY003`), `v1/extensions/document.py` (2x `EM102`, 2x `TRY003`), and `v1/extensions/validate_element.py` (1x `EM102`, 1x `TRY003`). A `parser.py`-only entry naming only `EM101` and `TRY003` cannot reach zero. Counts were measured with Ruff 0.4.5 from the Hatch static-analysis environment, not the Pinned_Ruff_Version, so they are indicative rather than final.)*
4. THE Ruff_Config SHALL record, as a comment on the `per-file-ignores` entry required by criterion 2.3, that the entry defers a planned dedicated document-type-mismatch exception (`WrongDocumentTypeError`) rather than accepting the flagged pattern as correct. *(Amended after delivery: the comment originally cited a backlog ID, and a raw-text test asserted that wording. When the backlog moved out of the repo, the ID was dropped from the comment and the wording-only test was removed; the exact-codes assertion for the entry remains.)* *(The `EM`/`TRY003` findings are incidentally reporting a real API weakness: all eight typed parsers raise a flat `OscalParseError`, indistinguishable from an invalid-JSON or schema-violation error except by string-matching the message. Correcting that changes the public API surface and is out of scope for this feature, so the entry is a deferral with a pointer, not a blessing.)*
5. THE Ruff_Config SHALL allow `PLC0414` for `src/oscal_bindings/__init__.py` through a `per-file-ignores` entry scoped to that file. *(One finding, at line 44. The flagged line is the PEP 484 explicit-re-export idiom `import X as X`, which is the intended construct in a compatibility shim whose whole purpose is re-export; the rule is wrong in this context.)*
6. THE hand-written source SHALL contain no `# noqa` directive that suppresses no finding under the selected rule set, and the six unused `# noqa: F401` directives on re-export lines in `src/oscal_bindings/__init__.py` (2), `src/oscal_bindings/extensions/__init__.py` (1), `src/oscal_bindings/parser.py` (1), and `src/oscal_bindings/v1/__init__.py` (2) SHALL be removed by deletion. On the four of those lines that are star imports and carried `# noqa: F401, F403`, only the `F401` code is removed and `F403` is retained, because it still suppresses a real finding. *(This is the one place the configuration-only stance of criterion 2.8 yields, and it is consistent with it rather than an exception to it: a directive that suppresses nothing is dead code, deleting it is not a source rewrite of working logic, and exempting `RUF100` would preserve misleading comments that claim a suppression the linter does not need. No import, no name, and no re-export changes — only the trailing comment is deleted.)*
7. THE Ruff_Config SHALL keep `T201`, `INP001`, `EM101`, `EM102`, `TRY003`, `PLC0414`, `PLR0912`, and `PLR0915` active for every path outside the `per-file-ignores` entries that name them.
8. WHEN the Linter runs after this feature is implemented with the `per-file-ignores` entries required by criteria 2.1, 2.2, 2.3, 2.5, and 2.9 in place and the directives named in criterion 2.6 removed, THE Linter SHALL report zero findings without any change to the `print` calls in `scripts/`, without adding `tests/__init__.py`, and without rewriting any exception message in `src/oscal_bindings/v1/`.
9. THE Ruff_Config SHALL allow `PLR0912` and `PLR0915` for exactly `scripts/postprocess_models.py` through an exact-path `per-file-ignores` entry, with a comment stating why the flagged function is not split. *(Added during implementation on measured findings under the Pinned_Ruff_Version. Both codes fire once, on `collapse_scalar_root_models()` (18 branches, 81 statements): a single-pass line scanner whose branches are the cases of one state machine sharing one cursor, which splitting would scatter across helpers.)*

### Requirement 3: Generated models exempt from lint and format

**User Story:** As a maintainer, I want the generated model module exempt from lint and format findings, so that regeneration stays byte-identical and no finding is raised on output no one edits by hand.

#### Acceptance Criteria

1. THE Ruff_Config SHALL exclude Generated_Models from the Linter.
2. THE Ruff_Config SHALL exclude Generated_Models from the Formatter.
3. THE Ruff_Config SHALL express both exclusions in `pyproject.toml`.
4. THE Generated_Models file SHALL contain no `# noqa` comment and no `# fmt: off` or `# fmt: on` comment added by this feature.
5. WHEN `hatch run generate` runs after this feature is implemented, THE Generated_Models file SHALL be byte-identical to the Generated_Models file committed before that run. (Added during implementation: byte-identity depends on `datamodel-code-generator[http]` being pinned with an exact `==` specifier and on `generate` passing `--disable-timestamp`; without either, the generator's timestamp banner or version drift changes the file on every run.)

### Requirement 4: Enforcement gated by the release chain

**User Story:** As a maintainer, I want lint and format checks gated by the release chain, so that findings block a release the same way type errors and failing tests already do.

#### Acceptance Criteria

1. THE Lint_Script SHALL run the Linter in check mode over the repository.
2. THE Lint_Script SHALL run the Formatter in check mode over the repository, reporting differences without rewriting files.
3. IF the Linter reports one or more findings, THEN THE Lint_Script SHALL exit with a non-zero status.
4. IF the Formatter reports one or more files that would be rewritten, THEN THE Lint_Script SHALL exit with a non-zero status.
5. THE Release_Chain SHALL invoke the Lint_Script.
6. THE Release_Chain SHALL continue to invoke `generate`, `typing`, `hatch test --all --cover`, and `docs`.
7. IF the Lint_Script exits with a non-zero status, THEN THE Release_Chain SHALL exit with a non-zero status.
8. THE repository SHALL contain no file under `.github/workflows/`.
9. THE repository SHALL contain no `.pre-commit-config.yaml` file.
10. WHERE the `hatch-static-analysis` environment is unusable, THE Lint_Script SHALL obtain Ruff from the Pinned_Ruff_Version in Dev_Dependencies.

### Requirement 5: Formatting pass verified behavior-preserving

**User Story:** As a maintainer, I want the formatting pass verified as behavior-preserving, so that adopting the Formatter carries no functional risk.

#### Acceptance Criteria

1. THE Formatter SHALL rewrite every file it reports as unformatted, excluding Generated_Models.
2. WHEN `ruff format --check` runs after the formatting pass, THE Formatter SHALL report zero files needing changes.
3. WHEN `ruff check` runs after the formatting pass, THE Linter SHALL report zero findings.
4. WHEN the Test_Suite runs after the formatting pass, THE Test_Suite SHALL report zero failures and zero errors on both the Python 3.11 and the Python 3.12 matrix cell, and SHALL report no test that passed before the formatting pass as failing after it. The passing count SHALL be greater than or equal to the pre-pass baseline of 261 on each cell; it is expected to exceed 261, because this feature adds test modules of its own.
5. WHEN the Type_Check runs after the formatting pass, THE Type_Check SHALL report zero errors.
