# Proposal

## Why

The binding has no published API docs ([#90]). `hatch run docs` builds pdoc HTML into `build/api-docs`, and CI keeps it
only as the `api-docs` workflow artifact. A user must download the artifact to read it.

The current output also fails as a reference:

1. pdoc reads the docstrings as reStructuredText, but the docstrings use Google-style sections. Thus `Args:`,
   `Returns:`, and `Raises:` show as plain paragraphs. The `Key Classes:` and `Key Functions:` lists of the
   `oscal_bindings.v1` docstring show as one paragraph with no links.
2. Hand-written docstrings use Sphinx roles (`:func:`, `:class:`, `:mod:`, `:attr:`). pdoc keeps the `~` prefix and
   the private module path of a role, so a reader sees text such as `~oscal_bindings.v1.models.CatalogDocument`.
3. Each public object has two entries, one on the `oscal_bindings` page and one on the `oscal_bindings.v1` page,
   because the top level re-exports `v1`. Search gives each object two times.
4. Most generated models have no entries. pdoc follows `oscal_bindings.v1.__all__`, which holds 50 names. Only 10 of
   them are generated models: `OscalDocument`, the 8 document wrappers, and `DocumentId`. Thus a reader cannot find
   the fields of `Catalog` or of any other model. The 10 models that the page does document show Pydantic internals:
   a `FieldInfo(...)` repr in each field type, and `= PydanticUndefined` on each required field.
5. The site root is a redirect to the `oscal_bindings` page. That page has no overview of the project.

## What Changes

1. `hatch run docs` builds a reference that renders correctly:
   1. pdoc reads docstrings as Google style.
   2. Hand-written docstrings use Markdown code spans, not Sphinx roles. A test keeps the roles out.
   3. `oscal_bindings.v1` is the canonical page of each public object. The `oscal_bindings` page is the home page: a
      short overview of the project, with links into `oscal_bindings.v1`. It lists no objects, and search gives each
      object one time.
   4. `oscal_bindings.v1.models` has a page with an entry for each generated model. A field shows its type and its
      default, with no Pydantic internals.
   5. Each page links to its source file on GitHub at the commit or tag that CI built.
   6. The build fails when its output has a duplicate entry, a Pydantic internal, or a dead local link.
2. Each published release deploys its docs to the GitHub Pages site of the repo,
   <https://cairn-proofs.github.io/oscal-bindings-python/>. The site holds the docs of the latest published release.
   1. A `v*` tag build attaches the docs to the draft release as the asset `api-docs.zip`. The `attest` job signs it
      with the wheel and the sdist. Nothing rebuilds the docs after CI.
   2. When the release is published and the PyPI upload succeeds, a new `pages-deploy` job in `release.yml` verifies
      the provenance of `api-docs.zip` and deploys it. A failed PyPI upload deploys no docs.
      A release that GitHub does not mark as the latest release, such as a pre-release, deploys no docs.
   3. Pushes to `main` and pull requests deploy no docs.
3. The README links to the site. DEVELOPING.md tells how the deploy works and lists the one-time repo settings.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. The change adds no binding behavior. It changes docstrings, the docs build, and CI, so `.openspec.yaml` sets
`skip_specs: true`.

## Impact

1. Docs build: the `docs` script in `pyproject.toml`, a new script `scripts/build_docs.py`, and a new pdoc template
   directory.
2. Docstrings: the module docstrings of `oscal_bindings` and `oscal_bindings.v1`, and the Sphinx roles in eight
   hand-written modules under `src/oscal_bindings/`. No code changes.
3. Tests: a new test that finds Sphinx roles in hand-written docstrings, and tests of `scripts/build_docs.py`.
   The `hatch-test` env gets `pdoc`, so its four lockfiles change.
4. CI: `.github/workflows/build.yml` (`checks`, `attest`, and `draft-release` jobs) and `.github/workflows/release.yml`
   (new `docs-latest` and `pages-deploy` jobs).
5. Repo settings. A maintainer sets them one time by hand:
   1. GitHub Pages with the "GitHub Actions" source.
   2. A `github-pages` environment with a `v*` tag rule, a required reviewer, and a wait timer.
6. Docs: `README.md`, `DEVELOPING.md`, `AGENTS.md`, and `.agents/summary/` pages that describe the docs build or the
   release flow.

[#90]: https://github.com/cairn-proofs/oscal-bindings-python/issues/90
