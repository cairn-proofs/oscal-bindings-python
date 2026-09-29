# Design Document

## Overview

The deliverable is configuration, not code: a Ruff pin, a rule selection, an exclusion set, and one Hatch script wired into the existing `release` chain. No module is added to `src/`, no runtime behavior changes, and no CI or hook infrastructure appears. The source churn is a one-time mechanical reformat of the hand-written Python files (14 tracked at design time) plus the deletion of six unused `# noqa: F401` directives (§4a) — Markdown is held out of scope by the `*.md` exclusion in §3.

Four facts about Ruff drive the whole design, and each was verified against Ruff's documentation and release notes rather than assumed:

1. **Exclusion placement decides engine coverage.** Top-level `[tool.ruff]` `exclude` / `extend-exclude` are documented as "a list of file patterns to exclude from formatting and linting." `lint.exclude` and `format.exclude` are each engine-scoped. The current config puts the patterns under `[tool.ruff.lint]`, so the formatter has never honored them.
2. **Exclusions do not survive an explicitly named path by default.** With `force-exclude = false` (the default), a path passed directly on the command line is processed even if it matches `exclude` — intentional, matching Black. This matters for the generated module, which must never be rewritten.
3. **`extend-exclude` is additive; `exclude` replaces.** Ruff's default exclusion list already covers `.git`, `.venv`, `.mypy_cache`, `_build`, `dist`, `node_modules`, and friends (20 entries). Writing top-level `exclude` would silently drop all of them. Note that the defaults cover `_build`, **not** `build`, and do not cover `.hatch` — so both existing entries are load-bearing.
4. **On the pinned version, `.` is not "the Python files."** Ruff's default `include` list is `["*.py", "*.pyi", "*.pyw", "*.ipynb", "*.md", "**/pyproject.toml", "**/ruff.toml", "**/.ruff.toml"]`, and 0.16.0 added Markdown code-block formatting *on by default*. So `ruff format .` and `ruff check .` walk every `.md` file in the tree that isn't gitignored, and format or lint the Python blocks inside it. This repo has 13 tracked Markdown files plus untracked-but-unignored `.kiro/specs/**/*.md`; `README.md` and `.agents/summary/interfaces.md` carry ```python blocks today. See §3 for the decision.

## Architecture

Enforcement is a single local path with no alternative entry point:

```
hatch run lint          hatch run release
      |                        |
      |                  generate → lint → typing → hatch test --all --cover → docs
      v                               |
[tool.hatch.envs.default]             |
  dependencies: ruff==0.16.8  <-------+
  scripts.lint:
    1. ruff check .
    2. ruff format --check .
      |
      v
[tool.ruff]                    <- pin-owned rules, read by BOTH engines
  extend-exclude, force-exclude
[tool.ruff.lint]
  select, per-file-ignores, isort
[tool.ruff.format]
  quote-style, indent-style
