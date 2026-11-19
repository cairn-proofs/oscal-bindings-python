# Resource limits

The parse operations apply six documented limits (PRS-010 of the spec store). An input past any of them is an `OscalParseError`, also when the document is otherwise valid, and `validate_oscal` returns `False` for it. The error carries one entry whose `type` names the limit, and no entry holds the input text. The error also has the attribute `limit`, the identifier in the last column of the table. The two alias limits share an entry `type`, and `limit` tells them apart. For each other parse error, `limit` is `None`. Test an `OscalParseError` with `error.limit is not None`, and an error of any class with `getattr(error, "limit", None) is not None`.

| Limit | Value | Measure | Operations | Entry `type` | `limit` |
|---|---|---|---|---|---|
| JSON depth | 200 levels | The number of arrays and objects that hold a value in the JSON text. Arrays and objects count the same. | `parse_oscal`, `parse_oscal_file`, the eight typed parsers, `OscalDoc.from_json`, `OscalDoc.from_file`, `validate_oscal` | `json_depth_limit` | `json_depth` |
| JSON digits | 4,300 digits | The digits of the integer part of one JSON number, at any location. A sign, a fraction, and an exponent do not count. | The operations of the JSON depth limit, and `parse_oscal_yaml`, `parse_oscal_yaml_file`, and the eight typed YAML parsers at each number location | `json_digit_limit` | `json_digits` |
| Alias nodes | 100,000 nodes | The scalars, sequences, mappings, and mapping keys that aliases add to one YAML input | `parse_oscal_yaml`, `parse_oscal_yaml_file`, the eight typed YAML parsers | `yaml_alias_budget` | `yaml_alias_nodes` |
| Alias characters | 1,000,000 characters | The characters of scalar text and key text that aliases add to one YAML input | `parse_oscal_yaml`, `parse_oscal_yaml_file`, the eight typed YAML parsers | `yaml_alias_budget` | `yaml_alias_characters` |
| YAML depth | 128 levels | The number of sequences and mappings that hold a node, after alias expansion | `parse_oscal_yaml`, `parse_oscal_yaml_file`, the eight typed YAML parsers | `yaml_depth_limit` | `yaml_depth` |
| Line-break placeholders | about 137,000 private-use characters | The free private-use characters that a YAML input with U+0085, U+2028, or U+2029 leaves for them | `parse_oscal_yaml`, `parse_oscal_yaml_file`, the eight typed YAML parsers | `yaml_line_break_placeholder` | `yaml_line_break_placeholders` |

pydantic-core's JSON parser sets the two JSON limits, and the binding cannot change them. The YAML depth limit is lower than the JSON depth limit, so deep YAML input always gets the YAML depth error. For a JSON limit, the entry's `line` and `column` give the position in the JSON text, and `column` counts UTF-8 bytes. For a YAML input, they give the position in the YAML source. No limit bounds the input size. See [Performance](limits.md#performance) for the memory that a parse uses.

## Performance

The performance numbers (parse time, garbage collection, memory, YAML cost, serialization) are in [PERFORMANCE.md](../PERFORMANCE.md).

A parse creates many objects that Python's cyclic garbage collector tracks, and each collection also scans the objects that the process already holds. So the GC time of a parse increases with the documents that your application keeps. The library does not change the GC settings, because they apply to the full process and to all of its threads. Your application can change them:

1. After it loads documents that it keeps for a long time, call `gc.freeze()`. The collector then does not scan those objects again.
2. For a batch job that parses many documents, raise the first GC threshold, for example `gc.set_threshold(50_000)`. A higher threshold uses more memory between collections.

`scripts/bench_serialization.py` and `scripts/bench_memory.py` measure time and memory. [PERFORMANCE.md](../PERFORMANCE.md#how-to-measure) says how to run them.
