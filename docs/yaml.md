# YAML

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

The YAML parser applies three documented limits on alias expansion and nesting depth, so a small file cannot expand into a large value or exhaust the call stack. A fourth limit applies to line-break characters, below. [Resource limits](limits.md) lists every limit with the operations it applies to. An input past any of them is an `OscalParseError`:

- Aliases can add at most 100,000 nodes. Each use of an alias adds every scalar, sequence, mapping, and mapping key of the value it expands to.
- Aliases can add at most 1,000,000 characters of scalar text and key text.
- No node can sit deeper than 128 levels of sequences and mappings, counted after alias expansion.

Content that the document writes out, and that no alias repeats, does not count against the two alias limits, so a large document without aliases parses. The SP 800-53 rev5 catalog has about 323,000 nodes and nests 21 levels.

The limits do not bound the size of the input. Memory grows linearly with the input size, at a higher factor than the JSON path, and a node-dense input costs more on both paths. Cap the size of untrusted YAML input before you parse it. [PERFORMANCE.md](../PERFORMANCE.md#memory) has the measured memory.

One more documented limit applies only to input that holds U+0085, U+2028, or U+2029. The parser swaps each of these for an unused private-use character while it reads the text. An input that also holds or names all of the about 137,000 private-use characters, which takes at least 520 KB built for that purpose, leaves none unused and is a parse error.
