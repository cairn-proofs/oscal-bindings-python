# Errors

## Parse errors

```python
from oscal_bindings import parse_oscal, OscalParseError

try:
    parse_oscal(invalid_json)
except OscalParseError as e:
    print(e)          # Human-readable message
    print(e.errors)   # Pydantic validation error details
```

The root key of the input (`catalog`, `profile`, and so on) selects the one document type that the parser validates the input against. So `e.errors` holds only the errors of that document type, and the first `loc` segment of each schema entry is its class name, for example `('CatalogDocument', 'catalog', 'controls', 0, 'id')`. A YAML parse that finds scalars matching no grammar returns those entries first, with a `loc` that has no class-name segment, followed by the schema entries (see [YAML](yaml.md)). An input with no known root key gives one entry with the `type` `oscal_document_type` and the `loc` `()`. For a JSON object, its message names the keys of the object:

```text
Not an OSCAL document: no known root key (found: 'assessment_plan')
```

The `input` of an entry is the failing value when that value is a string, a number, a boolean, or a null. When the failing value is an object or an array, `input` is the sentinel `OscalParseError.OMITTED_INPUT` (shown as `<omitted input>`), so the error holds no copy of the document. Use `loc` to find the value in your own input. The sentinel stays the same object through `copy` and `pickle`. To write the entries as JSON, pass `default=repr`:

```python
if entry["input"] is OscalParseError.OMITTED_INPUT:
    ...
json.dumps(e.errors, default=repr)
```

An entry for a [resource limit](limits.md) has `input` `None`.

## Error categories

A typed parser (JSON or YAML) raises `OscalDocumentTypeMismatchError` for a document of another type. It is a subclass of `OscalParseError`, so `except OscalParseError` also catches it. `validate_element` raises `OscalUnknownElementTypeError` for an element type that the library does not recognize. That error is a category of its own, outside the parse errors. A file-path parse raises `FileNotFoundError` when no file can exist at the path, and `OscalReadError` for each other read failure (a directory, a permission failure, a loop of symbolic links). `OscalReadError` is a subclass of `OSError`, not of `OscalParseError` or of `FileNotFoundError`, so `except OSError` catches both file categories and `except OscalParseError` catches neither. Test the category of an error with `isinstance`.
