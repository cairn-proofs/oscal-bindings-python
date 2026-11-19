# oscal-bindings documentation

The [README](../README.md) has the quick start. These pages hold the details.

| Page | Covers |
|---|---|
| [Installation and versions](installation.md) | Install options, the `yaml` extra, the `v1` import path, which OSCAL release the models come from |
| [Parsing and reading documents](parsing.md) | `parse_oscal` and the typed parsers, `str` / `bytes` / file input, the `OscalDoc` facade, `validate_oscal` |
| [Building and serializing models](models.md) | Back-matter builders, field names vs. OSCAL names, serialization defaults |
| [Datetimes](datetimes.md) | `OscalDateTime` and fraction digits |
| [YAML](yaml.md) | The YAML functions, scalar typing, YAML limits |
| [Errors](errors.md) | `OscalParseError` entries and the error categories |
| [Resource limits](limits.md) | Every parse limit, and garbage-collection tuning |

The API reference is the docstrings: `hatch run docs` builds it into `build/api-docs`. Performance numbers are in [PERFORMANCE.md](../PERFORMANCE.md). To work on the library, see [DEVELOPING.md](../DEVELOPING.md).
