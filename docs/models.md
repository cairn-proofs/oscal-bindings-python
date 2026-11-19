# Building and serializing models

## Building back-matter resources

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

## Field names vs. OSCAL names

Python code can use field names; OSCAL data must use OSCAL names.

- Constructor keyword arguments accept either: `BackMatterResourceRlink(href=..., media_type=...)` and `BackMatterResourceRlink(href=..., **{"media-type": ...})` build the same model. Plain dicts nested inside the kwargs are OSCAL data and must use OSCAL names.
- Dict input (`Model.model_validate(...)`, `validate_element`) rejects a field name at any depth with `extra_forbidden`.
- JSON input (`parse_oscal`, `parse_oscal_file`, the typed `parse_*` functions, `model_validate_json`) rejects a field name at any depth with `extra_forbidden`, and `validate_oscal` returns `False`.

JSON rejection needs pydantic 2.14.2 or later, which this library requires. Earlier releases of this library allowed pydantic 2.13.x, where JSON input silently dropped a field-name key and its value ([#6](https://github.com/cairn-proofs/oscal-bindings-python/issues/6)).

## Serialization

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