```

What is deliberately absent: `.github/workflows/` (Req 4.8), `.pre-commit-config.yaml` (Req 4.9), any `[tool.hatch.envs.hatch-static-analysis]` table, and any `extend = "ruff_defaults.toml"` line. The last two are what keep Hatch's bundled ruleset out of the resolution path (Req 1.3).

### Decision: reuse the `default` environment, no dedicated lint env

Ruff goes into `[tool.hatch.envs.default.dependencies]` beside `pytest`, `mypy`, `datamodel-code-generator`, and `pdoc`.

A dedicated `[tool.hatch.envs.lint]` with `skip-install = true` would build faster in isolation, but nothing in this repo runs lint in isolation — `release` already materializes the default env for `generate`, `typing`, and `docs`, so a second env is a second thing to provision for zero saved work. It also matches how `typing` already works: mypy is a default-env dependency and `typing` is a default-env script. One env, one lockfile, one provisioning step.

Consequence for Req 4.10: because `lint` is a `default`-env script, the Ruff it invokes is the pinned one from that env's dependencies. The broken `hatch-static-analysis` environment is never entered.

### Decision: `lint` runs before `typing` and the tests

```toml
release = ["generate", "lint", "typing", "hatch test --all --cover", "docs"]
```

After `generate`: the chain's first act is to bring the tree to its canonical generated state, and everything downstream verifies that state. Putting `lint` first would check a tree that `generate` might then change.

Before `typing` and the tests: Ruff over 14 files is sub-second; mypy plus a two-cell parallel matrix of 261 tests is tens of seconds. Cheapest gate first is the standard ordering, and a lint finding is almost always faster to read than a mypy cascade. The ordering carries no correctness weight — every stage must pass — so the argument is purely feedback latency.

## Components and Interfaces

### 1. The Ruff pin

```toml
[tool.hatch.envs.default]
python = "3.12"
dependencies = ["pytest", "mypy", "datamodel-code-generator[http]", "pdoc", "ruff==0.16.8"]
```

`0.16.8` is the current release; `==` rather than `~=` or `>=` because both engines are version-sensitive in ways that matter here. Ruff 0.15 shipped a revised formatter style guide, and 0.16 replaced the default rule set with a much broader one (roughly 413 rules across 34 categories). A floating specifier would let either change land as a mystery diff or a mystery finding count.

A correction to an earlier reading of the evidence: the ~61 → 136 growth in finding count between two commits was **not** a tooling-drift event. The Ruff binary in the `hatch-static-analysis` environment is **0.4.5**, Hatch-pinned and unmoved across both measurements. The count grew because the source grew — the preceding feature (`major-version-namespace`) added six test modules. Nothing about that number implicates a ruleset change, and the design should not claim it does.

The pin remains the right decision on its own merits, which are forward-looking rather than historical: 0.15's formatter style-guide revision and 0.16's default-ruleset replacement are both real and both would land silently under a floating specifier, and nothing in the repository today records which Ruff version produced a given result. A finding count with no version attached is not evidence of anything — that is the gap the pin closes, and it is why Requirement 1.4 is phrased as "no input machine-dependent" rather than as a reproducibility observation.

The pin is also what makes Req 1.4 hold. Same commit plus same Ruff version plus a selection owned by `pyproject.toml` leaves nothing machine-dependent.

Bumping the pin is then a deliberate, reviewable act: change the version, run `hatch run lint`, absorb whatever new findings or format changes arrive in that commit.

### 2. The rule selection

```toml
[tool.ruff.lint]
select = [
  "F", "E", "W",        # pyflakes, pycodestyle
  "I",                  # isort
  "N",                  # pep8-naming
  "UP",                 # pyupgrade
  "B",                  # flake8-bugbear
  "A",                  # flake8-builtins
  "C4",                 # flake8-comprehensions
  "DTZ",                # flake8-datetimez
  "EM",                 # flake8-errmsg        <- keeps EM101 active
  "EXE", "FA", "ICN", "ISC", "PIE", "PYI", "PT", "RSE", "RET", "SLF", "SIM",
  "INP",                # flake8-no-pep420     <- keeps INP001 active
  "T20",                # flake8-print         <- keeps T201 active
  "TID",                # flake8-tidy-imports  <- keeps TID252 active
  "TC",                 # flake8-type-checking
  "S",                  # flake8-bandit        <- keeps S101 active
  "ARG", "PTH", "PGH", "FLY", "PERF", "FURB", "RUF",
  "PL",                 # pylint               <- keeps PLR2004, PLC0415 active
  "TRY",                # tryceratops          <- keeps TRY003 active
]
ignore = ["ISC001"]     # implicit-str-concat: documented formatter conflict
```

The selection is deliberately broad. Requirements 2.7 and 1.6 name ten codes — `T201`, `INP001`, `EM101`, `EM102`, `TRY003`, `PLC0414`, `PLR2004`, `S101`, `TID252`, `PLC0415` — that must stay live outside their per-file ignores, and those ten span seven separate rule families. Any selection that keeps all ten active is necessarily wide, so `select = ["E", "F"]` is not on the table. Choosing a narrower set that happened to drop, say, `TRY` would make the `TRY003` per-file ignore in Requirement 2.3 vacuous: the config would still read as if the rule were enforced everywhere else, and it would not be. That is the silent weakening this design is specifically avoiding, and the "selection covers the governed codes" property below is the executable guard against it.

Four families are excluded on purpose, each for a stated reason rather than by omission:

| Family | Why not |
|---|---|
| `D` (pydocstyle) | Would demand docstrings on every public symbol across `src/`. A large source rewrite, which Requirement 2 exists to avoid. |
| `ANN` (annotations) | Overlaps `mypy`, already run by `typing`. Two tools arguing about the same thing. |
| `COM` (commas), `Q` (quotes) | Documented as conflicting with the formatter, which already owns trailing commas and quote style. |
| `FBT` (boolean trap) | An API-design opinion, not a defect class; would flag existing signatures. |

`ISC001` is selected-then-ignored rather than dropping `ISC` entirely, so `ISC002`/`ISC003` stay active. `E501` stays in: the formatter handles most long lines, and the residue is worth seeing.

**Empirical reconciliation is part of implementation, not design.** This selection is a proposal until the linter runs against it. The reconciliation rule, stated in advance so the task is not a judgment call: after the formatting pass, the residual findings in non-generated source must be exactly the codes Requirement 2 accepts. Anything else is resolved by fixing the source when the fix is mechanical and local (an unused import, a `pathlib` swap). Widening `per-file-ignores` or removing a family from `select` to reach zero is not an available move, because it re-creates the weakening the selection was chosen to prevent — if a residual finding is genuinely not worth fixing, it goes back to the user as a requirements question.

#### The measured baseline

A run over `scripts/`, `src/`, and `tests/` with the `select` list above and `src/oscal_bindings/v1/models.py` excluded reported **418 findings**. The shape of that number matters more than the number:

| Code | Count | Note |
|---|---:|---|
| `E501` | 408 | Line length. The formatter absorbs most of these by rewrapping; the residue is long string literals and URLs it will not split — `v1/extensions/validate_element.py:37,51,67` and `v1/parser.py:177`. |
| `S101` | 262 | `assert` in tests. Already covered by the `tests/**/*` entry. |
| — | tail | `T201`, `INP001`, `EM101`/`EM102`/`TRY003`, `PLC0414`, `RUF100`, plus the two items named under "Deliberate non-actions" below. |

(The two headline counts overlap: a long `assert` line reports under both codes.)

**These counts are from Ruff 0.4.5, not the proposed 0.16.8 pin, and the step-1 baseline must be re-measured against the pinned version.** They are indicative of shape, not a target to reconcile against. Rule availability differs materially between the two versions: `TCH` was renamed `TC`, and several `FURB` and `PERF` rules were in preview on 0.4.5 and are stable (and therefore selected) on 0.16.8. Expect the re-measured list to differ in both codes and counts. Anything in step 1 that compares against 418 is comparing against the wrong tool.

#### Deliberate non-actions

Two findings from the 0.4.5 run are recorded here as judged-and-left rather than missed, so a later reader does not re-derive them as oversights:

- **`PLR0912` / `PLR0915` on `scripts/postprocess_models.py:main()`** (19 branches, 82 statements). *(Resolved during implementation: the finding is on `collapse_scalar_root_models()`, not `main()`, and is accepted by the exact-path entry in §4 under Req 2.9. The text below is the original step-1 framing.)* The complexity signal is legitimate — that function is genuinely large. It is judged acceptable because `main()` reads as a linear nine-phase pipeline, and the phases must run in that order; splitting it into helpers would scatter the ordering that is the function's main comprehensibility asset across nine call sites and their signatures. This is not a closed question: **if either code fires under the pinned version, step 1 must either add a scoped `per-file-ignores` entry for it or escalate the decision.** It is a named open item for step 1's reconciliation, not a settled exemption, because no requirement currently accepts these codes anywhere.
- **`TRY300` at `v1/parser.py:114` and `tests/support/corpus.py:147`.** The fix is mechanical and local — move the `return` out of the `try` body into an `else` block, no logic change — so it falls squarely under the reconciliation rule's "fix when mechanical and local" and gets no ignore entry.

### 3. Exclusions

```toml
[tool.ruff]
line-length = 88
target-version = "py311"
extend-exclude = ["./build", ".hatch", "src/oscal_bindings/v1/models.py", "*.md"]
force-exclude = true
```

Five decisions are packed into those two lines.

**Moving the patterns out of `[tool.ruff.lint]` is a fix, not a tidy-up.** Today `exclude = ["./build", ".hatch"]` sits under the lint table, so `ruff format` has never seen it. Nobody noticed because no format command has ever run. The moment `ruff format --check .` joins the release chain, that misplacement becomes a live bug: the formatter would walk `./build` and `.hatch` and report findings on build artifacts and environment internals. Requirement 1.7 is describing a real defect.

**`extend-exclude`, not `exclude`.** `exclude` replaces Ruff's default list; `extend-exclude` adds to it. The documented defaults are `.bzr`, `.direnv`, `.eggs`, `.git`, `.git-rewrite`, `.hg`, `.mypy_cache`, `.nox`, `.pants.d`, `.pytype`, `.ruff_cache`, `.svn`, `.tox`, `.venv`, `__pypackages__`, `_build`, `buck-out`, `dist`, `node_modules`, `venv` — so using `exclude` would trade a three-entry win for a twenty-entry loss. Both existing entries must stay: the defaults list `_build`, not `build`, and `./build` is what `[tool.hatch.build] directory` names; `.hatch` is not a default either.

**One top-level entry for the generated module, not `lint.exclude` + `format.exclude`.** Requirements 3.1 and 3.2 could each be satisfied by an engine-scoped key, but two keys can drift: a later edit to one leaves the other behind, and the file starts getting reformatted with no config change that looks related. The top-level entry makes divergence unrepresentable, which is what the engine-symmetry property below asserts. Ruff's own issue tracker also reports `format.exclude` handling directory patterns less reliably than the global option — another reason to stay global.

**`*.md` is excluded, because on the pinned version Markdown is in scope by default.** Nothing in the requirements asks for documentation to be linted or reformatted, and the scope statement — "roughly ten files, the hand-written Python" — assumes Markdown is out. Leaving it in has two costs. The formatter would rewrite the ```python blocks in `README.md` and `.agents/summary/interfaces.md`, turning a documentation edit into part of a mechanical commit and making Requirement 5.1's "every file it reports as unformatted" cover files the requirement never contemplated. The linter is worse: doc snippets are illustrative fragments, so `F821` on undefined names, `I001` on unsorted imports in a three-line example, and `T201` on `print` in a usage sample are all near-certain — findings that would have to be answered by widening a glob, which the reconciliation rule forbids. Excluding `*.md` keeps the feature's blast radius equal to its stated scope, and it is a one-line decision that a later commit can reverse deliberately if documentation linting is ever wanted. Note this also covers the untracked `.kiro/specs/**/*.md`, which Ruff would otherwise walk: `respect-gitignore` skips *ignored* files, and `.kiro/` is not in `.gitignore`.

