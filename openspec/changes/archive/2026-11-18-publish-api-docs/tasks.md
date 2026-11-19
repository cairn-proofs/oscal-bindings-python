# Tasks

## 1. Docstring markup

- [x] 1.1 Add `tests/test_docstring_markup.py` as [design D3](design.md#d3-markdown-code-spans-replace-sphinx-roles)
  states. Verify with `hatch test tests/test_docstring_markup.py` that it fails and names each of the eight files
  that hold a role.
- [x] 1.2 Replace each Sphinx role in the hand-written modules under `src/oscal_bindings/` with a code span, as design
  D3 states. Name each member that a class takes from `datetime` or `OSError` with its base class, as D3 states.
  Change no other docstring text. Verify that `hatch test tests/test_docstring_markup.py` passes and that
  `hatch test` passes, including `TestDocumentation` in `tests/test_oscal_datetime.py`.

## 2. Docs build

- [x] 2.1 Add `scripts/build_docs.py` as [design D1](design.md#d1-a-script-runs-pdoc-and-checks-its-output) states,
  and `docs/pdoc-templates/module.html.jinja2` as
  [design D4](design.md#d4-the-script-corrects-the-pydantic-output-of-pdoc) states. Change the `docs`
  script in `pyproject.toml` to `python scripts/build_docs.py`. Add `pdoc` to the `extra-dependencies` of `hatch-test`
  and run `hatch run lock`. Add `tests/test_build_docs.py`, which imports the script with `load_script`. Verify with
  `hatch test tests/test_build_docs.py`:
  1. The corrected `annotation_str` of the `params` field of `Catalog` is
     `: list[oscal_bindings.v1.models.ParameterWithSelect | oscal_bindings.v1.models.ParameterWithValues] | None`.
     The corrected `default_value_str` of `StringDatatype` is `str`.
  2. For a small output directory with one defect of D1 item 3, the output check reports that defect. For a
     directory with no defect, it reports nothing.
- [x] 2.2 Run `hatch run docs`. Verify that it exits 0, and in `build/api-docs`:
  1. `oscal_bindings/v1.html` has `Arguments`, `Returns`, and `Raises` section headings.
  2. In `oscal_bindings/v1/models.html`, the `metadata` field of `Catalog` shows `metadata: Metadata` with no default.
     The `params` field shows `= None`, and its annotation links to `#ParameterWithSelect`.
  3. The `OscalDocument` entry of `oscal_bindings/v1.html` has no docstring from `RootModel`, and no `Generic` base.
  4. The edit link of `oscal_bindings/v1.html` is
     `https://github.com/cairn-proofs/oscal-bindings-python/blob/main/src/oscal_bindings/v1/__init__.py`. With
     `DOCS_SOURCE_REF=v0.0.0` set, it has `v0.0.0` in place of `main`.
- [x] 2.3 Rewrite the module docstring of `src/oscal_bindings/__init__.py` as the overview of
  [design D5](design.md#d5-the-oscal_bindings-docstring-is-the-home-page). In the module docstring of
  `src/oscal_bindings/v1/__init__.py`, write `Key Classes` and `Key Functions` as Markdown lists and add the link to
  `oscal_bindings.v1.models`. Run `hatch run docs`. Verify that `oscal_bindings.html` shows the overview with a working
  link to the `oscal_bindings.v1` page, and that each name in the two lists of `oscal_bindings/v1.html` is a link.
- [x] 2.4 Update the docs that describe the docs build:
  1. `DEVELOPING.md`: the `docs` line of the command list, and a short section on `scripts/build_docs.py`, its checks,
     and the template.
  2. `AGENTS.md`: the `hatch run docs` item in "Config-Derived Facts", and `scripts/build_docs.py` in the directory
     map.
  3. `.agents/summary/workflows.md` line 185, `.agents/summary/dependencies.md` line 39, and
     `.agents/summary/components.md` for the new script.

  Verify with a `grep` for `pdoc oscal_bindings oscal_bindings.v1 -o` that no doc states the old command.

## 3. Release deploy

- [x] 3.1 In `.github/workflows/build.yml`, set `DOCS_SOURCE_REF` on the `Docs` step of the `checks` job as design D1
  states. Change the `attest` and `draft-release` jobs as
  [design D7](design.md#d7-the-attest-job-signs-api-docszip) states. Update the comment above `attest`. Verify by
  reading the diff that `attest` signs `dist/api-docs.zip` and the packages in one step, and that `draft-release`
  attaches all three files.
- [x] 3.2 In `.github/workflows/release.yml`, add the `docs-latest` and `pages-deploy` jobs of
  [design D8](design.md#d8-pages-deploy-runs-after-pypi-publish-for-the-latest-release-only).
  Update the comment at the top of the file. Verify by reading the diff that `pypi-publish` does not change, and
  that only `pages-deploy` has `pages: write`.
- [x] 3.3 Run the zip command of the `attest` job on the `build/api-docs` of task 2.2, then the unzip command and the
  `index.html` test of `pages-deploy`, in a directory under `tmp/`. Verify that the unzipped directory has
  `index.html` at its root and the same file list as `build/api-docs`.
- [x] 3.4 Update the docs of the release flow:
  1. `DEVELOPING.md` "Releasing": the docs asset and the deploy after the PyPI upload. The skip for a release
     that is not the latest. The step to clear "Set as the latest release" for a release of an older line. "Re-run
     failed jobs" for a failed deploy. Also the one-time settings of
     [design D9](design.md#d9-a-maintainer-sets-the-repo-settings-by-hand) with their `gh api` commands.
  2. `README.md`: a link to <https://cairn-proofs.github.io/oscal-bindings-python/> below the first paragraph.
  3. `AGENTS.md` "Config-Derived Facts", the CI item: the docs asset and `pages-deploy`.
  4. `.agents/summary/workflows.md`: the release flow.

  Verify that each `gh api` command in `DEVELOPING.md` names the repo `cairn-proofs/oscal-bindings-python` and the
  environment `github-pages`.

## 4. Integration

- [x] 4.1 Run `hatch run release`. Verify that it passes, and that
  `git diff --exit-code -- src/oscal_bindings/v1/models.py` shows no change.

## Workflow follow-up

- Commit as `docs:` with `#90` in the message. Commit only the files that the tasks name, and no build output.
- On the pull request, verify that the CI `api-docs` artifact has the commit SHA in the edit links.
- The user applies the settings of design D9 before the next release. The first published release after the merge
  tests the deploy path end to end.
- Archive the change after review.
