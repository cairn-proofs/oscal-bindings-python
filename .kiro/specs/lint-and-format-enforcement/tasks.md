# Implementation Plan: lint-and-format-enforcement

## Overview

The deliverable is configuration plus a one-time mechanical reformat, so the plan follows the design's three-commit sequence and keeps each commit independently reviewable:

1. **Config plus dead-suppression cleanup** — the pin, `select`, `ignore`, `extend-exclude`, `force-exclude`, the four `per-file-ignores` entries, the `lint` script, `lint` in `release`, removal of `lint.exclude`, and deletion of the six unused `# noqa: F401` directives (§4a). The directive deletion rides in this commit, not the formatting one, so commit 2 stays a pure formatter diff. This step is **expected to end with `hatch run lint` failing.** That failure is the baseline measurement, not a defect: the formatter has never run over this tree, so format findings are certain and residual lint findings are likely. Do not chase green here.
2. **The formatting pass alone** — `hatch run ruff format .`, committing only what the formatter wrote.
3. **Evidence** — property tests, example config tests, integration and smoke checks, the Req 3.5 regeneration digest-and-diff, and the `DEVELOPING.md` note.

Language: Python (existing repo, 3.11/3.12 matrix). Tests use `pytest` + `hypothesis`, both already available to `hatch test`; config is parsed with stdlib `tomllib` (no new dependency).

Two standing constraints from the design, carried into the task text below because they are the two ways this feature can be "completed" while being wrong:

- **Reconciliation rule.** Residual findings in non-generated source are resolved by fixing the source when the fix is mechanical and local (unused import, `pathlib` swap, `TRY300`'s `else` block). Widening a `per-file-ignores` glob or dropping a family from `select` to reach zero is **not an available move** — it re-creates the silent weakening the selection exists to prevent. If a residual finding is genuinely not worth fixing, it goes back to the user as a requirements question.
- **Properties are pure config functions.** All three properties read the parsed `pyproject.toml` and quantify over generated path/code strings. No subprocess, no Ruff invocation, no filesystem walk — which is what makes `max_examples >= 100` cheap enough to be the default.

## Tasks

- [x] 1. Step 1 — configuration only (commit 1)

  - [x] 1.1 Write the full Ruff and Hatch configuration into `pyproject.toml`
    - Add `ruff==0.16.8` to `[tool.hatch.envs.default.dependencies]` (exact specifier, not `~=` or `>=`)
    - Under `[tool.ruff]`: keep `line-length = 88` and `target-version = "py311"`; add `extend-exclude = ["./build", ".hatch", "src/oscal_bindings/v1/models.py", "*.md"]` and `force-exclude = true`
    - The `"*.md"` entry is not optional on this pin: Ruff 0.16 has `*.md` in its default `include` and formats Markdown code blocks by default, so without it `ruff format .` rewrites the ```python blocks in `README.md` and `.agents/summary/interfaces.md`, and `ruff check .` raises `F821`/`I001`/`T201` on doc fragments. `.kiro/` is not gitignored, so its spec Markdown is walked too (Req 1.8)
    - **Remove** `exclude` from `[tool.ruff.lint]` — the patterns move to the top level so both engines read them; this is a fix for a live defect, not a tidy-up
    - Use `extend-exclude`, never `exclude`: `exclude` would replace Ruff's 20 defaults (`.git`, `.venv`, `.mypy_cache`, `_build`, `dist`, `node_modules`, …). Note the defaults list `_build`, not `build`, and do not include `.hatch` — both existing entries are load-bearing, not decorative
    - Under `[tool.ruff.lint]`: add the explicit `select` family list from design §2 and `ignore = ["ISC001"]` with the formatter-conflict comment. `ISC` stays selected so `ISC002`/`ISC003` remain active
    - Under `[tool.ruff.lint.per-file-ignores]`, **four** entries, each with its explanatory comment:
      ```toml
      # Tests can use magic values, assertions, and relative imports
      "tests/**/*" = ["PLR2004", "S101", "TID252", "PLC0415", "INP001"]
      # Build/codegen scripts report progress and errors on stdout/stderr
      "scripts/**/*" = ["T201"]
      # Inline exception messages. A deferral, not a blessing: these findings flag a
      # real API weakness (typed parsers raise a flat OscalParseError on a document-type
      # mismatch), to be fixed with a dedicated WrongDocumentTypeError.
      "src/oscal_bindings/v1/**" = ["EM101", "EM102", "TRY003"]
      # PEP 484 explicit re-export idiom (`import X as X`) — correct in a compat shim
      "src/oscal_bindings/__init__.py" = ["PLC0414"]
      ```
    - The `tests/**/*` entry preserves the Req 1.6 list as a prefix and adds `INP001` (same exemption, same reason)
    - The `v1/**` entry names **exactly** `EM101`, `EM102`, `TRY003` and no fourth code, and MUST carry the deferral comment (the planned `WrongDocumentTypeError`): the entry defers a real API weakness, it does not bless the flagged pattern (Req 2.4). Without that comment the entry reads as an endorsement
    - The `PLC0414` entry is scoped to the single file `src/oscal_bindings/__init__.py`, not `**/__init__.py` — the flagged line is the PEP 484 `import X as X` explicit-re-export idiom, which is correct in a compatibility shim and nowhere else in this tree (Req 2.5)
    - Keep globs exactly as narrow as written — `scripts/**/*` not `**/*`, `src/oscal_bindings/v1/**` not `src/oscal_bindings/**` (the shim and its alias modules must stay covered), the `PLC0414` entry as an exact path
    - Table name stays `per-file-ignores`, not `extend-per-file-ignores`; there is no Hatch base to extend
    - Leave `[tool.ruff.format]` and `lint.isort.known-first-party` unchanged
    - Add `lint = ["ruff check .", "ruff format --check ."]` under `[tool.hatch.envs.default.scripts]`; Hatch aborts a script list on first non-zero exit and propagates the status
    - Set `release = ["generate", "lint", "typing", "hatch test --all --cover", "docs"]` — `lint` after `generate`, no stage dropped
    - Add no `[tool.hatch.envs.hatch-static-analysis]` table and no `extend = "ruff_defaults.toml"` line
    - _Requirements: 1.1, 1.2, 1.3, 1.5, 1.6, 1.7, 1.8, 2.1, 2.2, 2.3, 2.4, 2.5, 2.7, 3.1, 3.2, 3.3, 3.5, 4.1, 4.2, 4.5, 4.6, 4.10_

  - [x] 1.2 Delete the six unused `# noqa: F401` directives
    - Sites, exactly six and no others: `src/oscal_bindings/__init__.py` (2), `src/oscal_bindings/extensions/__init__.py` (1), `src/oscal_bindings/parser.py` (1), `src/oscal_bindings/v1/__init__.py` (2)
    - Only the trailing comment is deleted: `from .v1 import parse_oscal  # noqa: F401` becomes `from .v1 import parse_oscal`. No import removed, no name renamed, no re-export changed, no `__all__` entry touched
    - The directives are dead: `__all__` already satisfies `F401`'s re-export condition, so they suppress nothing at any version under any configuration. `RUF100` reports them (Req 2.6)
    - **Bounded to exactly those six sites.** Req 2.6 names the files and the counts; this task has no room to expand into a tidy-up pass, an unused-import sweep, or a comment cleanup elsewhere in the tree. If `RUF100` fires anywhere else under the pin, that is a step-1 reconciliation item for task 1.3, not more deletions here
    - This belongs in **commit 1** (config + dead-suppression cleanup), not commit 2 — commit 2 must stay a pure formatter diff a reviewer can reproduce by re-running `ruff format`
    - _Requirements: 2.6, 2.8_

  - [x] 1.3 Record the baseline finding list from the failing `hatch run lint`
    - Run `hatch run lint > ./tmp/lint-baseline.log 2>&1; echo "EXIT: $?"` and expect a non-zero exit — this is the measured baseline, not a failure to fix in this step
    - Because the script aborts on the first non-zero command, also capture `hatch run ruff check . > ./tmp/ruff-check-baseline.log 2>&1` and `hatch run ruff format --check . > ./tmp/ruff-format-baseline.log 2>&1` separately so both engines' findings are on record before any source changes
    - Confirm Ruff resolved this repo's config, not Hatch's: the pinned version runs and `line-length` is 88, not 120
    - **The baseline MUST be re-measured against the pinned Ruff.** The 418-finding figure in design §2 came from Ruff 0.4.5 in the Hatch static-analysis environment, not the proposed 0.16.8: `TCH` was renamed `TC`, and several `FURB`/`PERF` rules were preview on 0.4.5 and are stable — therefore selected — on 0.16.8. Expect both codes and counts to differ. Anything that compares against 418 is comparing against the wrong tool, so treat §2's table as shape only
    - Summarize the residual lint findings by code and path. Classify each as (a) a code Req 2 accepts (`T201`, `INP001`, `EM101`, `EM102`, `TRY003`, `PLC0414`, plus the Req 1.6 `tests/**/*` list), (b) mechanically fixable locally, or (c) needs a requirements decision
    - **Open item to resolve in this step: `PLR0912` / `PLR0915` on `scripts/postprocess_models.py:main()`** (19 branches, 82 statements under 0.4.5). The design judged the linear nine-phase pipeline acceptable, but **no requirement accepts these codes anywhere**, so a judgment recorded in the design is not authorization. If either fires under the pin, step 1 must either add a scoped `per-file-ignores` entry for it — with a comment stating the reason — or escalate to the user. It may not be left as an unexplained residual finding, and it may not be resolved by splitting `main()` (that would scatter the phase ordering across nine call sites)
    - This task changes no source and commits nothing beyond step 1's config and the task 1.2 deletions
    - _Requirements: 1.3, 1.4, 4.3, 4.4, 4.10_

- [x] 2. Checkpoint — baseline recorded, config committed
  - `hatch run lint` failing here is the expected state. Confirm the baseline logs exist and the residual findings are classified before touching any further source. If any finding falls in class (c) — including the `PLR0912`/`PLR0915` open item — ask the user rather than widening a glob or trimming `select`.
  - Confirm the baseline was measured against the pinned Ruff, not against §2's 0.4.5 numbers, and that the only source change in this commit is the six `# noqa: F401` deletions.
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Step 2 — the formatting pass (commit 2)

  - [x] 3.1 Run the formatter and commit only what it wrote
    - Run `hatch run ruff format .` over the tree
    - Verify `git diff --stat` does **not** name `src/oscal_bindings/v1/models.py` and names no `.md` file. Either one means an exclusion is wrong — stop, fix step 1's config, and restart this step
    - Cross-check the changed-file list against `git ls-files '*.py'` minus the generated module (14 tracked at design time; use whatever the command returns)
    - No hand edits, renames, or docstring touch-ups ride along. A reviewer must be able to re-run the formatter on this commit and get an empty diff
    - Confirm `hatch run ruff format --check .` now reports zero files and leaves the working tree unchanged
    - _Requirements: 1.8, 4.2, 5.1, 5.2_

  - [x] 3.2 Reconcile residual lint findings in non-generated source
    - Re-run `ruff check .` after formatting; some baseline findings disappear with the reformat
    - Residual findings must reduce to exactly the codes accepted by Req 2.1, 2.2, 2.3, and 2.5 — `T201` under `scripts/`, `INP001` under `tests/`, `EM101`/`EM102`/`TRY003` under `src/oscal_bindings/v1/**`, `PLC0414` at `src/oscal_bindings/__init__.py` — plus the `tests/**/*` list from Req 1.6 (`PLR2004`, `S101`, `TID252`, `PLC0415`). All of them covered by the four `per-file-ignores` entries from task 1.1, and nothing else
    - Named mechanical fix, not left to discovery: **`TRY300` at `src/oscal_bindings/v1/parser.py:114` and `tests/support/corpus.py:147`** — move the statement out of the `try` body into an `else` block. No logic change, no ignore entry; this is the reconciliation rule's "mechanical and local" case
    - Fix anything else in the source when the fix is mechanical and local
    - Do **not** widen a `per-file-ignores` glob and do **not** drop a `select` family to reach zero — if a finding is genuinely not worth fixing, raise it with the user as a requirements question
    - Leave the `print(` calls in `scripts/`, the absence of `tests/__init__.py`, and the inline exception messages under `src/oscal_bindings/v1/` untouched (Req 2.8)
    - End state: `hatch run lint` exits 0 on a clean tree
    - _Requirements: 2.1, 2.2, 2.3, 2.5, 2.7, 2.8, 5.3_

- [x] 4. Step 3 — evidence (commit 3)

  - [x] 4.1 Create `tests/test_prop_lint_config.py` with the config loader and the glob-matching helper, covered by example tests
    - Module-scoped helper that reads `pyproject.toml` once via `tomllib` and returns the parsed tables; no subprocess, no Ruff invocation
    - Implement the glob-matching helper once, using the semantics Ruff documents for `per-file-ignores` patterns, to be shared by Properties 1 and 2
    - Cover the helper itself with example tests: `scripts/**/*` matches `scripts/postprocess_models.py` and not `src/scripts/x.py` or `scripts_old/x.py`; `tests/**/*` matches `tests/test_parser.py` and not `tests_extra/y.py` or `test/y.py`; `src/oscal_bindings/v1/**` matches `src/oscal_bindings/v1/parser.py` and `src/oscal_bindings/v1/extensions/document.py` but **not** `src/oscal_bindings/parser.py`, `src/oscal_bindings/extensions/__init__.py`, or `src/oscal_bindings/v1_2/x.py`; the exact-path `src/oscal_bindings/__init__.py` entry matches only itself and no other `__init__.py` in the tree
    - This helper is the one piece of real logic in the module — an incorrect helper would make both properties vacuously pass, which is the single way this suite could lie
    - Tag: **Feature: lint-and-format-enforcement**
    - _Requirements: 2.1, 2.2, 2.3, 2.5_

  - [x] 4.2 Write property test for engine-symmetric exclusion
    - **Property 1: For any repo-relative file path, the exclusion verdict is identical for the linter and the formatter — no path is excluded from one engine and walked by the other. Equivalently, the config declares no engine-scoped exclusion key (`lint.exclude`, `lint.extend-exclude`, `format.exclude`, `format.extend-exclude`).**
    - **Validates: Requirements 1.7, 3.1, 3.2, 3.3**
    - Generate repo-relative POSIX paths from a segment alphabet that includes the near-miss trees — `scripts`, `script`, `scripts_old`, `src/scripts`, `tests`, `tests_extra`, `test`, `src/oscal_bindings/v1` — with varied depth and both `.py` and non-`.py` leaves
    - The alphabet must also produce the shadow paths that sit just outside the widened `src/oscal_bindings/v1/**` glob, since those are the paths an over-broad glob silently captures: the compat-shim alias modules `src/oscal_bindings/extensions/__init__.py` and `src/oscal_bindings/parser.py`, a `v1`-lookalike directory such as `src/oscal_bindings/v1_2/x.py`, and `src/oscal_bindings/v1/__init__.py` as a positive case. Shared with Property 2, where the shadow paths carry the weight
    - Pin `@example` cases for `src/oscal_bindings/v1/models.py`, `./build`, and `.hatch` so the entries that matter are never merely probable
    - `max_examples >= 100`; pure config read, no subprocess
    - Tag: **Feature: lint-and-format-enforcement, Property 1: Exclusion is engine-symmetric**

  - [x] 4.3 Write property test for exactly-scoped per-file ignores
    - **Property 2: For any repo-relative Python path and any code in `{T201, INP001, EM101, EM102, TRY003, PLC0414, PLR2004, S101, TID252, PLC0415, PLR0912, PLR0915}` — twelve codes — that code is ignored at that path if and only if the path matches a `per-file-ignores` pattern naming it (`INP001` is named by both `tests/**/*` and `scripts/**/*`; `PLR0912`/`PLR0915` only by the exact path `scripts/postprocess_models.py`); for any path outside those patterns every code in the set remains active.**
    - **Validates: Requirements 1.6, 2.1, 2.2, 2.3, 2.5, 2.7, 2.9**
    - Reuse the shared glob helper from task 4.1
    - Same path generator as Property 1, with the shadow paths carrying the weight here: `src/scripts/x.py`, `scripts_old/x.py`, `tests_extra/y.py`, `src/oscal_bindings/v1_2/x.py`, and — the case the widened `v1/**` glob makes load-bearing — the compat-shim alias modules `src/oscal_bindings/extensions/__init__.py` and `src/oscal_bindings/parser.py`, which must **not** inherit the `EM101`/`EM102`/`TRY003` exemption. An entry written `src/oscal_bindings/**` would satisfy Req 2.1–2.3 while silently violating 2.7, and a positive-only check passes in that state
    - Pin `@example` cases for the exact literal paths `scripts/postprocess_models.py`, `src/oscal_bindings/v1/parser.py`, and `src/oscal_bindings/__init__.py` — the last is the sole `PLC0414` path, so a false negative there is invisible otherwise. Also pin a second file under `scripts/` (e.g. `scripts/other.py`), which must inherit `T201`/`INP001` but **not** `PLR0912`/`PLR0915`
    - Negative direction: sample codes from the selected families that appear in no ignore entry and assert they are never reported as ignored at any path. The code generator must cover `EM102` and `PLC0414` explicitly — both are governed codes with narrowly scoped entries, and omitting them under-checks the two scopings most likely to be written too broadly
    - `max_examples >= 100`
    - Tag: **Feature: lint-and-format-enforcement, Property 2: Per-file ignores are exactly scoped**

  - [x] 4.4 Write property test for selection coverage of governed codes
    - **Property 3: For every code in the accepted set of Property 2 — the same twelve codes `{T201, INP001, EM101, EM102, TRY003, PLC0414, PLR2004, S101, TID252, PLC0415, PLR0912, PLR0915}`, spanning seven rule families — some entry of `lint.select` is a prefix of that code, so the code is reachable by the linter and its `per-file-ignores` entry is meaningful rather than vacuous.**
    - **Validates: Requirements 1.2, 2.7**
    - Sample codes from the accepted set; assert prefix coverage against the parsed `select` list, accounting for `ignore` not removing a family wholesale. `EM102` needs `EM` selected and `PLC0414` needs `PL` selected — the same families `EM101` and `PLC0415` already depend on, so a trimmed `select` fails here once for several codes
    - This is the executable guard against reaching zero findings by trimming `select`
    - `max_examples >= 100`
    - Tag: **Feature: lint-and-format-enforcement, Property 3: The selection covers every governed code**

  - [x] 4.5 Write example config tests in `tests/test_lint_config.py`
    - Exactly one `ruff==X.Y.Z` entry in the default env dependencies, using an exact specifier (Req 1.1, 4.10)
    - `line-length == 88`, `target-version == "py311"`, `format.quote-style == "double"`, `format.indent-style == "space"`, `lint.isort.known-first-party == ["oscal_bindings"]` (Req 1.5)
    - The Req 1.6 codes are all present on the `tests/**/*` entry (Req 1.6)
    - The `src/oscal_bindings/v1/**` entry names exactly `EM101`, `EM102`, `TRY003` and no other code — assert set equality, not containment, since a fourth code is the widening Req 2.3 forbids (Req 2.3)
    - The `PLC0414` entry key is exactly `src/oscal_bindings/__init__.py` and no other entry names `PLC0414` (Req 2.5)
    - The `scripts/**/*` entry is exactly `{T201, INP001}` (Req 2.1); the `scripts/postprocess_models.py` entry is exactly `{PLR0912, PLR0915}` and no other entry names either code (Req 2.9)
    - No `# noqa: F401` remains at the six sites named in Req 2.6 — `src/oscal_bindings/__init__.py`, `src/oscal_bindings/extensions/__init__.py`, `src/oscal_bindings/parser.py`, `src/oscal_bindings/v1/__init__.py` (Req 2.6)
    - ~~The `v1/**` entry carries its deferral comment, checked by a raw-text read of `pyproject.toml` (a TOML parser discards comments) (Req 2.4)~~ *(Removed after delivery: it asserted a comment's wording, which pinned a backlog ID that no longer exists in the repo. See the amendment on Req 2.4.)*
    - `src/oscal_bindings/v1/models.py` appears in the top-level exclusion patterns (Req 3.3)
    - `"*.md"` appears in the top-level exclusion patterns (Req 1.8)
    - The generated module contains no `# noqa`, `# fmt: off`, or `# fmt: on` (Req 3.4)
    - The `lint` script list contains a `ruff check` command and a `ruff format --check` command, and is defined under `[tool.hatch.envs.default.scripts]` (Req 4.1, 4.2, 4.10)
    - `release` contains `lint` **and** still contains `generate`, `typing`, `hatch test --all --cover`, `docs` — the guard against a hand-edited list that adds a stage and drops one (Req 4.5, 4.6)
    - No `extend = "ruff_defaults.toml"` line and no `[tool.hatch.envs.hatch-static-analysis]` table (Req 1.3)
    - `.github/workflows/` and `.pre-commit-config.yaml` do not exist (Req 4.8, 4.9)
    - `tests/__init__.py` does not exist and `scripts/postprocess_models.py` still contains `print(` calls (Req 2.8)
    - _Requirements: 1.1, 1.3, 1.5, 1.6, 1.8, 2.1, 2.3, 2.4, 2.5, 2.6, 2.8, 2.9, 3.3, 3.4, 4.1, 4.2, 4.5, 4.6, 4.8, 4.9, 4.10_

- [x] 5. Step 3 — verification and documentation

  - [x] 5.1 Run the integration and smoke checks and record the results
    - `hatch run lint` exits 0 on a clean tree (Req 2.8, 5.2, 5.3)
    - Introduce a temporary violation, confirm `hatch run lint` exits non-zero and `hatch run release` stops at `lint`, then revert it (Req 4.3, 4.4, 4.7)
    - Working tree unchanged after `ruff format --check .` (Req 4.2)
    - `ruff check src/oscal_bindings/v1/models.py` and `ruff format --check src/oscal_bindings/v1/models.py` — explicitly named, must report nothing; this is the `force-exclude` check (Req 3.1, 3.2)
    - `hatch test --all` — zero failures and zero errors on both matrix cells, no test that passed before the formatting pass failing after it, and a passing count at or above the 261 floor (Req 5.4 as reworded; the count is evidence, not the target)
    - `hatch run typing` reports zero errors (Req 5.5)
    - Redirect each expensive run to `./tmp/*.log` with its exit code so the output can be re-read without re-running
    - _Requirements: 2.8, 3.1, 3.2, 4.2, 4.3, 4.4, 4.7, 5.2, 5.3, 5.4, 5.5_

  - [x] 5.2 Run the Req 3.5 regeneration digest-and-diff sequence
    - From a clean tree: `shasum -a 256 src/oscal_bindings/v1/models.py > /tmp/models.before`
    - `hatch run generate`
    - `shasum -a 256 -c /tmp/models.before` must pass, and `git diff --exit-code -- src/oscal_bindings/v1/models.py` must exit 0 — the diff is the authoritative check, the digest makes a failure legible
    - `grep -c -e '# noqa' -e '# fmt: off' -e '# fmt: on' src/oscal_bindings/v1/models.py` must be 0 (Req 3.4) — in-file suppression cannot work here in principle, since the next `generate` erases it
    - Manual/release-time check only; it invokes the full codegen pipeline and does not belong in the unit suite
    - _Requirements: 3.4, 3.5_

  - [x] 5.3 Add the `DEVELOPING.md` note on the enforcement entry point
    - One line: `hatch run lint` is the lint/format entry point; `hatch fmt` and `hatch check code` are not used by this repo
    - The `hatch-static-analysis` environment stays broken and unrepaired on purpose — repairing it would restore a second, differently configured lint path (Hatch's ruleset, line length 120). There is nothing in `pyproject.toml` to remove; the documentation is what stops someone "fixing" it later
    - _Requirements: 1.3, 4.10_

- [x] 6. Final checkpoint — full release chain
  - Run `hatch run release` end to end and confirm every stage passes in order: `generate`, `lint`, `typing`, `hatch test --all --cover`, `docs`
  - Clean up `./tmp/*.log` and any temporary violation files
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP. Note that tasks 4.1–4.5 are the evidence layer for this feature: skipping them leaves the config with no regression guard against the exact silent-weakening failure mode the design is built to prevent.
- Each task references specific requirements for traceability.
- The three commits map to tasks 1.x, 3.x, and 4.x + 5.x respectively.
- Task 1.2 is the one task in this plan that edits hand-written source outside the formatter's control, and it is bounded to deleting six trailing comments (Req 2.6). Keeping it in commit 1 is what lets a reviewer verify commit 2 by re-running `ruff format` and getting an empty diff.
- The `PLR0912`/`PLR0915` item in task 1.3 is an open decision, not a settled exemption: the design judged the nine-phase `main()` acceptable, but no requirement accepts those codes anywhere, so resolving it requires either a commented scoped ignore or a user decision.

### One requirement added during review

- **Req 1.8 — Markdown exclusion.** Verified against Ruff 0.16's release notes and the settings reference: `*.md` is in the default `include` list and 0.16.0 made Markdown code-block formatting a default. `ruff format .` and `ruff check .` therefore walk documentation, which neither the earlier design nor this plan accounted for. Handled by adding `"*.md"` to `extend-exclude` in task 1.1, asserted in task 4.5, and checked in task 3.1's diff review.

### Two requirements reworded during review

Both items flagged by the design and tasks phases were folded back into `requirements.md`, so no task satisfies a criterion only by reinterpreting it:

- **Req 5.4** now reads as a no-regression assertion — zero failures and zero errors on both matrix cells, no test that passed before the formatting pass failing after it, and 261 as a floor rather than an exact count. Task 5.1 checks exactly that. The glossary's `Test_Suite` entry was updated to match.
- **Req 1.4** now states what is checkable from one checkout: no input to the linter is machine-dependent, every one of them read from `pyproject.toml` at the commit under test. The cross-machine consequence is marked as structurally held. Task 4.5's example tests assert the inputs; no task claims to verify the two-machine observation empirically.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3"] },
    { "id": 2, "tasks": ["3.1"] },
    { "id": 3, "tasks": ["3.2"] },
    { "id": 4, "tasks": ["4.1", "4.5", "5.3"] },
    { "id": 5, "tasks": ["4.2"] },
    { "id": 6, "tasks": ["4.3"] },
    { "id": 7, "tasks": ["4.4"] },
    { "id": 8, "tasks": ["5.1", "5.2"] }
  ]
}
```