**`force-exclude = true` protects Requirement 3.5.** With the default `false`, `ruff format src/oscal_bindings/v1/models.py` rewrites the generated file despite the exclusion, because the path was named explicitly. That is not hypothetical: an editor LSP, a targeted invocation while debugging, or a future script passing changed files would all hit it, and the damage — a reformatted generated module — only surfaces on the next `hatch run generate` as a confusing diff. Setting `force-exclude = true` makes the exclusion unconditional. `ruff-vscode` already passes `--force-exclude` by default, so this aligns the command line with what editors do.

### 4. Per-file ignores

```toml
[tool.ruff.lint.per-file-ignores]
# Tests can use magic values, assertions, and relative imports
"tests/**/*" = ["PLR2004", "S101", "TID252", "PLC0415", "INP001"]
# Build/codegen scripts report progress and errors on stdout/stderr. scripts/ is
# intentionally not a package (like tests/), so INP001 does not apply.
"scripts/**/*" = ["T201", "INP001"]
# collapse_scalar_root_models() is a single-pass line scanner: its branches are the
# cases of one state machine over the generated source, sharing one cursor (`i`).
# Splitting it would scatter that shared cursor state across helpers.
"scripts/postprocess_models.py" = ["PLR0912", "PLR0915"]
# Inline exception messages. A deferral, not a blessing: these findings flag a
# real API weakness (typed parsers raise a flat OscalParseError on a document-type
# mismatch), to be fixed with a dedicated WrongDocumentTypeError.
"src/oscal_bindings/v1/**" = ["EM101", "EM102", "TRY003"]
# PEP 484 explicit re-export idiom (`import X as X`) — correct in a compat shim
"src/oscal_bindings/__init__.py" = ["PLC0414"]
```

