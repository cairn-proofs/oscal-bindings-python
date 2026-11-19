# Parsing and reading documents

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

## Typed parser functions

Each OSCAL document type has a dedicated parser:

- `parse_catalog(json)` → `CatalogDocument`
- `parse_profile(json)` → `ProfileDocument`
- `parse_component_definition(json)` → `ComponentDefinitionDocument`
- `parse_system_security_plan(json)` → `SystemSecurityPlanDocument`
- `parse_assessment_plan(json)` → `AssessmentPlanDocument`
- `parse_assessment_results(json)` → `AssessmentResultsDocument`
- `parse_plan_of_action_and_milestones(json)` → `PlanOfActionAndMilestonesDocument`
- `parse_mapping_collection(json)` → `MappingCollectionDocument`

A typed parser raises `OscalDocumentTypeMismatchError` for a document of another type; see [Errors](errors.md).

## Accessing parsed data

```python
catalog = parse_catalog(json_string)
print(catalog.catalog.metadata.title)       # plain str
print(catalog.catalog.metadata.version)
```

## The `OscalDoc` facade

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

For Assessment Plans and Assessment Results, `assessment_period()` returns the `(start, end)` bounds as datetimes (`OscalDateTime`, see [Datetimes](datetimes.md)), or `None` for a bound that no value gives. The start is the earliest start and the end is the latest end, ordered by instant with every fraction digit, so `2026-03-01T23:00:00-05:00` is later than `2026-03-02T01:00:00Z`. When two values share the earliest (or the latest) instant, the bound is the first of them in document order, and a task comes before its nested tasks. A bound keeps the offset it was written with. It is not converted to UTC:

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

## Validation

```python
from oscal_bindings import validate_oscal

if validate_oscal(json_string):
    print("Valid OSCAL document")
```
