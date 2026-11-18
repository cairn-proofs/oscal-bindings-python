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

The base install keeps a single runtime dependency (`pydantic`). Every import works without the extra. A call to a YAML operation without the extra raises `ImportError` with an install hint.

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

For Assessment Plans and Assessment Results, `assessment_period()` returns the `(start, end)` bounds as datetimes (`OscalDateTime`, see [Datetimes](#datetimes)), or `None` for a bound that no value gives. The start is the earliest start and the end is the latest end, ordered by instant with every fraction digit, so `2026-03-01T23:00:00-05:00` is later than `2026-03-02T01:00:00Z`. When two values share the earliest (or the latest) instant, the bound is the first of them in document order, and a task comes before its nested tasks. A bound keeps the offset it was written with. It is not converted to UTC:

```python
from oscal_bindings import OscalAccessError

doc = OscalDoc.from_file("assessment-results.json")
start, end = doc.assessment_period()       # (OscalDateTime(2025, 1, 5, ...), OscalDateTime(2025, 1, 30, ...))
start.to_string()                          # "2025-01-05T00:00:00Z", as the document wrote it
start.date()                               # date(2025, 1, 5), if you need a calendar date

try:
    OscalDoc.from_file("catalog.json").assessment_period()
except OscalAccessError as e:
    print(e)                               # only defined for AP / AR
```

Before this version the bounds were `date` values. A `datetime` never equals a `date`, so a caller that compared a bound with a `date` calls `.date()` on the bound first. Compare two bounds with `<`, `==` and `>`: `end - start` is a `timedelta` of microseconds and drops the digits beyond the sixth.

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

# A key gives a stable identifier: the UUID version 5 of the key.
make_resource(key="https://example.org/policies/access-control").uuid
# '51beb3e9-30bb-535f-ba49-e68d4661aaa9'
```

An invalid input raises `OscalBuilderError`, a `ValueError` that is not an `OscalParseError`. Its `errors` attribute
holds the structured entries. An empty `key`, or a `key` with a `uuid`, is invalid.

```python
from oscal_bindings import OscalBuilderError, make_hash

try:
    make_hash(digest, algorithm=" SHA-256")
except OscalBuilderError as e:
    print(e.errors)
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

### Datetimes

Each OSCAL date-time field (`metadata.last_modified`, `result.start`, ...) is an `OscalDateTime`: a `datetime` subclass, so `isinstance(value, datetime)` holds and code that reads it as a `datetime` keeps working. OSCAL allows any number of fraction digits, and Python's `datetime` keeps six, so `OscalDateTime` also keeps the digits of the text and writes them again:

```python
from oscal_bindings import OscalDateTime, parse_oscal

doc = parse_oscal(text)                    # last-modified: "2024-01-02T03:04:05.1234567Z"
last = doc.root.catalog.metadata.last_modified
last.microsecond                           # 123456, as a datetime has it
last.fraction                              # "1234567", every digit of the text
last.to_string()                           # "2024-01-02T03:04:05.1234567Z"
```

Equality, order, and hash count every digit: `.1234567` and `.1234568` are different instants, and `.120` equals `.12`. Arithmetic is where the extra digits can fall away:

- `value + timedelta` and `value - timedelta` keep them, and so do `replace` and `astimezone`.
- `value - other` is a `timedelta`, which holds microseconds, so two values that differ only after the sixth digit have a difference of zero. Compare them with `==`, `<`, and `>`.
- `timestamp()`, `strftime()`, and `isoformat(timespec=...)` use the microsecond value only.

The class docstring lists each method, and the API documentation shows it.

### YAML

With the `yaml` extra installed, `parse_oscal_yaml`, `parse_oscal_yaml_file`, and `serialize_oscal_yaml` read and write OSCAL in YAML. They accept and produce the same typed `OscalDocument` as the JSON functions.

```python
from oscal_bindings import parse_oscal_yaml, parse_oscal_yaml_file, serialize_oscal_yaml

doc = parse_oscal_yaml(yaml_string)          # str or bytes
doc = parse_oscal_yaml_file("catalog.yaml")  # a missing path raises FileNotFoundError

yaml_string = serialize_oscal_yaml(doc)
```

Each document type also has a typed YAML parser, as the JSON functions do: `parse_catalog_yaml`, `parse_profile_yaml`, `parse_component_definition_yaml`, `parse_system_security_plan_yaml`, `parse_assessment_plan_yaml`, `parse_assessment_results_yaml`, `parse_plan_of_action_and_milestones_yaml`, and `parse_mapping_collection_yaml`. Each parses as `parse_oscal_yaml` does and returns the wrapper (`CatalogDocument`, ...), or raises `OscalDocumentTypeMismatchError` for a document of another type. They need the `yaml` extra too.

```python
from oscal_bindings import parse_catalog_yaml

catalog = parse_catalog_yaml(yaml_string)  # CatalogDocument
```

The input is one YAML 1.2 document in UTF-8. A stream with no document or more than one, a duplicate mapping key, or invalid UTF-8 is an `OscalParseError`, the same error the JSON functions raise. An error that the YAML layer finds has an entry in `errors` (one for each scalar that fits no grammar, and one for any other failure), with the same `type`, `loc`, `msg`, and `input` keys as a schema-validation entry. Its `loc` is the JSON path of the failing node from the root key, such as `('component-definition', 'components', 0, ...)`, without the class-name segment that a schema-validation entry starts with. Its `line` and `column` give the position in the YAML text. Its message quotes at most 40 characters of input, and `input` holds the whole text. A scalar at a location that takes no scalar, such as `metadata: 5`, reads as its text, so a schema-validation entry for it has the `input` `"5"` where the JSON path has `5`.

The OSCAL schema, not the YAML reader, decides the type of each scalar at its location. A value keeps its text unless the location is a number or a boolean, so `version: 1.0` at a string location stays the string `"1.0"`, and `yes` stays `"yes"`. A number location takes only the JSON number grammar (no leading `+`, no leading zero, no hexadecimal), and a boolean location takes only `true` or `false`; any other text is a parse error that names the scalar's location. The error holds one entry for each such scalar, and the entries of the schema check for the rest of the document, so one parse shows every failure. A YAML tag does not change a value, and the key `<<` is an ordinary field, so a merge key is rejected as an unknown field. The characters U+0085, U+2028, and U+2029 are content, as YAML 1.2 defines, not line breaks. A `%YAML 1.1` or `%YAML 1.2` directive is accepted, and both read as YAML 1.2. Any other version is a parse error.

One case differs from the JSON path. A double-quoted escape that names a surrogate, such as the pair `"\ud83d\ude00"`, is a parse error, because a YAML escape must name a Unicode character; write `"\U0001F600"` instead.

The YAML parser applies three documented limits on alias expansion and nesting depth, so a small file cannot expand into a large value or exhaust the call stack. A fourth limit applies to line-break characters, below. [Resource limits](#resource-limits) lists every limit with the operations it applies to. An input past any of them is an `OscalParseError`:

- Aliases can add at most 100,000 nodes. Each use of an alias adds every scalar, sequence, mapping, and mapping key of the value it expands to.
- Aliases can add at most 1,000,000 characters of scalar text and key text.
- No node can sit deeper than 128 levels of sequences and mappings, counted after alias expansion.

Content that the document writes out, and that no alias repeats, does not count against the two alias limits, so a large document without aliases parses. The SP 800-53 rev5 catalog has about 323,000 nodes and nests 21 levels.

The limits do not bound the size of the input. Memory grows linearly with the input size, at a higher factor than the JSON path, and a node-dense input costs more on both paths. Cap the size of untrusted YAML input before you parse it. [PERFORMANCE.md](https://github.com/cairn-proofs/oscal-bindings-python/blob/main/PERFORMANCE.md#memory) has the measured memory.

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

The root key of the input (`catalog`, `profile`, and so on) selects the one document type that the parser validates the input against. So `e.errors` holds only the errors of that document type, and the first `loc` segment of each schema entry is its class name, for example `('CatalogDocument', 'catalog', 'controls', 0, 'id')`. A YAML parse that finds scalars matching no grammar returns those entries first, with a `loc` that has no class-name segment, followed by the schema entries (see [YAML](#yaml)). An input with no known root key gives one entry with the `type` `oscal_document_type` and the `loc` `()`. For a JSON object, its message names the keys of the object:

```text
Not an OSCAL document: no known root key (found: 'assessment_plan')
```

The `input` of an entry is the failing value when that value is a string, a number, a boolean, or a null. When the failing value is an object or an array, `input` is the sentinel `OscalParseError.OMITTED_INPUT` (shown as `<omitted input>`), so the error holds no copy of the document. Use `loc` to find the value in your own input. The sentinel stays the same object through `copy` and `pickle`. To write the entries as JSON, pass `default=repr`:

```python
if entry["input"] is OscalParseError.OMITTED_INPUT:
    ...
json.dumps(e.errors, default=repr)
```

An entry for a [resource limit](#resource-limits) has `input` `None`.

### Resource limits

The parse operations apply six documented limits (PRS-010 of the spec store). An input past any of them is an `OscalParseError`, also when the document is otherwise valid, and `validate_oscal` returns `False` for it. The error carries one entry whose `type` names the limit, and no entry holds the input text. The error also has the attribute `limit`, the identifier in the last column of the table. The two alias limits share an entry `type`, and `limit` tells them apart. For each other parse error, `limit` is `None`. Test an `OscalParseError` with `error.limit is not None`, and an error of any class with `getattr(error, "limit", None) is not None`.

| Limit | Value | Measure | Operations | Entry `type` | `limit` |
|---|---|---|---|---|---|
| JSON depth | 200 levels | The number of arrays and objects that hold a value in the JSON text. Arrays and objects count the same. | `parse_oscal`, `parse_oscal_file`, the eight typed parsers, `OscalDoc.from_json`, `OscalDoc.from_file`, `validate_oscal` | `json_depth_limit` | `json_depth` |
| JSON digits | 4,300 digits | The digits of the integer part of one JSON number, at any location. A sign, a fraction, and an exponent do not count. | The operations of the JSON depth limit, and `parse_oscal_yaml`, `parse_oscal_yaml_file`, and the eight typed YAML parsers at each number location | `json_digit_limit` | `json_digits` |
| Alias nodes | 100,000 nodes | The scalars, sequences, mappings, and mapping keys that aliases add to one YAML input | `parse_oscal_yaml`, `parse_oscal_yaml_file`, the eight typed YAML parsers | `yaml_alias_budget` | `yaml_alias_nodes` |
| Alias characters | 1,000,000 characters | The characters of scalar text and key text that aliases add to one YAML input | `parse_oscal_yaml`, `parse_oscal_yaml_file`, the eight typed YAML parsers | `yaml_alias_budget` | `yaml_alias_characters` |
| YAML depth | 128 levels | The number of sequences and mappings that hold a node, after alias expansion | `parse_oscal_yaml`, `parse_oscal_yaml_file`, the eight typed YAML parsers | `yaml_depth_limit` | `yaml_depth` |
| Line-break placeholders | about 137,000 private-use characters | The free private-use characters that a YAML input with U+0085, U+2028, or U+2029 leaves for them | `parse_oscal_yaml`, `parse_oscal_yaml_file`, the eight typed YAML parsers | `yaml_line_break_placeholder` | `yaml_line_break_placeholders` |

pydantic-core's JSON parser sets the two JSON limits, and the binding cannot change them. The YAML depth limit is lower than the JSON depth limit, so deep YAML input always gets the YAML depth error. For a JSON limit, the entry's `line` and `column` give the position in the JSON text, and `column` counts UTF-8 bytes. For a YAML input, they give the position in the YAML source. No limit bounds the input size. See [Performance](#performance) for the memory that a parse uses.

### Performance

The performance numbers (parse time, garbage collection, memory, YAML cost, serialization) are in [PERFORMANCE.md](https://github.com/cairn-proofs/oscal-bindings-python/blob/main/PERFORMANCE.md).

A parse creates many objects that Python's cyclic garbage collector tracks, and each collection also scans the objects that the process already holds. So the GC time of a parse increases with the documents that your application keeps. The library does not change the GC settings, because they apply to the full process and to all of its threads. Your application can change them:

1. After it loads documents that it keeps for a long time, call `gc.freeze()`. The collector then does not scan those objects again.
2. For a batch job that parses many documents, raise the first GC threshold, for example `gc.set_threshold(50_000)`. A higher threshold uses more memory between collections.

`scripts/bench_serialization.py` and `scripts/bench_memory.py` measure time and memory. [PERFORMANCE.md](https://github.com/cairn-proofs/oscal-bindings-python/blob/main/PERFORMANCE.md#how-to-measure) says how to run them.

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

A typed parser (JSON or YAML) raises `OscalDocumentTypeMismatchError` for a document of another type. It is a subclass of `OscalParseError`, so `except OscalParseError` also catches it. `validate_element` raises `OscalUnknownElementTypeError` for an element type that the library does not recognize. That error is a category of its own, outside the parse errors. A file-path parse raises `FileNotFoundError` when no file can exist at the path, and `OscalReadError` for each other read failure (a directory, a permission failure, a loop of symbolic links). `OscalReadError` is a subclass of `OSError`, not of `OscalParseError` or of `FileNotFoundError`, so `except OSError` catches both file categories and `except OscalParseError` catches neither. Test the category of an error with `isinstance`.

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

- Python 3.11+ (tested on 3.11–3.15)
- Pydantic 2.14.2+ (below 3)

## License

Apache License 2.0; see [LICENSE](LICENSE). The models are generated from the OSCAL JSON Schema of NIST, which is in the public domain; see [NOTICE](NOTICE).
