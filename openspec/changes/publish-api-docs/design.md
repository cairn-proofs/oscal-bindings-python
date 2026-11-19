# Design

## Context

See [proposal.md - Why](proposal.md#why) for the motivation. These facts constrain the approach.

1. The `docs` script in `pyproject.toml` is `pdoc oscal_bindings oscal_bindings.v1 -o build/api-docs`. pdoc is pinned
   by the lockfile of the `default` env (16.0.0). The `checks` job of `build.yml` runs the script on each CI run and
   uploads `build/api-docs` as the artifact `api-docs`.
2. pdoc documents the names in the `__all__` of a module. `oscal_bindings.__all__` is `oscal_bindings.v1.__all__`, so
   the two pages have the same entries. `oscal_bindings.v1.__all__` holds 10 classes that `v1/models.py` defines:
   `OscalDocument`, the 8 document wrappers such as `CatalogDocument`, and `DocumentId`. It holds no other model.
3. pdoc supports Pydantic models, but two parts of its output are wrong for the generated models:
   1. The annotation of a field is the full `Annotated[...]` text, with the `FieldInfo(...)` repr and the address of
      the `omit_none` function in it.
   2. A required field shows the default `= PydanticUndefined`.

   A scalar alias such as `StringDatatype` shows its value as the same `Annotated[...]` text. The 10 model classes on
   the current `oscal_bindings.v1` page already show these defects.
4. Pydantic registers two `RootModel[...]` parametrizations in `models` under names that are not identifiers.
5. pdoc changes each Sphinx role to a code span, but it keeps the `~` prefix and the full private module path. Thus
   ``:class:`~oscal_bindings.v1.models.CatalogDocument` `` shows as the literal text
   `~oscal_bindings.v1.models.CatalogDocument`. Hand-written modules under `src/oscal_bindings/` hold 67 roles, 17 of
   them with a `~` prefix, all in `v1/extensions/yaml_io.py`.
6. A `v*` tag push runs `build.yml`. Its `attest` job signs the wheel and the sdist, and its `draft-release` job
   attaches them to a draft release. Publishing the draft runs `release.yml` from the tagged commit. Its one job,
   `pypi-publish`, downloads the assets with `--pattern "*.whl" --pattern "*.tar.gz"`, requires one wheel and one
   sdist, verifies their provenance with `gh attestation verify`, and uploads them to PyPI.
7. The `pypi` environment has a `v*` tag deployment rule, a required reviewer, and a 10-minute wait timer. GitHub Pages
   is not enabled, and no `github-pages` environment exists.

## Goals / Non-Goals

**Goals:**

1. Readers of the site see what PyPI serves: the docs of a release go live only after its packages are on PyPI.
2. The site gets only docs that `build.yml` built and signed for the tag.
3. A docs build that renders a known defect fails, on a developer machine and in CI.

**Non-Goals:**

1. A change to the content of docstrings other than markup, except the two package docstrings of
   [D5](#d5-the-oscal_bindings-docstring-is-the-home-page).
2. A change to the public surface (`__all__`) of either package.

## Decisions

### D1: A script runs pdoc and checks its output

A new script, `scripts/build_docs.py`, replaces the pdoc command line of the `docs` script. `docs` becomes
`python scripts/build_docs.py`. The script:

1. Registers the Jinja filter of [D4](#d4-the-template-renders-model-fields-without-pydantic-internals) on
   `pdoc.render.env`.
2. Calls the pdoc command line (`pdoc.__main__.cli`) with these arguments:
   1. `-d google` ([D2](#d2-pdoc-reads-docstrings-as-google-style)).
   2. `-t docs/pdoc-templates` ([D4](#d4-the-template-renders-model-fields-without-pydantic-internals)).
   3. `-e oscal_bindings=https://github.com/cairn-proofs/oscal-bindings-python/blob/<ref>/src/oscal_bindings/`, where
      `<ref>` is the environment variable `DOCS_SOURCE_REF`, or `main` when it is not set. pdoc then shows a button on
      each page that opens the source file on GitHub.
   4. The modules `oscal_bindings`, `oscal_bindings.v1`, and `oscal_bindings.v1.models`
      ([D6](#d6-the-models-module-gets-its-own-page)).
   5. `-o build/api-docs`.
3. Checks the output, and exits non-zero with one line for each defect that it finds:
   1. `oscal_bindings.html` documents no object.
   2. In `search.js`, each name other than the module `oscal_bindings` starts with `oscal_bindings.v1`, and no object
      name has entries under two modules.
   3. No page contains `FieldInfo(`, `PydanticUndefined`, a memory address (`at 0x`), an `id="RootModel[`, or
      `~oscal_bindings`.
   4. `index.html` and `oscal_bindings/v1/models.html` exist.

The `Docs` step of the `checks` job sets `DOCS_SOURCE_REF` to the tag name on a tag build, and to `github.sha` on each
other build.

A trial build with a script of this kind and the template of D4 gave the output that the checks require.

Alternative: keep the pdoc command line in `pyproject.toml`. The pdoc command line cannot register a filter, and
nothing checks the output. Rejected.

### D2: pdoc reads docstrings as Google style

The script passes `-d google`. pdoc then renders `Args:`, `Returns:`, and `Raises:` as sections, and reads the rest of
each docstring as Markdown. A trial build showed 19 `Raises` sections on the `oscal_bindings.v1` page.

`Key Classes:` and `Key Functions:` are not Google section names. pdoc renders each as a heading over one paragraph.
Thus the `oscal_bindings.v1` docstring writes each of the two lists as a Markdown list. Each item starts with the name
as a code span, and pdoc links a code span that names an object it documents.

Alternative: rewrite each docstring in reStructuredText field lists. That changes each `Args` section in the code.
Rejected.

### D3: Markdown code spans replace Sphinx roles

Each Sphinx role becomes a code span of the name that `oscal_bindings.v1` exports. For example,
``:func:`parse_oscal` `` becomes `` `parse_oscal` ``, and ``:class:`~oscal_bindings.v1.models.CatalogDocument` ``
becomes `` `CatalogDocument` ``. pdoc then links the name to its canonical entry, and the `~` text goes.

A new test, `tests/test_docstring_markup.py`, reads the text of each `.py` file under `src/oscal_bindings/` except
`v1/models.py`. It fails for each match of `:(mod|class|func|meth|attr|exc|data|obj):`` ` ``, and the message names the
file and the line. The test reads the source text, so it finds a role in a comment too. A comment does not need a
role, so this is no loss.

### D4: The template renders model fields without Pydantic internals

A pdoc template directory, `docs/pdoc-templates/`, holds one file, `module.html.jinja2`. It extends the default module
template and overrides three macros:

1. `is_public`. These members are not public:
   1. Each member of the module `oscal_bindings` that is not a module. Thus `oscal_bindings.v1` is the canonical page
      of each object.
   2. Each member of `oscal_bindings.v1.models` whose name is in `oscal_bindings.v1.__all__`. Thus the 10 classes of
      [Context](#context) item 2 have one entry, on the `oscal_bindings.v1` page.
   3. Each member of `oscal_bindings.v1.models` whose name is not an identifier: the `RootModel[...]` entries.

   Each other member gets the default answer. pdoc builds the search index with the same macro, and a link to a hidden
   member goes to its public entry.
2. `annotation`. It writes the annotation through a filter of the script. The filter removes each `Annotated[...]`
   wrapper and its metadata, at each depth, and formats the type that is left. For example,
   `params: list[ParameterWithSelect | ParameterWithValues] | None`.
3. `default_value`. It writes no default when the value is `PydanticUndefined`. Thus a required field shows no
   default. For a scalar alias, it writes the type that the filter gives. For example, `StringDatatype = str`.

Alternative for the duplicates: document only `oscal_bindings.v1`. The site then has no page for the import path that
most examples use. Rejected. Alternative: give `oscal_bindings` a different `__all__`. That changes the public
surface. Rejected.

### D5: The `oscal_bindings` docstring is the home page

The site root redirects to the `oscal_bindings` page, so that page is the home page. Its docstring becomes a short
Markdown overview:

1. What the package is, and the OSCAL release that it binds.
2. The install command, and the `yaml` extra.
3. A short parse-and-serialize example.
4. A statement that `oscal_bindings` re-exports `oscal_bindings.v1`, that each name of either path is the same object,
   and that the reference is on the `oscal_bindings.v1` page, with a link.
5. A link to the README on GitHub for the full guide.

The `oscal_bindings.v1` docstring gets the lists of [D2](#d2-pdoc-reads-docstrings-as-google-style) and a link to
`oscal_bindings.v1.models`.

Alternative: include `README.md` in the docstring with `.. include::`. Its links to `LICENSE` and `NOTICE` are
relative, so they break on the site. `help(oscal_bindings)` also shows the directive as text. Rejected.

### D6: The models module gets its own page

The script documents `oscal_bindings.v1.models`. A trial build gave a page of about 250 entries (5 MB) at
`oscal_bindings/v1/models.html`, and the site grew from 1.3 MB to 11 MB. Code spans and annotations on the
`oscal_bindings.v1` page, such as the field types of `CatalogDocument`, then link into it.

Alternative: add the models to `oscal_bindings.v1.__all__`. That changes the public surface. It also puts about 250
entries on the page that holds the 50 functions and classes that a reader looks for first. Rejected.

### D7: The `attest` job signs `api-docs.zip`

The tag build already runs `hatch run docs` in the `checks` job. The `attest` job downloads the `api-docs` artifact
into a directory of its own, and writes `dist/api-docs.zip` from inside that directory. Thus `index.html` is at the
root of the zip. It adds the zip to the subjects that it signs, and uploads it as the artifact `release-docs`. The
`draft-release` job downloads `release-docs` into `dist/` beside the packages, so `gh release create "$TAG" dist/*`
attaches it.

The name `api-docs.zip` matches neither `*.whl` nor `*.tar.gz`. Thus `pypi-publish` does not download it, and its
test for one wheel and one sdist does not change.

Alternative: the deploy downloads the `api-docs` workflow artifact of the tag build. A workflow artifact expires after
90 days, and the artifact has no provenance. Rejected.

### D8: `pages-deploy` runs after `pypi-publish`

`release.yml` gets a second job, `pages-deploy`, with `needs: pypi-publish`. Its properties:

1. It uses the environment `github-pages`, with the URL from the deploy step.
2. Its permissions are `contents: read`, `pages: write`, and `id-token: write`. The permissions of `pypi-publish` do
   not change.
3. It has `concurrency: { group: pages, cancel-in-progress: false }`, so two deploys do not run at the same time.
4. Its steps:
   1. Compare the tag with the latest release (`gh release view --json tagName`). When they differ, the job writes a
      notice and stops with success. Thus a pre-release, or a release of a lower version that a maintainer publishes
      after a higher one, does not replace the site.
   2. Download `api-docs.zip` from the release with `gh release download --pattern api-docs.zip`.
   3. Verify the provenance of the zip with the `gh attestation verify` command of `pypi-publish`: the same signer
      workflow, source ref, and source digest.
   4. Unzip it into `site/`, and fail when `site/index.html` does not exist.
   5. Upload `site/` with `actions/upload-pages-artifact`, and deploy it with `actions/deploy-pages`.

A failed `pypi-publish` skips `pages-deploy`, so the site keeps the docs of the last release on PyPI. A
`workflow_dispatch` run that retries a failed PyPI upload deploys the docs when the retry succeeds. If only the deploy
fails, "Re-run failed jobs" on that run deploys again and does not repeat the PyPI upload.

Alternative: deploy from `build.yml` on the tag push. The docs then go live for a draft before its packages are on
PyPI, or for a draft that is never published. Rejected.

### D9: A maintainer sets the repo settings by hand

A workflow cannot enable Pages or create an environment with its own token. DEVELOPING.md gets the `gh api` commands,
which a maintainer runs one time before the first release that deploys:

1. Enable Pages with the "GitHub Actions" source (`build_type=workflow`).
2. Create or update the `github-pages` environment with the reviewer and the 10-minute wait timer of `pypi`, and custom
   deployment rules.
3. Add a `v*` tag deployment rule to `github-pages`. The default rule of the environment allows only the default
   branch, and the ref of a release run is the tag.

## Risks / Trade-offs

1. [The template of D4 depends on the macro names of the pdoc default template, and the filter imports
   `formatannotation` from the private module `pdoc._compat`. A pdoc upgrade can break either.] → The checks of D1
   fail the build when the duplicates or the Pydantic internals come back. The lockfile pins pdoc, so only
   `hatch run upgrade` moves it.
2. [The models page is 5 MB, and a browser takes time to open it.] → Search finds a model with no need to scroll the
   page. Each annotation links to the entry.
3. [The required reviewer and the wait timer delay the site for 10 minutes or more after PyPI gets the packages.] →
   The delay is a choice of the maintainer, and the settings of D9 can change it.
4. [If a maintainer publishes a release before the settings of D9 exist, `pages-deploy` fails after the PyPI upload.]
   → The packages are on PyPI, and the site keeps its old docs. Apply the settings, then use "Re-run failed jobs".
5. [`release.yml` runs from the tagged commit. A defect in `pages-deploy` thus stays in the run of that release, and a
   fix on `main` does not reach it. That release gets no deployed docs, and the next release deploys.] → Before the
   merge, a task runs the zip and unzip commands of D7 and D8 on a local build.

## Migration Plan

1. Merge the change. The first CI runs show the new docs in the `api-docs` artifact. No deploy runs.
2. Apply the settings of [D9](#d9-a-maintainer-sets-the-repo-settings-by-hand).
3. The next published release deploys the site.

Rollback: revert the change. The site keeps the last deployed docs until a maintainer disables Pages.
