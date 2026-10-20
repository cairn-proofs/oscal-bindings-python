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
pip install "git+https://github.com/cairn-proofs/oscal-bindings-python.git@main"
```

## Known issue: Invalid OSCAL JSON keys can be silently lost

> [!IMPORTANT]
> On pydantic 2.13.x, which `pip install` picks today, the JSON parsers silently discard any key spelled with a Python field name (`back_matter`) instead of its OSCAL name (`back-matter`), along with that key's entire value. `validate_oscal` still reports the document as valid. Tracked in [#6](https://github.com/cairn-proofs/oscal-bindings-python/issues/6).

Verified on pydantic 2.13.5. What happens:

- `parse_oscal`, `parse_oscal_file`, the typed `parse_*` functions, and `model_validate_json` accept the document with the field unset.
- `validate_oscal` returns `True`, so it can't catch the mistake.
- A missing required field is reported only as `missing` at its OSCAL name, which hides the real cause.
- If both spellings are present, the OSCAL-name value wins and the other key is ignored.

```python
doc = parse_oscal('{"catalog": {..., "back_matter": {"resources": [...]}}}')
doc.root.catalog.back_matter    # None: the back-matter is gone
```

You're most likely to hit this with hand-written JSON, or with output from `model_dump(by_alias=False)` that's fed back in. Unknown keys (`bogus`, `back-matterr`) are still rejected, and dict input is rejected on every supported pydantic version.

**Workaround:** if your input might not come from a conforming OSCAL tool, validate it as a dict. Dict validation rejects field-name keys with `extra_forbidden`:

```python
import json
from oscal_bindings import CatalogDocument, OscalDocument

CatalogDocument.model_validate(json.loads(text))   # known type: clearest errors
OscalDocument.model_validate(json.loads(text))     # any of the 8 document types
```

This raises `pydantic.ValidationError`, not `OscalParseError`. Pinning `pydantic<2.13` probably avoids the bug too, but that hasn't been verified.

This is an upstream pydantic-core bug in its new 2.13 JSON validation path. The fix is [pydantic/pydantic#13275](https://github.com/pydantic/pydantic/pull/13275), which hasn't merged yet. Once a fixed release ships, this library will raise its pydantic floor to that release.

## Upgrading to 0.3.0

Version 0.3.0 is a breaking release. The class names now follow the naming manifest of the
[OSCAL bindings specs](https://github.com/cairn-proofs/oscal-bindings-specs), so each OSCAL type has the same name in
every language binding. The serialized OSCAL JSON does not change. Parsing is stricter where the schema is strict, and
some parsed values have a different Python type (items 5 to 9). The release has no deprecated aliases, because an alias
for a reused name would point at the wrong type.

1. About 95 classes have a new name. Some examples:

   | 0.2.x | 0.3.0 |
   | --- | --- |
   | `Algorithm` | `HashAlgorithm` |
   | `Type3` | `DefinedComponentType` |
   | `ProfileGroup1` | `ProfileGroupWithGroups` |
   | `Resource` | `BackMatterResource` |
   | `Rlink` | `BackMatterResourceRlink` |

2. Five names now name a different type. Check each use of these names:

   | Name | Type in 0.3.0 | Name of the 0.2.x type in 0.3.0 |
   | --- | --- | --- |
   | `Status` | Status of the system in an SSP | `SystemComponentStatus` |
   | `Origin` | Origin of a finding, observation, or risk, with `related_tasks` | `PoamItemOrigin` |
   | `LocalDefinitions` | Local definitions of a POA&M | `AssessmentPlanLocalDefinitions` |
   | `MergeFlat` | The `flat` directive of a profile merge (no fields) | `MergeWithFlat` |
   | `MergeCustom` | The `custom` grouping of a profile merge | `MergeWithCustom` |

3. `ExternalId` and `ExternalId1` are one class now: `MetadataPartyExternalId`.
4. Each union of OSCAL types has a type alias, for example `CatalogGroup` for
   `CatalogGroupWithControls | CatalogGroupWithGroups`.
5. Closed enums reject values outside the enum
   ([#21](https://github.com/cairn-proofs/oscal-bindings-python/issues/21)). For example, a field of type
   `ParameterSelectionHowMany` accepts `one` and `one-or-more`, and a document with `"how-many": "many"` raises
   `OscalParseError`.
6. A closed-enum field holds an `Enum` member, not a `str`. Thus `sel.how_many == "one-or-more"` is `False`. Compare
   the value with `ParameterSelectionHowMany.one_or_more`, or compare `sel.how_many.value` with the string. An
   open-enum field, such as `Hash.algorithm`, holds a `str` when it is parsed from a string.
7. In a profile merge, `combine` and `flat` are the empty models `MergeCombine` and `MergeFlat`, with
   `extra='forbid'`. They are not `dict` values. Thus `merge.combine["method"]` and `merge.combine == {}` do not work.
   A non-empty object fails validation, as in 0.2.x.
8. `MappingCollection.mappings` is always a `MappingCollectionMappings` root model. Read the item or the list
   through `.root`.
9. The variants of each union are in manifest order. Data that has no variant property parses as the first variant.
   For example, a `Parameter` with no `select` and no `values` parses as `ParameterWithSelect`. The serialized JSON
   does not change.
10. The strings of `get_supported_element_types()` follow the new class names, for example `rlink` is now
    `back-matter-resource-rlink`.

The [release notes of v0.3.0](https://github.com/cairn-proofs/oscal-bindings-python/releases/tag/v0.3.0) list each
renamed, removed, and added name, and each changed element-type string.

## Import paths

The bindings live under a namespace scoped to the OSCAL **major** version:

```python
from oscal_bindings.v1 import parse_oscal, OscalDoc, Catalog
```

The top-level package re-exports the current major version, so `from oscal_bindings import parse_oscal` (and `oscal_bindings.models`, `oscal_bindings.parser`, `oscal_bindings.extensions`) resolves to the same objects:

```python
import oscal_bindings
import oscal_bindings.v1