`INP001` joins the existing `tests/**/*` entry rather than getting its own — it is the same exemption for the same reason (`tests/` is intentionally not a package; see Req 2.8, which forbids adding `tests/__init__.py`). The literal list from Requirement 1.6 is preserved as a prefix of the extended list. The same reasoning puts `INP001` on `scripts/**/*` (Req 2.1): `scripts/` is loaded by path, never imported as a package.

**The `PLR0912`/`PLR0915` entry is an exact path, added during implementation on measured findings (Req 2.9).** Under the pin both codes fire once, on `collapse_scalar_root_models()` (18 branches, 81 statements) — not on `main()` as §2 originally attributed. The entry names one file and two codes, so the complexity rules stay live for every other file, including `tests/` and the rest of `scripts/`.

**The exception-message entry was widened on measured evidence, not on preference.** The original design scoped it to the exact path `src/oscal_bindings/v1/parser.py` and named only `EM101` and `TRY003`. Measurement shows that entry cannot reach zero, for two independent reasons:

- **A code was missing.** `EM102` — the f-string variant of `EM101` — fires 4x in `parser.py` itself. It is the same pattern as `EM101` (message constructed at the raise site rather than bound to a name first); only the string kind differs.
- **The path was too narrow.** The same code family fires in two sibling modules: `v1/extensions/document.py` (2x `EM102`, 2x `TRY003`) and `v1/extensions/validate_element.py` (1x `EM102`, 1x `TRY003`). `parser.py` carries the bulk (8x `EM101`, 4x `EM102`, 12x `TRY003`) but not the whole.

So the choice was between three exact-path entries naming the same three codes, or one glob over the package. One glob wins: the three modules share one cause — every hand-written module under `v1/` raises `OscalParseError` with an inline message — and three entries would have to be kept in sync as modules are added, with the failure mode being a silent new finding in step 1 of some future feature.

Two things keep the widening from becoming the weakening §2 warns about. `src/oscal_bindings/v1/**` is still meaningfully narrower than `src/**`: it does **not** cover the compat shim at `src/oscal_bindings/__init__.py` or the alias modules beside it, which is exactly where a stray inline-message raise should still be reported. And the entry names exactly three codes, which is what makes Requirement 2.7 enforceable — `EM101`, `EM102`, `TRY003` stay live everywhere else, and Property 2's negative direction has a concrete list to check rather than an open-ended one. An entry that widened *and* grew its code list would be indefensible; this one widens the path by one level and adds one code that is the twin of a code already there.

Every glob is otherwise scoped as narrowly as the requirement allows. `scripts/**/*` and not `**/*`; `src/oscal_bindings/v1/**` and not `src/**`; the `PLC0414` entry is a single exact file and not `**/__init__.py`, because the PEP 484 re-export idiom is correct *in a compatibility shim* and nowhere else in this tree. Over-broad globs are the failure mode that satisfies Requirements 2.1–2.3 while violating 2.7, and the scoping property below generates shadow paths (`src/scripts/x.py`, `tests_extra/y.py`, a `v1`-lookalike directory elsewhere, `src/oscal_bindings/extensions/__init__.py`) specifically to catch it.

### 4a. `RUF100`: the one fix-rather-than-ignore case

Six findings get deleted rather than ignored — unused `# noqa: F401` directives on re-export lines:

