# Design

## Context

See [proposal.md - Why](proposal.md#why) for the motivation. These facts constrain the approach.

1. The `docs` script in `pyproject.toml` is `pdoc oscal_bindings oscal_bindings.v1 -o build/api-docs`. pdoc is pinned
   by the lockfile of the `default` env (16.0.0). The `hatch-test` env does not have pdoc. The `checks` job of
   `build.yml` runs the script on each CI run and uploads `build/api-docs` as the artifact `api-docs`.
2. pdoc documents the names in the `__all__` of a module. `oscal_bindings.__all__` is `oscal_bindings.v1.__all__`, so
   the two pages have the same entries. `oscal_bindings.v1.__all__` holds 10 classes that `v1/models.py` defines:
   `OscalDocument`, the 8 document wrappers such as `CatalogDocument`, and `DocumentId`. It holds no other model.
3. pdoc supports Pydantic models, but its output is wrong for the generated models in these ways:
   1. The annotation of a field is the full `Annotated[...]` text, with the `FieldInfo(...)` repr and the address of
      the `omit_none` function in it.
   2. A required field shows the default `= PydanticUndefined`.
   3. A scalar alias such as `StringDatatype` shows its value as the same `Annotated[...]` text.
   4. `OscalDocument` and `MappingCollectionMappings` have no docstring of their own, so they show the docstring of
      Pydantic's `RootModel`: a raw mkdocs admonition and a dead relative link. They also show the base
      `typing.Generic[~RootModelRootType]` and the attribute `__pydantic_root_model__`.

   pdoc writes the annotation and the default of each variable into the search index from the properties of its
   `pdoc.doc.Variable` objects, not through the template. The 10 model classes on the current `oscal_bindings.v1`
   page already show these defects.
4. Pydantic registers two `RootModel[...]` parametrizations in `models` under names that are not identifiers.
5. pdoc changes each Sphinx role to a code span, but it keeps the `~` prefix and the full private module path. Thus
   ``:class:`~oscal_bindings.v1.models.CatalogDocument` `` shows as the literal text
   `~oscal_bindings.v1.models.CatalogDocument`. Hand-written modules under `src/oscal_bindings/` hold 67 roles, 17 of
   them with a `~` prefix, all in `v1/extensions/yaml_io.py`.
6. pdoc links a code span that names a member of a documented class. But a class can take a member from a base
   outside the package, and pdoc renders no entry for such a member. The docstrings of `OscalDateTime` and
   `OscalReadError` name such members (`now`, `timestamp`, `errno`, and others). Thus `oscal_bindings/v1.html` has 12
   links to anchors that do not exist.
7. A `v*` tag push runs `build.yml`. Its `attest` job signs the wheel and the sdist, and its `draft-release` job
   attaches them to a draft release. Publishing the draft runs `release.yml` from the tagged commit. Its one job,
   `pypi-publish`, downloads the assets with `--pattern "*.whl" --pattern "*.tar.gz"`, requires one wheel and one
   sdist, verifies their provenance with `gh attestation verify`, and uploads them to PyPI.
8. The `pypi` environment has a `v*` tag deployment rule, a required reviewer, and a 10-minute wait timer. GitHub Pages
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

1. Applies the corrections of [D4](#d4-the-script-corrects-the-pydantic-output-of-pdoc) to the classes of `pdoc.doc`.
2. Calls the pdoc command line (`pdoc.__main__.cli`) with these arguments:
   1. `-d google` ([D2](#d2-pdoc-reads-docstrings-as-google-style)).
   2. `-t docs/pdoc-templates` ([D4](#d4-the-script-corrects-the-pydantic-output-of-pdoc)).
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
   3. No HTML page and not `search.js` contains `FieldInfo(`, `PydanticUndefined`, a memory address (`at 0x`),
      `RootModel[`, `Generic[~`, `__pydantic_`, the admonition marker `!!! `, or `~oscal_bindings`.
   4. Each local link of each HTML page goes to a page that exists and, when the link has a fragment, to an `id` on
      that page. A link inside JavaScript text, such as `${url}`, is not a link.
   5. `index.html` and `oscal_bindings/v1/models.html` exist.

The `Docs` step of the `checks` job sets `DOCS_SOURCE_REF` to the tag name on a tag build, and to `github.sha` on each
other build.

`tests/test_build_docs.py` imports the script with `load_script`. The script imports pdoc at the top, so the
`hatch-test` env gets `pdoc` in its `extra-dependencies`. The `default` env constrains its version, so the tests and
`hatch run docs` use the same pdoc. The four `hatch-test` lockfiles change with it.

Alternative: keep the pdoc command line in `pyproject.toml`. The pdoc command line cannot change the `pdoc.doc`
classes, and nothing checks the output. Rejected. Alternative: import pdoc only inside the function that builds, so
the tests need no pdoc. The correction code then cannot use pdoc's own annotation formatter in a test. Rejected.

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

A code span can name a member that a class takes from a base outside the package. Such a code span names the
member with its base class, for example `` `datetime.timestamp()` `` in place of `` `timestamp()` ``. pdoc does not
document `datetime`, so it does not link the name, and the dead links of [Context](#context) item 6 go. This is a
markup change: the text still names the same member.

A new test, `tests/test_docstring_markup.py`, reads the text of each `.py` file under `src/oscal_bindings/` except
`v1/models.py`. It fails for each match of `:(mod|class|func|meth|attr|exc|data|obj):`` ` ``, and the message names the
file and the line. The test reads the source text, so it finds a role in a comment too. A comment does not need a
role, so this is no loss.

### D4: The script corrects the Pydantic output of pdoc

pdoc writes the HTML pages and the search index from the same `pdoc.doc` objects. Thus the script corrects these
properties of the `pdoc.doc` classes before it calls pdoc, and one correction covers both outputs:

1. `Variable.annotation_str`: the script removes each `Annotated[...]` wrapper and its metadata, at each depth, and
   formats the type that is left with pdoc's own formatter. The result keeps the qualified names, for example
   `: list[oscal_bindings.v1.models.ParameterWithSelect | oscal_bindings.v1.models.ParameterWithValues] | None`. The
   default template sends it through `linkify`, which links each name and shows it short.
2. `Variable.default_value_str`: empty for `PydanticUndefined`, so a required field shows no default. For a scalar
   alias, the type that item 1 gives, for example `StringDatatype = str`. Each other value keeps the pdoc result.
3. `Class.docstring`: empty for a Pydantic model class that does not define its own docstring. Thus a class takes no
   docstring from `RootModel` or from `BaseModel`.
4. `Class.bases`: without `typing.Generic[...]`.

A pdoc template directory, `docs/pdoc-templates/`, holds one file, `module.html.jinja2`. It extends the default module
template and overrides the `is_public` macro. These members are not public:

1. Each member of the module `oscal_bindings` that is not a module. Thus `oscal_bindings.v1` is the canonical page of
   each object.
2. Each member of `oscal_bindings.v1.models` whose name is in `oscal_bindings.v1.__all__`. Thus the 10 classes of
   [Context](#context) item 2 have one entry, on the `oscal_bindings.v1` page.
3. Each member whose name is not an identifier (the `RootModel[...]` entries), or starts with `__pydantic`.

Each other member gets the default answer. pdoc builds the search index with the same macro, and a link to a hidden
member goes to its public entry.

A trial build with these corrections and this template gave 0 matches for each string of D1 check 3, in each HTML page
and in `search.js`. The only dead local links were the 12 of [Context](#context) item 6.

Alternative: override the `annotation` and `default_value` macros of the template. The search index does not use the
template, so search keeps the defects. Rejected. Alternative for the duplicates: document only `oscal_bindings.v1`.
The site then has no page for the import path that most examples use. Rejected. Alternative: give `oscal_bindings` a
different `__all__`. That changes the public surface. Rejected.

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
`oscal_bindings/v1/models.html`, and the site grew from 1.3 MB to 11 MB. Annotations on the `oscal_bindings.v1` page,
such as the field types of `CatalogDocument`, then link into it.

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

### D8: `pages-deploy` runs after `pypi-publish`, for the latest release only

`release.yml` gets two jobs:

1. `docs-latest`, with `needs: pypi-publish`, no environment, and `contents: read`. It compares the tag with the
   release that GitHub marks as the latest (`gh release view --json tagName`), and sets the output `latest` to `true`
   or `false`. A pre-release is never the latest release.
2. `pages-deploy`, with `needs: docs-latest` and `if: needs.docs-latest.outputs.latest == 'true'`. Its properties:
   1. It uses the environment `github-pages`, with the URL from the deploy step.
   2. Its permissions are `contents: read`, `pages: write`, and `id-token: write`. The permissions of `pypi-publish`
      do not change.
   3. It has `concurrency: { group: pages, cancel-in-progress: false }`, so two deploys do not run at the same time.
   4. Its steps:
      1. Download `api-docs.zip` from the release with `gh release download --pattern api-docs.zip`.
      2. Verify the provenance of the zip with the `gh attestation verify` command of `pypi-publish`: the same signer
         workflow, source ref, and source digest.
      3. Unzip it into `site/`, and fail when `site/index.html` does not exist.
      4. Upload `site/` with `actions/upload-pages-artifact`, and deploy it with `actions/deploy-pages`.

GitHub applies the reviewer and the wait timer of `github-pages` before the first step of a job. A skipped
`pages-deploy` does not start, so a release that is not the latest asks for no approval.

The guard follows GitHub's latest flag, not the version number. When a maintainer publishes a release, "Set as the
latest release" is checked by default. DEVELOPING.md tells the maintainer to clear it for a release of an older line.

A failed `pypi-publish` skips both jobs, so the site keeps the docs of the last release on PyPI. A `workflow_dispatch`
run that retries a failed PyPI upload deploys the docs when the retry succeeds. If only the deploy fails, "Re-run
failed jobs" on that run deploys again and does not repeat the PyPI upload.

Alternative: deploy from `build.yml` on the tag push. The docs then go live for a draft before its packages are on
PyPI, or for a draft that is never published. Rejected. Alternative: compare the tag in the first step of
`pages-deploy`. Each release that is not the latest then waits for the reviewer and the timer before the job skips.
Rejected.

### D9: A maintainer sets the repo settings by hand

A workflow cannot enable Pages or create an environment with its own token. DEVELOPING.md gets the `gh api` commands,
which a maintainer runs one time before the first release that deploys:

1. Enable Pages with the "GitHub Actions" source (`build_type=workflow`).
2. Create or update the `github-pages` environment with the reviewer and the 10-minute wait timer of `pypi`, and custom
   deployment rules.
3. Add a `v*` tag deployment rule to `github-pages`. The default rule of the environment allows only the default
   branch, and the ref of a release run is the tag.

## Risks / Trade-offs

1. [The corrections of D4 replace properties of `pdoc.doc` classes, and the template depends on the macro names of
   the pdoc default template. A pdoc upgrade can break either.] → The checks of D1 fail the build when a defect comes
   back. The lockfile pins pdoc, so only `hatch run upgrade` moves it.
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
