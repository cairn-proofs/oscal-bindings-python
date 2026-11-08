# Performance of oscal-bindings (Python)

This file holds every performance number of the project: parse time, garbage collection, memory, YAML cost, and serialization time. The README, `DEVELOPING.md`, and `AGENTS.md` point here and state no number of their own. A pull request that changes a number here updates this file in the same change.

Absolute times depend on the machine, so compare ratios. Each section names its Python version. The document is the NIST SP 800-53 rev5 catalog (10.4 MB of JSON, 7.3 MB of YAML) unless a section says otherwise.

## Contents

- [Parse time and garbage collection](#parse-time-and-garbage-collection)
- [Memory](#memory)
- [YAML cost](#yaml-cost)
- [Serialization](#serialization)
- [Design changes with a measured effect](#design-changes-with-a-measured-effect)
- [How to measure](#how-to-measure)

## Parse time and garbage collection

Python 3.14. A parse of the catalog takes about 60 ms of validation work. It creates about 174,000 objects that Python's cyclic garbage collector tracks. At the default GC threshold, the parse starts about 87 collections. Each collection also scans a part of the objects that the process already holds, so the GC time of a parse increases with the documents that your application keeps:

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

## Memory

Peak traced memory of one parse, measured with `tracemalloc` on Python 3.14 (`scripts/bench_memory.py`). The factor is the peak divided by the input size.

| Input | Input size | Peak | Factor |
|---|---|---|---|
| Catalog, `parse_oscal` | 10.4 MB | 36 MB | about 3.4x |
| Catalog, `parse_oscal_yaml` | 7.3 MB | 83 MB | about 11x |
| Flow mapping of 150,000 unknown short keys, `parse_oscal` | 2.0 MB | 144 MB | about 72x |
| Flow mapping of 150,000 unknown short keys, `parse_oscal_yaml` | 1.7 MB | 148 MB | about 87x |

The limits on alias expansion and nesting depth do not bound the size of the input. Memory grows linearly with the input size, at a higher factor for YAML than for JSON. A node-dense input costs more on both paths:

- A flow sequence of one-character scalars peaks at about 43 times its size. A test keeps that factor below 60. Scalar nodes share one empty `items` list and the walk joins its output in chunks, which cut the factor of the catalog from 16 to 11, and this factor from 81 to 43.
- The flow mapping above is invalid input: every unknown key is one entry of the parse error. Most of its peak is the JSON validation step that both paths share. Since #42 (#46), an error entry whose failing value is an object or an array keeps no copy of that value. The JSON-path peak of this input was 297 MB before that change (about 149 times the input size), and 144 MB after it.
- A catalog without `metadata` left 25.7 MB held after the `OscalParseError` was raised, before #42. The error now holds 1.6 KB.
- An input just under either alias limit peaks below 15 MB, and a test keeps the peak below 100 MB. A design that counted all emitted nodes against 5,000,000, which was rejected, let a 3.5 KB alias bomb reach 334 MB before the parser rejected it.

Cap the size of untrusted input before you parse it.

## YAML cost

For the catalog (7.3 MB of YAML), `parse_oscal_yaml` takes 0.8 s with libyaml (`CSafeLoader`) and 3.4 s with the pure-Python parser, against 0.2 s for `parse_oscal` on the 10.4 MB JSON. These times come from the release of the YAML feature (#32). The parser uses libyaml whenever PyYAML has it. The serializer picks `CSafeDumper` or `SafeDumper` the same way.

## Serialization

`hatch run python scripts/bench_serialization.py`, median of 7 per run; "after" is the median of 3 runs, which varied by up to about 30% on the compact row. Python 3.12.14, pydantic 2.13.5, pydantic-core 2.46.5. These numbers come from the change that made every serialization path emit valid OSCAL (issue #5). The serialize-time regression is accepted as the price of valid OSCAL on every path; parse is unchanged. Before, `model_dump_json()` and `to_json` emitted invalid OSCAL (Python names, `null`s), so those rows are not like-for-like. If serialize time becomes a problem, the fallback is per-field `exclude_if` (about 1.35x in the prototype, needs pydantic 2.12 or later).

| Path | Before ms | After ms | Ratio | Output after |
|------|----------:|---------:|------:|-------------:|
| `parse_oscal(bytes)` | 288.9 | 292.7 | 1.01x | - |
| `serialize_oscal(doc, indent=None)` | 27.3 | 125.6 | 4.6x | 4.88 MB (same) |
| `serialize_oscal(doc)` | 63.1 | 168.4 | 2.7x | 10.44 MB (same) |
| `doc.model_dump_json()` | 66.1 (invalid) | 165.8 | 2.5x | 4.88 MB (was 7.57 MB) |
| `pydantic_core.to_json(doc)` | 63.7 (invalid) | 170.6 | 2.7x | 4.88 MB (was 7.53 MB) |

## Design changes with a measured effect

| Change | Effect | Measured on |
|---|---|---|
| Union fields validate `left_to_right` (#43) | About 18% faster parse of the catalog, because validation stops at the first variant that validates, which is the variant that smart mode picks. | The catalog |
| An error entry keeps no copy of an object or array input (#42) | Peak of the 150,000-key invalid mapping: 297 MB to 144 MB. Held after the raise, for a catalog without `metadata`: 25.7 MB to 1.6 KB. | See [Memory](#memory) |

## How to measure

- `hatch run python scripts/bench_serialization.py` reports parse and serialize time, with the GC enabled and disabled.
- `hatch run python scripts/bench_memory.py` reports the peak memory of the rows in [Memory](#memory). Both scripts read the catalog from `tests/.corpus_cache/`, which the first run of `hatch test` fills. Pass `--catalog` or `--catalog-dir` to use another copy.
- Timing is not a CI test: four Pythons under xdist make it flaky. A pull request reports before and after numbers instead, with the GC enabled and disabled, and a change that claims a speedup states its numeric target first.
