---
inclusion: always
---
<!------------------------------------------------------------------------------------
   Add rules to this file or a short description and have Kiro refine them for you.
   
   Learn about inclusion modes: https://kiro.dev/docs/steering/#inclusion-modes
-------------------------------------------------------------------------------------> 
# Use Hatch for all Python execution

All Python execution in this project goes through `hatch`. Never invoke a Python
interpreter or Python tool directly.

**Why:** every Hatch env is locked (`hatch-pip-compile` with the uv resolver and
hashes: `default` → `requirements.txt`, others → `requirements/requirements-<env>.txt`),
so hatch guarantees the right Python version and exact pinned deps. That matters
here beyond reproducibility: `datamodel-code-generator` formats `v1/models.py`
with black and isort, so an unlocked tool can change generated code with no
change in this repo. It also keeps shell permissions narrow: `hatch ...` commands
are allowlisted, while arbitrary `python`/`python3`/`.venv/bin/python`
invocations are not and will require manual approval.

## Do / Don't

| Task | Do | Don't |
|---|---|---|
| Full gate (generate + lint + typing + security + all-version tests with coverage + docs) | `hatch run release` | chaining the steps by hand |
| Run tests | `hatch test` | `pytest`, `python -m pytest`, `.venv/bin/pytest` |
| Run a specific test | `hatch test tests/test_parser.py::TestX::test_y` | `python -m pytest tests/...` |
| Pass pytest flags | `hatch test -- -x -k "catalog"` | `pytest -x -k "catalog"`, `hatch test -x` |
| Single Python version | `hatch test -py 3.12 tests/...` | switching interpreters manually |
| Whole matrix with coverage | `hatch test --all --cover` (writes `htmlcov/`) | `coverage run -m pytest` |
| Regenerate models | `hatch run generate` | hand-editing `src/oscal_bindings/v1/models.py`, running `datamodel-codegen` or `scripts/postprocess_models.py` with your own arguments |
| Type checking | `hatch run typing` | `mypy src`, `python -m mypy`, `hatch check types` |
| Lint + format check | `hatch run lint` | `ruff check .`, `hatch check`, `hatch fmt` |
| Lint autofix | `hatch run ruff check --fix .` | `ruff check --fix`, `hatch check code --fix` |
| Format | `hatch run ruff format .` | `ruff format`, `hatch check fmt --fix`, `hatch fmt` |
| Security scan (bandit + pip-audit over every lockfile) | `hatch run security` | `bandit -r src`, `pip-audit` |
| Just one scanner | `hatch run security:scan-code` or `hatch run security:scan-deps` | running bandit/pip-audit from `default` (they aren't installed there) |
| API docs | `hatch run docs` (writes `build/api-docs`) | `pdoc oscal_bindings` |
| Run a script | `hatch run python scripts/postprocess_models.py --help` | `python3 scripts/...`, `.venv/bin/python ...` |
| One-off snippet | `hatch run python -c "import oscal_bindings; print(oscal_bindings.__oscal_schema_version__)"` | `python3 -c ...` |
| Project scripts | `hatch run <script>` (see `[tool.hatch.envs.default.scripts]` in `pyproject.toml`) | re-implementing the script's steps inline |
| Add / change deps | edit `pyproject.toml`, then `hatch run lock`; commit the lockfile changes with it | `pip install`, `uv pip install`, `uv lock` |
| Upgrade locked deps | `hatch run upgrade`, review the lockfile diff, then `hatch run release` | re-resolving envs one at a time by hand |

## Notes

- `hatch test` uses the `hatch-test` env (matrix: 3.11, 3.12, 3.13, 3.14; parallel; adds
  `hypothesis`; constrained to `default`'s versions). `hatch run` uses `default`
  (Python 3.14: mypy, ruff, pdoc, datamodel-code-generator). The `security` env
  is detached and holds bandit and pip-audit. Use `hatch test` for tests and
  `hatch run` for everything else.
- pytest is intentionally not in `default`. Don't add it, and don't try
  `hatch run pytest`; Hatch supplies pytest's range in `hatch-test`, and listing
  it in `default` breaks the constrained resolve.
- Always put pytest flags after `--`. Several short flags collide with
  `hatch test`'s own options (`-x` is matrix exclude, `-p` is parallel, `-c` is
  cover, `-r` is randomize), so `hatch test -x` will not do what pytest's `-x`
  does.
- Don't use `hatch check` / `hatch fmt` for linting, formatting, or types. They
  run in Hatch's own unlocked `hatch-check-*` / `hatch-static-analysis` envs
  with Hatch's choice of tool versions (and Pyrefly, not mypy, for
  `hatch check types`), not the project's pinned ruff and mypy. The `lint` and
  `typing` scripts are what `release` and CI run, so they're the source of truth.
- Ruff is configured to never touch `v1/models.py` (`force-exclude`), even when
  named explicitly. If generated code needs to change, change the schema or
  `scripts/postprocess_models.py` and run `hatch run generate`.
- `hatch run release` is slow. Capture its full output and exit code in one
  invocation (`hatch run release > ./tmp/release.log 2>&1; echo "EXIT: $?"`)
  and inspect the log rather than re-running.
- Prefer an existing `hatch run <script>` over composing the equivalent commands
  yourself. Check `pyproject.toml` before writing a new command line.
- If a needed tool isn't available in a hatch environment, don't fall back to a
  global or `.venv` interpreter. Stop and propose adding it to the appropriate
  hatch env's `dependencies` (and re-locking). Keep scanner-type tools out of
  `default`, since its pins leak into `hatch-test` through the constraint.
- Hatch itself comes from mise (`mise.toml` / `mise.lock`). Don't install or
  upgrade Hatch via pip, pipx, or brew.
- Don't prefix hatch commands with `cd`; use the tool's `cwd` parameter.
- When delegating to a subagent, restate this rule in the prompt.