| File | Count |
|---|---:|
| `src/oscal_bindings/__init__.py` | 2 |
| `src/oscal_bindings/extensions/__init__.py` | 1 |
| `src/oscal_bindings/parser.py` | 1 |
| `src/oscal_bindings/v1/__init__.py` | 2 |

This looks like an exception to Requirement 2's configuration-only stance. It is not; it is an application of it.

The stance exists to protect *working source* from being rewritten to satisfy a linter. A `# noqa` that suppresses nothing is not working source — it is dead code, in the most literal sense available for a comment: it has no effect on any tool, at any version, under any configuration. Deleting it removes no behavior because it produces none.

The diff is a trailing comment and nothing else. No import is removed, no name is renamed, no re-export changes, no `__all__` entry moves. `from .v1 import parse_oscal  # noqa: F401` becomes `from .v1 import parse_oscal`. Compare this to what Requirement 2 actually forbids — rewriting `print` calls, restructuring exception messages, adding `tests/__init__.py` — all of which change what the code does or how it is organized. Nothing of that kind happens here.

And the alternative is worse than the change. Ignoring `RUF100` on these files would preserve six comments that assert a suppression the linter does not need. A reader encountering `# noqa: F401` reasonably concludes that `F401` would fire without it, and therefore that the import is unreferenced and kept deliberately — which is a false claim about the module. Config-only would mean choosing to keep misleading documentation in the source in order to honor a rule whose purpose is to avoid touching the source.

Worth recording *why* the directives are there at all, because it explains why they are safe to delete: they predate `__all__` being the thing that keeps the re-exports alive. `F401` fires on an import that is unused *and* not re-exported; an explicit `__all__` naming the symbol satisfies the re-export condition on its own. Once `__all__` became the audited public surface (see the API pattern in `AGENTS.md`, where neither the shim nor `v1/__init__.py` defines anything), the directives became redundant without anyone removing them. `RUF100` is simply reporting a cleanup that was already implied.

This is the only place the no-source-rewrite rule yields, and the yield is bounded by the requirement itself: Requirement 2.6 names the six sites and the count, so the implementation has no room to expand the deletion into a tidy-up pass.

Note the table name stays `per-file-ignores`, not `extend-per-file-ignores`. The latter is for extending a Hatch-supplied base, and this config has no base to extend — that is the point.

### 5. The `lint` script

```toml
[tool.hatch.envs.default.scripts]
lint = [
    "ruff check .",
    "ruff format --check .",
]
```

Hatch runs a script list sequentially and aborts on the first non-zero exit, propagating that status — the `-` command prefix exists precisely to opt out of that behavior, so the default is abort. That gives Requirements 4.3, 4.4, and 4.7 without extra shell plumbing.

The ordering has one consequence worth naming: a lint finding aborts before the format check runs, so the two never report together. Accepted. Both must pass eventually, and a developer iterating on findings would re-run anyway. The alternative — running both unconditionally and combining exit codes — needs a shell one-liner with `set -o pipefail` semantics for a marginal gain in first-run completeness.

`--check` on the formatter is what satisfies Requirement 4.2's "without rewriting": it reports and exits non-zero, touching nothing. `--diff` is deliberately not added; it makes the failure output long, and a developer who wants the diff runs `hatch run ruff format --diff .`.

