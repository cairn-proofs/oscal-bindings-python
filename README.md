# oscal-bindings (Python)

Typed Python data bindings for [OSCAL](https://pages.nist.gov/OSCAL/) (Open Security Controls Assessment Language) v1.2.3, generated from the official NIST JSON Schema using datamodel-code-generator (Pydantic v2).

## Installation

```bash
pip install oscal-bindings
# or
uv add oscal-bindings
```

The distribution is `oscal-bindings`; the import package is `oscal_bindings`.

To install from a local checkout (e.g., as a `uv` workspace path dependency):

```bash
uv add ../oscal-bindings-python
# or
pip install -e ../oscal-bindings-python
```

To install directly from a Git tag, branch, or commit:

```bash
pip install "git+https://github.com/cairn-proofs/oscal-bindings-python.git@v0.1.0"
```

## Import paths

The bindings live under a namespace scoped to the OSCAL **major** version:

```python
from oscal_bindings.v1 import parse_oscal, OscalDoc, Catalog
```

The flat paths that predate the `v1` namespace remain fully supported — the top-level
package is a re-export shim, so `from oscal_bindings import parse_oscal`,
`oscal_bindings.models`, `oscal_bindings.parser`, and `oscal_bindings.extensions` all
keep resolving, to the same objects:

```python
import oscal_bindings
import oscal_bindings.v1

oscal_bindings.Catalog is oscal_bindings.v1.models.Catalog   # True
```

Examples below use the flat path. `oscal_bindings.v1` works identically and is the
better choice for new code, since it says which major version you're binding against.

OSCAL is backward-compatible within a major version, so a routine 1.x schema refresh
regenerates `v1` in place and never changes your imports. Only OSCAL 2.0 would
introduce a second namespace.

### Which OSCAL release?

`__oscal_schema_version__` reports the exact release the models were generated from:

```python
from oscal_bindings import __oscal_schema_version__

__oscal_schema_version__      # '1.2.3'
```

Worth checking, because models are strict about unknown fields: a document from a
newer 1.x release than the vendored one can fail validation on a field these bindings
have never seen. The constant makes that gap visible rather than a mystery.

## Usage

### Parsing

```python
from oscal_bindings import parse_oscal, parse_oscal_file, parse_catalog, parse_profile

# Parse any OSCAL document
doc = parse_oscal(json_string)

# Parse with type-specific convenience functions
catalog = parse_catalog(json_string)    # returns CatalogDocument
profile = parse_profile(json_string)    # returns ProfileDocument

# Parse from a file
doc = parse_oscal_file("catalog.json")
```

`parse_oscal` and the per-type parsers accept either `str` or `bytes`.
Passing `bytes` directly skips a UTF-8 decode step, which avoids one
document-size string allocation — preferable when the document comes
from a byte-source (HTTP response body, S3 GET, container layer pull):

```python
import urllib.request

with urllib.request.urlopen("https://example.com/catalog.json") as resp:
    doc = parse_oscal(resp.read())     # bytes → parsed model, no .decode() needed
```

Invalid UTF-8 bytes surface as `OscalParseError`, the same exception
type used for JSON and schema validation failures.

### Accessing Parsed Data

```python
catalog = parse_catalog(json_string)
print(catalog.catalog.metadata.title)       # direct string access
print(catalog.catalog.metadata.version)     # no .root needed
```

### Accessors

`OscalDoc` is a uniform facade over any of the 8 parsed wrappers
(`CatalogDocument`, `ProfileDocument`, `SystemSecurityPlanDocument`,
…). It exposes the structural fields shared across every OSCAL
top-level document — `metadata`, `oscal_version`, `uuid` — without
making the caller dispatch on body type.

```python
from oscal_bindings import OscalDoc

doc = OscalDoc.from_file("ssp.json")
doc.oscal_version          # '1.2.0'
doc.uuid                   # body-level UUID, regardless of document type
doc.metadata.title
doc.body                   # the underlying Catalog | Profile | SSP | ...
```

Wrap an already-parsed document directly:

```python
from oscal_bindings import OscalDoc, parse_oscal_file

doc = OscalDoc(parse_oscal_file("ssp.json"))
```

For Assessment Plans and Assessment Results, `assessment_period()`
returns the `(start, end)` date range:

```python
from oscal_bindings import OscalAccessError

doc = OscalDoc.from_file("assessment-results.json")
start, end = doc.assessment_period()       # (date(2025, 1, 5), date(2025, 1, 30))

try:
    OscalDoc.from_file("catalog.json").assessment_period()
except OscalAccessError as e:
    print(e)                               # only defined for AP / AR
```

### Building back-matter resources

```python
from oscal_bindings import make_hash, make_resource, make_rlink

digest = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
resource = make_resource(
    title="Evidence: signed audit report",
    description="Q1 audit deliverable, two equivalent mirrors.",
    rlinks=[
        make_rlink("https://example.com/audit-q1.pdf", media_type="application/pdf",
                   hashes=[make_hash(digest)]),
        make_rlink("s3://evidence-bucket/audit-q1.pdf",
                   hashes=[make_hash(digest)]),
    ],
)
# resource.uuid is a freshly generated UUID4
```

### Serialization

```python
from oscal_bindings import serialize_oscal

json_str = serialize_oscal(doc)                # pretty-printed (indent: 2)
json_str = serialize_oscal(doc, indent=None)   # compact
```

### Validation

```python
from oscal_bindings import validate_oscal

if validate_oscal(json_string):
    print("Valid OSCAL document")
```

### Error Handling

```python
from oscal_bindings import parse_oscal, OscalParseError

try:
    parse_oscal(invalid_json)
except OscalParseError as e:
    print(e)          # Human-readable message
    print(e.errors)   # Pydantic validation error details
```

## Typed Parser Functions

Each OSCAL document type has a dedicated parser:

- `parse_catalog(json)` → `CatalogDocument`
- `parse_profile(json)` → `ProfileDocument`
- `parse_component_definition(json)` → `ComponentDefinitionDocument`
- `parse_system_security_plan(json)` → `SystemSecurityPlanDocument`
- `parse_assessment_plan(json)` → `AssessmentPlanDocument`
- `parse_assessment_results(json)` → `AssessmentResultsDocument`
- `parse_plan_of_action_and_milestones(json)` → `PlanOfActionAndMilestonesDocument`
- `parse_mapping_collection(json)` → `MappingCollectionDocument`

## Building

```bash
hatch build
hatch run release  # generate + test + coverage + docs
```

## Architecture

- **Version package** (`src/oscal_bindings/v1/`) — everything below, scoped to the OSCAL major version. Exposes `__oscal_schema_version__`.
- **Generated models** (`src/oscal_bindings/v1/models.py`) — Pydantic v2 `BaseModel` classes with `Annotated` field constraints, produced by `datamodel-code-generator` from the OSCAL JSON Schema.
- **Post-processing** (`scripts/postprocess_models.py`) — renames classes from schema namespace paths to clean short names, deriving the document-wrapper names from the generated content rather than class ordering.
- **Vendored schemas** (`schemas/<release>/`) — one directory per OSCAL release; the active bundle is chosen by explicit path.
- **Runtime** (`src/oscal_bindings/v1/parser.py`) — parse / serialize / validate utilities and per-type typed parsers.
- **Extensions** (`src/oscal_bindings/v1/extensions/`) — hand-written helpers layered on top of the generated models:
  - `document.py` — `OscalDoc` facade (uniform `metadata` / `uuid` / `oscal_version` / `assessment_period()` accessors).
  - `builders.py` — `make_hash`, `make_rlink`, `make_resource` constructors for `back-matter` elements.
  - `validate_element.py` — element-level schema validation utilities.
- **Compatibility shim** (`src/oscal_bindings/__init__.py` and the `models` / `parser` / `extensions` alias modules) — pure re-exports of the version package, keeping the flat import paths working.

Public symbols are re-exported from `oscal_bindings.v1` and from the top-level `oscal_bindings` package, so callers don't need to know which submodule a name lives in.

## Requirements

- Python 3.11+
- Pydantic v2

## License

Apache License 2.0; see [LICENSE](LICENSE). The vendored OSCAL schemas are from NIST
and are in the public domain; see [NOTICE](NOTICE).