oscal_bindings.Catalog is oscal_bindings.v1.models.Catalog   # True
```

Examples below use the shorter top-level path. Importing from `oscal_bindings.v1` is equivalent and states which OSCAL major version your code is written against.

OSCAL is backward-compatible within a major version, so a routine 1.x schema refresh regenerates `v1` in place and never changes your imports. Only OSCAL 2.0 would introduce a second namespace.

### Which OSCAL release?

`__oscal_schema_version__` reports the exact release the models were generated from:

```python
from oscal_bindings import __oscal_schema_version__

__oscal_schema_version__      # '1.2.3'
```

Worth checking, because models are strict about unknown fields: a document from a newer 1.x release than the vendored one can fail validation on a field these bindings have never seen. The constant makes that gap visible rather than a mystery.

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

`parse_oscal` and the per-type parsers accept either `str` or `bytes`. Passing `bytes` directly skips a UTF-8 decode step, which avoids one document-size string allocation — preferable when the document comes from a byte-source (HTTP response body, S3 GET, container layer pull):

```python
import urllib.request

with urllib.request.urlopen("https://example.com/catalog.json") as resp:
    doc = parse_oscal(resp.read())     # bytes → parsed model, no .decode() needed
```

Invalid UTF-8 bytes surface as `OscalParseError`, the same exception type used for JSON and schema validation failures.

### Accessing Parsed Data

```python
catalog = parse_catalog(json_string)
print(catalog.catalog.metadata.title)       # plain str
print(catalog.catalog.metadata.version)
```

### Accessors

`OscalDoc` is a uniform facade over any of the 8 parsed wrappers (`CatalogDocument`, `ProfileDocument`, `SystemSecurityPlanDocument`, …). It exposes the structural fields shared across every OSCAL top-level document — `metadata`, `oscal_version`, `uuid` — without making the caller dispatch on body type.

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

For Assessment Plans and Assessment Results, `assessment_period()` returns the `(start, end)` date range:

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

Every model serializes to valid OSCAL by default: OSCAL key names (`media-type`, not `media_type`) and no `null` for unset fields, on every path. That covers `model_dump()`, `model_dump(mode="json")`, `model_dump_json()`, `pydantic_core.to_json(...)`, and `TypeAdapter(...).dump_python(...)`, including models nested in plain dicts and lists. Framework serializers that never pass kwargs (e.g. MCP or agent tool results) get valid OSCAL too. `serialize_oscal` is still the recommended call for whole documents.

```python
from oscal_bindings import make_rlink