No `lint-fix` companion script. The one-time formatting pass runs as an ad-hoc `hatch run ruff format .` (Ruff is on the env's path), and no acceptance criterion asks for a persistent fix script. One script, one purpose.

### 6. `hatch fmt` and the broken static-analysis environment

The `hatch-static-analysis` environment has a broken Python symlink, and this design does not repair it. It is not repaired because it is not used: its Ruff version, rule set, and line length (120, versus this repo's 88) are all Hatch's, which is exactly the ownership problem Requirement 1 exists to solve. Fixing the symlink would restore a second, differently configured lint path — a worse outcome than leaving it broken.

Recommendation: leave the environment untouched and add one line to `DEVELOPING.md` stating that `hatch run lint` is the entry point and that `hatch fmt` / `hatch check code` are not used by this repo. The environment is Hatch-internal and provisioned on demand, so there is nothing in `pyproject.toml` to remove; an unused path with no documentation is how someone ends up "fixing" it in six months. (Hatch is itself deprecating `fmt` in favor of `check code` / `check fmt`, which makes documenting non-use more useful than tracking the rename.)

## Data Models

No runtime data model. The configuration surface, as a table of what each key satisfies:

| Table | Key | Value | Requirement |
|---|---|---|---|
| `tool.hatch.envs.default` | `dependencies` | `+ ruff==0.16.8` | 1.1, 4.10 |
| `tool.hatch.envs.default` | `dependencies` | `datamodel-code-generator[http]==0.59.0` (was unpinned; `project.optional-dependencies.codegen` pinned to match) | 3.5 |
| `tool.hatch.envs.default.scripts` | `generate` | `+ --disable-timestamp` on the `datamodel-codegen` command | 3.5 |
| `tool.ruff` | `line-length` | `88` (unchanged) | 1.5 |
| `tool.ruff` | `target-version` | `"py311"` (unchanged) | 1.5 |
| `tool.ruff` | `extend-exclude` | `["./build", ".hatch", "src/oscal_bindings/v1/models.py", "*.md"]` | 1.7, 1.8, 3.1, 3.2, 3.3 |
| `tool.ruff` | `force-exclude` | `true` | 3.5 |
| `tool.ruff.format` | `quote-style` | `"double"` (unchanged) | 1.5 |
| `tool.ruff.format` | `indent-style` | `"space"` (unchanged) | 1.5 |
| `tool.ruff.lint` | `select` | explicit family list | 1.2, 1.3, 2.4 |
| `tool.ruff.lint` | `ignore` | `["ISC001"]` | — (formatter conflict) |
| `tool.ruff.lint` | `exclude` | **removed** (moved to top level) | 1.7 |
| `tool.ruff.lint` | `isort.known-first-party` | `["oscal_bindings"]` (unchanged) | 1.5 |
| `tool.ruff.lint.per-file-ignores` | `"tests/**/*"` | `[PLR2004, S101, TID252, PLC0415, INP001]` | 1.6, 2.2 |
| `tool.ruff.lint.per-file-ignores` | `"scripts/**/*"` | `[T201, INP001]` | 2.1 |
| `tool.ruff.lint.per-file-ignores` | `"scripts/postprocess_models.py"` | `[PLR0912, PLR0915]`, with the scanner-structure comment | 2.9 |
| `tool.ruff.lint.per-file-ignores` | `"src/oscal_bindings/v1/**"` | `[EM101, EM102, TRY003]`, with the `WrongDocumentTypeError` deferral comment | 2.3, 2.4 |
| `tool.ruff.lint.per-file-ignores` | `"src/oscal_bindings/__init__.py"` | `[PLC0414]` | 2.5 |
| — (source edit, not config) | six `# noqa: F401` directives | **deleted** | 2.6 |
| `tool.hatch.envs.default.scripts` | `lint` | two-command list | 4.1, 4.2 |
| `tool.hatch.envs.default.scripts` | `release` | `+ "lint"` after `generate` | 4.5, 4.6 |

Files in scope for the formatting pass — the tracked Python files, generated module excluded. `git ls-files '*.py'` reports 14 at design time; the count is whatever the command returns at implementation time, not a fixed number:

```
scripts/postprocess_models.py
src/oscal_bindings/__init__.py
src/oscal_bindings/v1/__init__.py
src/oscal_bindings/v1/parser.py
src/oscal_bindings/v1/extensions/{__init__,builders,document,validate_element}.py
tests/test_{builders,document,oscal_bindings,parser,postprocess,prop_postprocess,validate_element}.py
```

## Implementation Sequence

Three commits, each independently reviewable. The split exists so the mechanical diff never hides a decision.

**Step 1 — config only.** Add the pin, `select`, `ignore`, `extend-exclude`, `force-exclude`, the three new `per-file-ignores` entries (`scripts/**/*`, `src/oscal_bindings/v1/**`, `src/oscal_bindings/__init__.py`), `INP001` on the tests entry, the `lint` script, and `lint` in `release`. Remove `lint.exclude`. Delete the six unused `# noqa: F401` directives per §4a. At the end of this step `hatch run lint` is *expected to fail* on format findings and possibly on residual lint findings — that failure is the baseline measurement, and it is what makes step 2's diff predictable. Record the finding list against the **pinned** Ruff, not against the 418-finding 0.4.5 numbers in §2; reconcile per the rule in §2, and resolve the `PLR0912`/`PLR0915` open item named there.

**Step 2 — the formatting pass, nothing else.** Run `hatch run ruff format .` and commit only what the formatter wrote. No hand edits ride along, no renames, no docstring touch-ups. A reviewer should be able to verify this commit by re-running the formatter and getting an empty diff, which is exactly how Requirement 5.2 reads. Confirm `git diff --stat` does not name `src/oscal_bindings/v1/models.py`; if it does, the exclusion is wrong and step 1 needs fixing before proceeding.

**Step 3 — evidence and config tests.** Add the config-assertion tests and the properties below; run `hatch run typing` (Req 5.5), `hatch test --all` (Req 5.4), and the regeneration check (Req 3.5). Update `DEVELOPING.md` per §6.

### Verifying Requirement 3.5 concretely

`hatch run generate` overwrites `src/oscal_bindings/v1/models.py` in place, so "byte-identical to the file committed before that run" needs a before/after comparison rather than an inspection. The check, from a clean tree:

```bash
shasum -a 256 src/oscal_bindings/v1/models.py > /tmp/models.before
hatch run generate
shasum -a 256 -c /tmp/models.before          # must pass
git diff --exit-code -- src/oscal_bindings/v1/models.py   # must exit 0
```

`git diff --exit-code` is the stronger of the two and is sufficient on its own — the digest is there to make a failure legible when the diff is enormous. Two supporting checks, both cheap, that catch the realistic ways this breaks:

```bash
ruff format --check src/oscal_bindings/v1/models.py   # explicitly named: must report nothing
grep -c -e '# noqa' -e '# fmt: off' -e '# fmt: on' src/oscal_bindings/v1/models.py   # must be 0
```

The first is the `force-exclude` check — it is the invocation that would silently rewrite the file if `force-exclude` were left at its default. The second is Requirement 3.4, and it is the reason the exclusion is configuration rather than in-file suppression: any marker added to the file would be erased by the next `generate` anyway, so suppression comments cannot work here even in principle.

This check runs manually and at release time, not in the unit suite — it invokes the full codegen pipeline (external tool, network-capable, tens of seconds).

## Error Handling

There is no runtime error path to design; the failure modes are all developer-facing, and the question for each is whether the message points at the cause.

| Failure | Surface | Resolution |
|---|---|---|
| Lint finding | `ruff check` prints code, path, line; non-zero exit aborts `lint` and `release` | Fix source, or add a scoped `per-file-ignores` entry with a comment saying why |
| Format drift | `ruff format --check` lists files needing change | `hatch run ruff format .` |
| Unknown rule code in `select` | Ruff errors on config parse, before checking anything | Typo in the selection; the pin makes the valid set of codes deterministic |
| Pin bumped, new findings appear | `lint` fails in the bump commit | Intended. Absorb findings in that commit or revert the bump |
| `ruff` missing from the env | Hatch reports command not found | Env is stale; `hatch env prune` and re-provision. The lockfiles in `requirements/` are `hatch-pip-compile` output and regenerate from the dependency list |
| Generated module reformatted | `hatch run generate` produces a large unexpected diff | Exclusion or `force-exclude` regressed; the §3.5 checks localize it |

One anti-pattern to name because it is the tempting shortcut: reaching zero findings by widening a glob or dropping a `select` family. Both leave a config that reads as enforcing and does not. The scoping and coverage properties below fail when either happens.

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

This feature's deliverable is configuration, so most acceptance criteria are literal config assertions (examples) or single invocations of an external tool (integration and smoke checks). Three criteria are genuinely universal — each names a quantifier over paths or codes, and each has a failure mode that a fixed example would pass while the config is silently wrong. Those three become properties. The prework analysis records the classification of the criteria (32 at the time it ran; Req 1.8 was added during review and is an example assertion, not a property) and the reflection that collapsed the candidate list to these three.

All three are pure functions of the parsed `pyproject.toml` plus a generated path or code string: no subprocess, no filesystem walk, no Ruff invocation. That is what makes 100+ iterations cheap enough to be worth running.

### Property 1: Exclusion is engine-symmetric

For any repo-relative file path, the exclusion verdict computed from the Ruff configuration is identical for the linter and the formatter — no path is excluded from one engine and walked by the other. Equivalently: the configuration declares no engine-scoped exclusion key (`lint.exclude`, `lint.extend-exclude`, `format.exclude`, `format.extend-exclude`), so both engines resolve every path against the same top-level pattern set.

**Validates: Requirements 1.7, 3.1, 3.2, 3.3**

### Property 2: Per-file ignores are exactly scoped

For any repo-relative Python path and any code in the accepted set `{T201, INP001, EM101, EM102, TRY003, PLC0414, PLR2004, S101, TID252, PLC0415}`, that code is ignored at that path if and only if the path matches the specific `per-file-ignores` pattern that names it. In particular, for any path outside those patterns, every code in the set remains active.

**Validates: Requirements 1.6, 2.1, 2.2, 2.3, 2.5, 2.7**

### Property 3: The selection covers every governed code

For any code the requirements require to remain enforceable — the accepted set of Property 2 — some entry of `lint.select` is a prefix of that code, so the code is reachable by the linter and its `per-file-ignores` entry is meaningful rather than vacuous.

**Validates: Requirements 1.2, 2.7**

The widened `src/oscal_bindings/v1/**` glob of Requirement 2.3 is precisely why Property 2's negative direction earns its keep. The compat-shim alias modules — `src/oscal_bindings/extensions/__init__.py`, `src/oscal_bindings/parser.py` — sit one directory level outside that glob, and an entry written `src/oscal_bindings/**` instead would satisfy Requirements 2.1–2.3 while silently violating 2.7: the `EM`/`TRY003` exemption would leak onto the shim. A positive-only check passes in that state. The negative direction is the exact failure the property exists to catch.

## Testing Strategy

### Property tests

`hypothesis` is already an `extra-dependencies` entry on `hatch-test`, and `tests/test_prop_postprocess.py` establishes the repo's convention for property tests. The new properties live in a sibling module, `tests/test_prop_lint_config.py`.

Each test reads `pyproject.toml` once via `tomllib` (stdlib on 3.11+, no new dependency), then quantifies over generated inputs. Minimum 100 iterations each — the default. Tag format: **Feature: lint-and-format-enforcement, Property {n}: {property text}**.

Generators, chosen so the shadow cases that break over-broad globs actually get produced rather than left to chance:

- **Paths**: repo-relative POSIX paths built from a directory-segment alphabet that deliberately includes near-misses of the ignored trees — `scripts`, `script`, `scripts_old`, `src/scripts`, `tests`, `tests_extra`, `test`, `src/oscal_bindings/v1` — with varied depth and both `.py` and non-`.py` leaves. The alphabet must also produce the shadow paths that sit just outside the widened `src/oscal_bindings/v1/**` glob and the exact-path `PLC0414` entry, since those are the paths an over-broad glob silently captures: the compat-shim alias modules `src/oscal_bindings/extensions/__init__.py` and `src/oscal_bindings/parser.py` (these must *not* pick up the `v1/**` `EM`/`TRY003` exemption), a `v1`-lookalike directory such as `src/oscal_bindings/v1_2/x.py`, and `src/oscal_bindings/v1/__init__.py` as a positive case. Include the exact literal paths (`scripts/postprocess_models.py`, `src/oscal_bindings/v1/parser.py`) as explicit `@example` cases so they are never merely probable, and pin `src/oscal_bindings/__init__.py` as an `@example` too — it is the sole `PLC0414` path, so a false negative there is invisible otherwise.
- **Codes**: sampled from the accepted set for Properties 2 and 3, plus, for Property 2's negative direction, codes drawn from the selected families that appear in *no* ignore entry (they must never be reported as ignored anywhere). The negative-direction code generator must cover `EM102` and `PLC0414` explicitly: both are now governed codes with narrowly scoped entries (`src/oscal_bindings/v1/**` and `src/oscal_bindings/__init__.py` respectively), and a generator that omits them under-checks — it would never exercise the two scopings most likely to be written too broadly.

Pattern matching uses the same semantics Ruff documents for `per-file-ignores` globs, implemented once in a helper and shared by Properties 1 and 2. That helper is the one piece of genuine logic in the test module and is itself covered by a handful of examples — an incorrect helper would make both properties vacuously pass, which is the one way this test suite could lie.

### Example tests

Fixed assertions over the parsed config, in `tests/test_lint_config.py`. These are regression guards on literal values, deliberately not generalized:

- Exactly one `ruff==X.Y.Z` entry in the default env dependencies (Req 1.1, 4.10).
- `line-length == 88`, `target-version == "py311"`, `format.quote-style == "double"`, `format.indent-style == "space"`, `lint.isort.known-first-party == ["oscal_bindings"]` (Req 1.5).
- The Requirement 1.6 codes are all present on the `tests/**/*` entry (Req 1.6).
- `src/oscal_bindings/v1/models.py` appears in the top-level exclusion patterns (Req 3.3).
- The generated module contains no `# noqa`, `# fmt: off`, or `# fmt: on` (Req 3.4).
- The `lint` script list contains a `ruff check` command and a `ruff format --check` command, and `lint` is defined under `[tool.hatch.envs.default.scripts]` (Req 4.1, 4.2, 4.10).
- `release` contains `lint` and still contains `generate`, `typing`, `hatch test --all --cover`, `docs` (Req 4.5, 4.6).
- No `extend = "ruff_defaults.toml"` and no `[tool.hatch.envs.hatch-static-analysis]` table (Req 1.3).
- `.github/workflows/` and `.pre-commit-config.yaml` do not exist (Req 4.8, 4.9).
- `tests/__init__.py` does not exist, and `scripts/postprocess_models.py` still contains `print(` calls (Req 2.8, the "without rewriting source" half).
- The `src/oscal_bindings/v1/**` ignore entry names exactly `EM101`, `EM102`, `TRY003` and carries the deferral comment (Req 2.3, 2.4).
- No `# noqa` directive remains at the six sites named in Req 2.6 (Req 2.6).

Requirement 4.6 deserves a note: it is the guard against the most likely regression in this change, which is a hand-edited `release` list that adds `lint` and drops a stage.

### Integration and smoke checks

Run at implementation time and at release time, not in the unit suite — each invokes an external tool over the whole tree, and repetition buys nothing:

| Check | Criterion |
|---|---|
| `hatch run lint` exits 0 on a clean tree | 2.8, 5.2, 5.3 |
| Temporary violation ⇒ `hatch run lint` non-zero ⇒ `hatch run release` stops at `lint` | 4.3, 4.4, 4.7 |
| Working tree unchanged after `ruff format --check .` | 4.2 |
| `ruff check` / `ruff format --check` on the explicitly named generated path report nothing | 3.1, 3.2 |
| The §3.5 digest-and-diff sequence around `hatch run generate` | 3.5 |
| `hatch test --all` pass count, before vs. after the formatting pass | 5.4 |
| `hatch run typing` reports zero errors | 5.5 |

Requirement 5.4 was reworded during review to a no-regression assertion — zero failures on both matrix cells and no test that passed before the formatting pass failing after it, with 261 as a floor rather than an exact count. The original fixed count was a criterion this feature could not satisfy while also testing itself, since it adds test modules of its own.

Requirement 1.4 was likewise reworded to state what is actually checkable from one checkout: that no input to the linter is machine-dependent. Identical findings on two machines follows structurally from that plus the exact pin (Req 1.1) and the self-owned selection (Req 1.2, 1.3), all of which the example tests assert. Observing it directly would require provisioning a second environment — out of proportion to the risk, and no task claims to do so.
