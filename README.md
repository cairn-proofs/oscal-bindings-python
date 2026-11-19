# oscal-bindings (Python)

<p align="center">
  <a href="https://github.com/cairn-proofs/oscal-bindings-python/actions/workflows/build.yml"><img alt="CI" src="https://github.com/cairn-proofs/oscal-bindings-python/actions/workflows/build.yml/badge.svg?branch=main"></a>
  <a href="https://pypi.org/project/oscal-bindings/"><img alt="PyPI" src="https://img.shields.io/pypi/v/oscal-bindings.svg"></a>
  <a href="https://pypi.org/project/oscal-bindings/"><img alt="Python versions" src="https://img.shields.io/pypi/pyversions/oscal-bindings.svg"></a>
  <a href="https://github.com/cairn-proofs/oscal-bindings-python/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/pypi/l/oscal-bindings.svg"></a>
</p>

Typed Python data bindings for [OSCAL](https://pages.nist.gov/OSCAL/) (Open Security Controls Assessment Language) v1.2.3, generated from the NIST JSON Schema with Pydantic v2.

- **Every OSCAL document type.** Catalog, Profile, Component Definition, System Security Plan, Assessment Plan, Assessment Results, Plan of Action and Milestones, and Mapping Collection, each with a typed parser.
- **Strict input.** A parse rejects unknown fields, Python field names in place of OSCAL names, and values that break an OSCAL pattern, and reports each failure with its location.
- **Valid OSCAL output.** Every serialization path writes OSCAL key names and never writes `null`.
- **Measured performance.** [PERFORMANCE.md](https://github.com/cairn-proofs/oscal-bindings-python/blob/main/PERFORMANCE.md) has the parse, memory, and serialization costs.
- **One runtime dependency.** Only `pydantic`. JSON and YAML input as `str`, `bytes`, or a file path, with YAML as an optional extra.
- **Implements oscal-bindings-specs.** The bindings follow the [language-neutral OSCAL bindings spec](https://github.com/cairn-proofs/oscal-bindings-specs): type names come from its naming manifest, and the tests pass its full conformance corpus. One known gap, a depth limit of `validate_element`, is tracked in [#89](https://github.com/cairn-proofs/oscal-bindings-python/issues/89).

## Installation

```bash
pip install oscal-bindings
```

For YAML support, install `oscal-bindings[yaml]`. Requires Python 3.11+ and Pydantic 2.14.2+. [Installation and versions](https://github.com/cairn-proofs/oscal-bindings-python/blob/main/docs/installation.md) covers uv, local checkouts, and Git installs.

## Quick start

**Parse** a document. Each document type has a typed parser that returns its wrapper (`CatalogDocument` here); `parse_oscal` takes any type.

```pycon
>>> from oscal_bindings import parse_catalog, serialize_oscal, OscalParseError
>>> text = '''{"catalog": {
...   "uuid": "74c8ba1e-5cd4-4ad1-bbfd-d888e2f6c724",
...   "metadata": {"title": "Demo catalog", "last-modified": "2026-01-02T03:04:05Z",
...                "version": "1.0", "oscal-version": "1.2.3"},
...   "controls": [{"id": "ac-1", "title": "Policy and Procedures"}]}}'''
>>> doc = parse_catalog(text)
```

**Read** it as typed Python objects.

```pycon
>>> doc.catalog.metadata.title
'Demo catalog'
>>> doc.catalog.controls[0].id
'ac-1'
```

**Serialize** it back. Output always uses OSCAL key names and omits unset fields.

```pycon
>>> doc.catalog.controls[0].model_dump_json()
'{"id":"ac-1","title":"Policy and Procedures"}'
>>> json_text = serialize_oscal(doc)   # the whole document, indented
```

**Reject** input that is not valid OSCAL. Here a Python field name stands in for an OSCAL name:

```pycon
>>> try:
...     parse_catalog(text.replace('"oscal-version"', '"oscal_version"'))
... except OscalParseError as e:
...     for entry in e.errors:
...         print(entry["type"], entry["loc"])
...
missing ('CatalogDocument', 'catalog', 'metadata', 'oscal-version')
extra_forbidden ('CatalogDocument', 'catalog', 'metadata', 'oscal_version')
```

## Highlights

**One facade for every document type.** `OscalDoc` gives `metadata`, `uuid`, and `oscal_version` without dispatching on the type ([details](https://github.com/cairn-proofs/oscal-bindings-python/blob/main/docs/parsing.md#the-oscaldoc-facade)):

```python
from oscal_bindings import OscalDoc

doc = OscalDoc.from_file("ssp.json")
doc.metadata.title
```

**Back-matter builders** validate as they build ([details](https://github.com/cairn-proofs/oscal-bindings-python/blob/main/docs/models.md)):

```python
from oscal_bindings import make_hash, make_resource, make_rlink

digest = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
resource = make_resource(
    title="Evidence: signed audit report",
    rlinks=[make_rlink("https://example.com/audit-q1.pdf", media_type="application/pdf",
                       hashes=[make_hash(digest)])],
)
```

**YAML** works the same way as JSON, with the `yaml` extra ([details](https://github.com/cairn-proofs/oscal-bindings-python/blob/main/docs/yaml.md)):

```python
from oscal_bindings import parse_oscal_yaml_file, serialize_oscal_yaml

doc = parse_oscal_yaml_file("catalog.yaml")
yaml_text = serialize_oscal_yaml(doc)
```

**Datetimes keep every fraction digit.** OSCAL allows more than the six that `datetime` holds; `OscalDateTime` keeps and writes them all ([details](https://github.com/cairn-proofs/oscal-bindings-python/blob/main/docs/datetimes.md)).

## OSCAL versions

> [!NOTE]
> The models come from one OSCAL release, reported by `oscal_bindings.__oscal_schema_version__` (currently `'1.2.3'`). The models reject unknown fields, so a document from a newer 1.x release can fail on a field they have never seen.

The bindings live in `oscal_bindings.v1`, named for the OSCAL major version, and the top-level package re-exports it, so `from oscal_bindings import parse_oscal` and `from oscal_bindings.v1 import parse_oscal` give the same object. A 1.x schema refresh regenerates `v1` in place and never changes your imports. See [Installation and versions](https://github.com/cairn-proofs/oscal-bindings-python/blob/main/docs/installation.md#import-paths).

## Other Python OSCAL libraries

- [compliance-trestle](https://github.com/oscal-compass/compliance-trestle) is a compliance workflow tool: workspaces, document splitting, Markdown authoring, and CI governance, built on its own OSCAL object model. Use it to run an authoring workflow.
- [oscal](https://github.com/brian-ruf/oscal-class) loads, validates, converts, and queries OSCAL in XML, JSON, and YAML for every published OSCAL version, and resolves profiles and imports. Use it when you need XML, several OSCAL versions at once, or profile resolution.
- [oscal-pydantic-v2](https://github.com/RS-Credentive/oscal-pydantic) provides Pydantic models for OSCAL. Its latest release covers the Catalog and Profile models, without parse or serialize helpers.

oscal-bindings is the typed data-binding layer for one OSCAL release: Pydantic models for all eight document types that type checkers and IDEs understand, strict parsing that reports each failure with its location, valid OSCAL on every serialization path, and no dependency beyond Pydantic.

## Documentation

- [Parsing and reading documents](https://github.com/cairn-proofs/oscal-bindings-python/blob/main/docs/parsing.md): typed parsers, `bytes` input, `OscalDoc`, `validate_oscal`
- [Building and serializing models](https://github.com/cairn-proofs/oscal-bindings-python/blob/main/docs/models.md): builders, field names vs. OSCAL names, serialization defaults
- [Datetimes](https://github.com/cairn-proofs/oscal-bindings-python/blob/main/docs/datetimes.md) and [YAML](https://github.com/cairn-proofs/oscal-bindings-python/blob/main/docs/yaml.md)
- [Errors](https://github.com/cairn-proofs/oscal-bindings-python/blob/main/docs/errors.md): error entries and categories
- [Resource limits](https://github.com/cairn-proofs/oscal-bindings-python/blob/main/docs/limits.md): every parse limit, and garbage-collection tuning
- [Performance](https://github.com/cairn-proofs/oscal-bindings-python/blob/main/PERFORMANCE.md): measured parse, memory, and serialization costs
- API reference: the docstrings; `hatch run docs` builds them into HTML

## Project information

- [Source](https://github.com/cairn-proofs/oscal-bindings-python) · [Issues](https://github.com/cairn-proofs/oscal-bindings-python/issues) · [PyPI](https://pypi.org/project/oscal-bindings/) · [Releases](https://github.com/cairn-proofs/oscal-bindings-python/releases)
- Contributing: [DEVELOPING.md](https://github.com/cairn-proofs/oscal-bindings-python/blob/main/DEVELOPING.md) covers the code generation pipeline, the locked environments, and the architecture.
- Other languages: [oscal-bindings (TypeScript)](https://github.com/cairn-proofs/oscal-bindings-typescript) follows the same [language-neutral contract](https://github.com/cairn-proofs/oscal-bindings-specs).

## License

Apache License 2.0; see [LICENSE](https://github.com/cairn-proofs/oscal-bindings-python/blob/main/LICENSE). The models are generated from the OSCAL JSON Schema of NIST, which is in the public domain; see [NOTICE](https://github.com/cairn-proofs/oscal-bindings-python/blob/main/NOTICE).
