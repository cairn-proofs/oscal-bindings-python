# oscal-bindings (Python)

Typed Python data bindings for [OSCAL](https://pages.nist.gov/OSCAL/) (Open Security Controls Assessment Language) v1.2.3, generated from the official NIST JSON Schema using datamodel-code-generator (Pydantic v2).

## Installation

```bash
pip install oscal-bindings
# or
uv add oscal-bindings
```

The distribution is `oscal-bindings`; the import package is `oscal_bindings`.

YAML parse and serialize are an optional feature. Install the `yaml` extra to add them:

```bash
pip install "oscal-bindings[yaml]"
# or
uv add "oscal-bindings[yaml]"
```

The base install keeps a single runtime dependency (`pydantic[email]`). Every import works without the extra. A call to a YAML operation without the extra raises `ImportError` with an install hint.

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

Worth checking, because models are strict about unknown fields: a document from a newer 1.x release than the one the models come from can fail validation on a field these bindings have never seen. The constant makes that gap visible rather than a mystery.

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

### YAML

With the `yaml` extra installed, `parse_oscal_yaml`, `parse_oscal_yaml_file`, and `serialize_oscal_yaml` read and write OSCAL in YAML. They accept and produce the same typed `OscalDocument` as the JSON functions.

```python
from oscal_bindings import parse_oscal_yaml, parse_oscal_yaml_file, serialize_oscal_yaml

doc = parse_oscal_yaml(yaml_string)          # str or bytes
doc = parse_oscal_yaml_file("catalog.yaml")  # a missing path raises FileNotFoundError

yaml_string = serialize_oscal_yaml(doc)
```

The input is one YAML 1.2 document in UTF-8. A stream with no document or more than one, a duplicate mapping key, or invalid UTF-8 is an `OscalParseError`, the same error the JSON functions raise. An error that the YAML layer finds has one entry in `errors`, with the same `type`, `loc`, `msg`, and `input` keys as a schema-validation entry. Its `loc` is the JSON path of the failing node, and its `line` and `column` give the position in the YAML text. Its message quotes at most 40 characters of input, and `input` holds the whole text. A scalar at a location that takes no scalar, such as `metadata: 5`, reads as its text, so a schema-validation entry for it has the `input` `"5"` where the JSON path has `5`.

The OSCAL schema, not the YAML reader, decides the type of each scalar at its location. A value keeps its text unless the location is a number or a boolean, so `version: 1.0` at a string location stays the string `"1.0"`, and `yes` stays `"yes"`. A number location takes only the JSON number grammar (no leading `+`, no leading zero, no hexadecimal), and a boolean location takes only `true` or `false`; any other text is a parse error that names the scalar's location. A YAML tag does not change a value, and the key `<<` is an ordinary field, so a merge key is rejected as an unknown field. The characters U+0085, U+2028, and U+2029 are content, as YAML 1.2 defines, not line breaks. A `%YAML 1.1` or `%YAML 1.2` directive is accepted, and both read as YAML 1.2. Any other version is a parse error.

Two cases differ from the JSON path. A double-quoted escape that names a surrogate, such as the pair `"\ud83d\ude00"`, is a parse error, because a YAML escape must name a Unicode character; write `"\U0001F600"` instead. And the serializer drops the seventh fraction digit of a datetime, as `serialize_oscal` does ([#19](https://github.com/cairn-proofs/oscal-bindings-python/issues/19)).

The YAML parser applies three documented limits on alias expansion and nesting depth, so a small file cannot expand into a large value or exhaust the call stack. A fourth limit applies to line-break characters, below. [Resource limits](#resource-limits) lists every limit with the operations it applies to. An input past any of them is an `OscalParseError`:

- Aliases can add at most 100,000 nodes. Each use of an alias adds every scalar, sequence, mapping, and mapping key of the value it expands to.
- Aliases can add at most 1,000,000 characters of scalar text and key text.
- No node can sit deeper than 128 levels of sequences and mappings, counted after alias expansion.

Content that the document writes out, and that no alias repeats, does not count against the two alias limits, so a large document without aliases parses. The SP 800-53 rev5 catalog has about 323,000 nodes and nests 21 levels.

The limits do not bound the size of the input. Memory grows linearly with the input size, at a higher factor than the JSON path. Measured with `tracemalloc` on Python 3.14, the SP 800-53 rev5 catalog peaks at about 11 times its YAML size (6.2 MB), against about 3.4 times its JSON size for `parse_oscal`. A node-dense input costs more on both paths. A flow mapping of 150,000 short keys (1.7 MB) peaks at about 190 MB, most of it in the JSON validation step that both paths share. Cap the size of untrusted YAML input before you parse it.

One more documented limit applies only to input that holds U+0085, U+2028, or U+2029. The parser swaps each of these for an unused private-use character while it reads the text. An input that also holds or names all of the about 137,000 private-use characters, which takes at least 520 KB built for that purpose, leaves none unused and is a parse error.

### Field names vs. OSCAL names

Python code can use field names; OSCAL data must use OSCAL names.

- Constructor keyword arguments accept either: `BackMatterResourceRlink(href=..., media_type=...)` and `BackMatterResourceRlink(href=..., **{"media-type": ...})` build the same model. Plain dicts nested inside the kwargs are OSCAL data and must use OSCAL names.
- Dict input (`Model.model_validate(...)`, `validate_element`) rejects a field name at any depth with `extra_forbidden`.
- JSON input (`parse_oscal`, `parse_oscal_file`, the typed `parse_*` functions, `model_validate_json`) rejects a field name at any depth with `extra_forbidden`, and `validate_oscal` returns `False`.

JSON rejection needs pydantic 2.14.2 or later, which this library requires. Earlier releases of this library allowed pydantic 2.13.x, where JSON input silently dropped a field-name key and its value ([#6](https://github.com/cairn-proofs/oscal-bindings-python/issues/6)).

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

The root key of the input (`catalog`, `profile`, and so on) selects the one document type that the parser validates the input against. So `e.errors` holds only the errors of that document type, and the first `loc` segment of each entry is its class name, for example `('CatalogDocument', 'catalog', 'controls', 0, 'id')`. An input with no known root key gives one entry with the `type` `oscal_document_type` and the `loc` `()`. For a JSON object, its message names the keys of the object:

```text
Not an OSCAL document: no known root key (found: 'assessment_plan')
```

### Resource limits

The parse operations apply six documented limits (PRS-010 of the spec store). An input past any of them is an `OscalParseError`, also when the document is otherwise valid, and `validate_oscal` returns `False` for it. The error carries one entry whose `type` names the limit, and no entry holds the input text.

| Limit | Value | Measure | Operations | Entry `type` |
|---|---|---|---|---|
| JSON depth | 200 levels | The number of arrays and objects that hold a value in the JSON text. Arrays and objects count the same. | `parse_oscal`, `parse_oscal_file`, the eight typed parsers, `OscalDoc.from_json`, `OscalDoc.from_file`, `validate_oscal` | `json_depth_limit` |
| JSON digits | 4,300 digits | The digits of the integer part of one JSON number, at any location. A sign, a fraction, and an exponent do not count. | The operations of the JSON depth limit, and `parse_oscal_yaml` and `parse_oscal_yaml_file` at each number location | `json_digit_limit` |
| Alias nodes | 100,000 nodes | The scalars, sequences, mappings, and mapping keys that aliases add to one YAML input | `parse_oscal_yaml`, `parse_oscal_yaml_file` | `yaml_alias_budget` |
| Alias characters | 1,000,000 characters | The characters of scalar text and key text that aliases add to one YAML input | `parse_oscal_yaml`, `parse_oscal_yaml_file` | `yaml_alias_budget` |
| YAML depth | 128 levels | The number of sequences and mappings that hold a node, after alias expansion | `parse_oscal_yaml`, `parse_oscal_yaml_file` | `yaml_depth_limit` |
| Line-break placeholders | about 137,000 private-use characters | The free private-use characters that a YAML input with U+0085, U+2028, or U+2029 leaves for them | `parse_oscal_yaml`, `parse_oscal_yaml_file` | `yaml_line_break_placeholder` |

pydantic-core's JSON parser sets the two JSON limits, and the binding cannot change them. The YAML depth limit is lower than the JSON depth limit, so deep YAML input always gets the YAML depth error. For a JSON limit, the entry's `line` and `column` give the position in the JSON text, and `column` counts UTF-8 bytes. For a YAML input, they give the position in the YAML source. No limit bounds the input size. See [YAML](#yaml) for the memory that a parse uses.

### Performance

A parse of the NIST SP 800-53 rev5 catalog (10.4 MB) takes about 60 ms of validation work on Python 3.14. It creates about 174,000 objects that Python's cyclic garbage collector tracks. At the default GC threshold, the parse starts about 87 collections. Each collection also scans a part of the objects that the process already holds, so the GC time of a parse increases with the documents that your application keeps:

| Parsed documents that the process holds | Parse time | GC part |
|---|---|---|
| 0 | 85 ms | 28 ms |
| 1 | 113 ms | 58 ms |
| 3 | 195 ms | 139 ms |
| 3, after `gc.freeze()` | 74 ms | 16 ms |
| 1, with `gc.set_threshold(50_000)` | 65 ms | 9 ms |

The library does not change the GC settings, because they apply to the full process and to all of its threads. Your application can change them:

1. After it loads documents that it keeps for a long time, call `gc.freeze()`. The collector then does not scan those objects again.
2. For a batch job that parses many documents, raise the first GC threshold, for example `gc.set_threshold(50_000)`. A higher threshold uses more memory between collections.

`scripts/bench_serialization.py` reports each time with the GC enabled and with the GC disabled.

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

`hatch run generate` and `hatch test` download the pinned spec artifact once into `tests/.corpus_cache/`, so the first run needs network access. The artifact supplies the OSCAL JSON Schema, so this also applies to an sdist checkout. A wheel build from the sdist needs no network access for the schema, because the sdist ships the generated `models.py`.

## Architecture

- **Version package** (`src/oscal_bindings/v1/`) — everything below, scoped to the OSCAL major version. Exposes `__oscal_schema_version__`.
- **Generated models** (`src/oscal_bindings/v1/models.py`) — Pydantic v2 classes with `Annotated` field constraints, produced by `datamodel-code-generator` from the OSCAL JSON Schema.
- **Model base** (`src/oscal_bindings/v1/_base.py`) — hand-written `OscalBaseModel`, which every generated object model inherits via `--base-class`: OSCAL keys and no nulls by default, field-name constructor kwargs.
- **Names** — every type name comes from the naming manifest (`names.json`) of the pinned spec artifact of [oscal-bindings-specs](https://github.com/cairn-proofs/oscal-bindings-specs). `scripts/hoist_names.py` writes a copy of the schema in which each manifest type is a definition with its canonical name, and codegen reads that copy.
- **Post-processing** (`scripts/postprocess_models.py`) — collapses scalar root models, adds the union type aliases, `MappingCollectionMappings`, and `OscalDocument`, and checks every module-level name against the manifest.
- **Schema** — the complete OSCAL JSON Schema comes from the pinned spec artifact (`scripts/spec_artifact.py`, version and sha256). The pin selects the OSCAL release. This repo holds no copy of the schema.
- **Runtime** (`src/oscal_bindings/v1/parser.py`) — parse / serialize / validate utilities and per-type typed parsers.
- **Extensions** (`src/oscal_bindings/v1/extensions/`) — hand-written helpers layered on top of the generated models:
  - `document.py` — `OscalDoc` facade (uniform `metadata` / `uuid` / `oscal_version` / `assessment_period()` accessors).
  - `builders.py` — `make_hash`, `make_rlink`, `make_resource` constructors for `back-matter` elements.
  - `validate_element.py` — element-level schema validation utilities.
- **Top-level package** (`src/oscal_bindings/__init__.py` and the `models` / `parser` / `extensions` alias modules) — pure re-exports of the current version package.

Public symbols are re-exported from `oscal_bindings.v1` and from the top-level `oscal_bindings` package, so callers don't need to know which submodule a name lives in.

## Requirements

- Python 3.11+ (tested on 3.11–3.14)
- Pydantic 2.14.2+ (below 3)

## License

Apache License 2.0; see [LICENSE](LICENSE). The models are generated from the OSCAL JSON Schema of NIST, which is in the public domain; see [NOTICE](NOTICE).