rlink = make_rlink("https://example.com/a.pdf", media_type="application/pdf")
rlink.model_dump_json()                 # '{"href":"https://example.com/a.pdf","media-type":"application/pdf"}'
rlink.model_dump(by_alias=False)        # {'href': '...', 'media_type': 'application/pdf'}
```

Opt-outs:

- `by_alias=False` emits Python field names, still without `null`.
- `exclude_none=False` has no effect. OSCAL forbids `null`, so None-valued fields are always omitted. To tell whether a field was set, use attribute access (`rlink.hashes is None`) or `model_fields_set`.

### Field names vs. OSCAL names

Python code can use field names; OSCAL data must use OSCAL names.

- Constructor keyword arguments accept either: `BackMatterResourceRlink(href=..., media_type=...)` and `BackMatterResourceRlink(href=..., **{"media-type": ...})` build the same model. Plain dicts nested inside the kwargs are OSCAL data and must use OSCAL names.
- Dict input (`Model.model_validate(...)`, `validate_element`) rejects a field name at any depth with `extra_forbidden`.
- JSON input (`parse_oscal`, `parse_oscal_file`, `validate_oscal`, the typed `parse_*` functions, `model_validate_json`) never populates a field from a field name key.

On pydantic 2.13.x, JSON input drops a field-name key without an error instead of rejecting it. See [Known issue: Invalid OSCAL JSON keys can be silently lost](#known-issue-invalid-oscal-json-keys-can-be-silently-lost).

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
hatch run release  # generate + lint + typing + security + test + coverage + docs
```

`hatch run generate` and `hatch test` download the pinned spec artifact once into `tests/.corpus_cache/`, so the first run needs network access.

## Architecture

- **Version package** (`src/oscal_bindings/v1/`) — everything below, scoped to the OSCAL major version. Exposes `__oscal_schema_version__`.
- **Generated models** (`src/oscal_bindings/v1/models.py`) — Pydantic v2 classes with `Annotated` field constraints, produced by `datamodel-code-generator` from the OSCAL JSON Schema.
- **Model base** (`src/oscal_bindings/v1/_base.py`) — hand-written `OscalBaseModel`, which every generated object model inherits via `--base-class`: OSCAL keys and no nulls by default, field-name constructor kwargs.
- **Names** — every type name comes from the naming manifest (`names.json`) of the pinned spec artifact of [oscal-bindings-specs](https://github.com/cairn-proofs/oscal-bindings-specs). `scripts/hoist_names.py` writes a copy of the schema in which each manifest type is a definition with its canonical name, and codegen reads that copy.
- **Post-processing** (`scripts/postprocess_models.py`) — collapses scalar root models, adds the union type aliases, `MappingCollectionMappings`, and `OscalDocument`, and checks every module-level name against the manifest.
- **Vendored schemas** (`schemas/<release>/`) — one directory per OSCAL release; the active bundle is chosen by explicit path.
- **Runtime** (`src/oscal_bindings/v1/parser.py`) — parse / serialize / validate utilities and per-type typed parsers.
- **Extensions** (`src/oscal_bindings/v1/extensions/`) — hand-written helpers layered on top of the generated models:
  - `document.py` — `OscalDoc` facade (uniform `metadata` / `uuid` / `oscal_version` / `assessment_period()` accessors).
  - `builders.py` — `make_hash`, `make_rlink`, `make_resource` constructors for `back-matter` elements.
  - `validate_element.py` — element-level schema validation utilities.
- **Top-level package** (`src/oscal_bindings/__init__.py` and the `models` / `parser` / `extensions` alias modules) — pure re-exports of the current version package.

Public symbols are re-exported from `oscal_bindings.v1` and from the top-level `oscal_bindings` package, so callers don't need to know which submodule a name lives in.

## Requirements

- Python 3.11+ (tested on 3.11–3.14)
- Pydantic 2.11+

## License

Apache License 2.0; see [LICENSE](LICENSE). The vendored OSCAL schemas are from NIST and are in the public domain; see [NOTICE](NOTICE).
