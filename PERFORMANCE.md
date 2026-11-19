# Performance of oscal-bindings (Python)

This file holds every performance number of the project: parse time, garbage collection, memory, YAML cost, and serialization time. The README, the `docs/` pages, `DEVELOPING.md`, and `AGENTS.md` point here and state no number of their own. A pull request that changes a number here updates this file in the same change.

Absolute times depend on the machine, so compare ratios. Each section names its Python version. The document is the NIST SP 800-53 rev5 catalog (10.4 MB of JSON, 7.3 MB of YAML) unless a section says otherwise.

## Contents

- [Parse time and garbage collection](#parse-time-and-garbage-collection)
- [Memory](#memory)
- [YAML cost](#yaml-cost)
- [Serialization](#serialization)
- [Datatype checks](#datatype-checks)
- [Error path: selected union branch](#error-path-selected-union-branch)
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
| Catalog, `parse_oscal` | 10.4 MB | 35 MB | about 3.4x |
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

`hatch run python scripts/bench_serialization.py`, median of 7 per run; "after" is the median of 3 runs, which varied by up to about 30% on the compact row. Python 3.12.14, pydantic 2.13.5, pydantic-core 2.46.5. These numbers come from the change that made every serialization path emit valid OSCAL (issue #5). The serialize-time regression is accepted as the price of valid OSCAL on every path; parse is unchanged. Before, `model_dump_json()` and `to_json` emitted invalid OSCAL (Python names, `null`s), so those rows are not like-for-like. The per-field `exclude_if` change below (issue #8) removed most of this regression.

| Path | Before ms | After ms | Ratio | Output after |
|------|----------:|---------:|------:|-------------:|
| `parse_oscal(bytes)` | 288.9 | 292.7 | 1.01x | - |
| `serialize_oscal(doc, indent=None)` | 27.3 | 125.6 | 4.6x | 4.88 MB (same) |
| `serialize_oscal(doc)` | 63.1 | 168.4 | 2.7x | 10.44 MB (same) |
| `doc.model_dump_json()` | 66.1 (invalid) | 165.8 | 2.5x | 4.88 MB (was 7.57 MB) |
| `pydantic_core.to_json(doc)` | 63.7 (invalid) | 170.6 | 2.7x | 4.88 MB (was 7.53 MB) |

### Per-field `exclude_if` (issue #8)

`omit_none` as `Field(exclude_if=...)` on each of the 982 fields of the object models (698 optional, 284 required) replaced the wrap `model_serializer` of `OscalBaseModel`, so pydantic-core drops a `None` and no Python callback runs per model node. A required field has it too, so a `None` that a caller sets by `model_construct` or by assignment is dropped as before. Output is byte-identical, and `model_json_schema` is unchanged in both modes: `OscalBaseModel.__get_pydantic_json_schema__` lists the required fields again in the serialization schema, which pydantic otherwise drops for a field with `exclude_if`. The hook runs when a schema is built, not when a value is serialized.

`hatch run python scripts/bench_serialization.py` on the NIST SP 800-53 rev5 catalog (10.4 MB of JSON), median of 7 per run, then the median of 3 runs. The runs of `main` and the branch alternate on one machine. Python 3.13.18, pydantic 2.14.3, pydantic-core 2.50.4.

| Path | Before, GC on ms | After, GC on ms | Before, GC off ms | After, GC off ms | Ratio, GC on |
|---|---:|---:|---:|---:|---:|
| `parse_oscal(bytes)` | 190.0 | 183.7 | 129.3 | 132.4 | 0.97x (noise) |
| `serialize_oscal(doc, indent=None)` | 311.6 | 72.5 | 292.8 | 63.5 | 0.23x |
| `serialize_oscal(doc)` | 341.1 | 100.4 | 329.2 | 95.6 | 0.29x |
| `doc.model_dump_json()` | 327.2 | 77.3 | 314.4 | 69.3 | 0.24x |
| `pydantic_core.to_json(doc)` | 332.6 | 72.3 | 314.6 | 68.0 | 0.22x |

Compact serialization is about 4.3x faster with the GC on and 4.6x with it off. Parse is not touched by the change; its row differs by run-to-run noise. Covering the 284 required fields costs about 5% against a version that covered the 698 optional fields only. The absolute times are higher than in the tables above because this machine and Python are different, so compare the ratios.

### Datetime fraction digits (issue #19)

The date-time fields are `OscalDateTime`, a `datetime` subclass that keeps every fraction digit of the text. A parse of a datetime now calls a Python wrap validator, and a JSON serialization of one calls a Python function. The NIST SP 800-53 rev5 catalog has 8 datetime fields, so the test is whether a parse and a serialization of a real document move.

`hatch run python scripts/bench_serialization.py` on that catalog (10.4 MB of JSON), median of 7 per run, then the median of 3 runs. The runs of `main` (with the `exclude_if` change above) and the branch alternate on one machine. Python 3.13.18, pydantic 2.14.3, pydantic-core 2.50.4.

| Path | Before, GC on ms | After, GC on ms | Before, GC off ms | After, GC off ms |
|---|---:|---:|---:|---:|
| `parse_oscal(bytes)` | 184.1 | 183.3 | 131.2 | 131.7 |
| `serialize_oscal(doc, indent=None)` | 69.5 | 70.0 | 59.2 | 59.9 |
| `serialize_oscal(doc)` | 104.3 | 101.8 | 91.6 | 96.8 |
| `doc.model_dump_json()` | 72.5 | 74.3 | 64.3 | 64.7 |
| `pydantic_core.to_json(doc)` | 76.9 | 74.8 | 62.5 | 63.7 |

No row moves beyond the run-to-run noise of this machine: the largest difference is 6%, in `serialize_oscal(doc)` with the GC off, and the runs of one tree differ by as much. The compact output is 54 bytes longer, because the type writes a datetime as the text wrote it: the catalog writes eight of them with a zero fraction (`.000000`) that the old type dropped. A document with many datetimes pays one Python call for each; the cost for such a document is not measured here.

## Datatype checks

The change that enforces the OSCAL datatype constraints (#77) replaced `AnyUrl`, `EmailStr`, and the unchecked `AwareDatetime` and `str` fields with four hand-written types (`v1/_datatypes.py`). Each value of those types now passes one to three `pattern` steps in pydantic-core (the Rust `regex` engine), and a `datetime` that a caller gives in Python input passes one Python call. The target was no measurable slowdown of a parse of the catalog.

`hatch run python scripts/bench_serialization.py`, median of 7 per run, then the median of 3 runs. The runs of the tree before and after the change alternate on one machine. Python 3.14.8, pydantic 2.14.2, pydantic-core 2.50.2. The catalog has 10.4 MB of JSON.

| Path | Before, GC on ms | After, GC on ms | Before, GC off ms | After, GC off ms |
|---|---:|---:|---:|---:|
| `parse_oscal(bytes)` | 64.0 | 61.1 | 47.2 | 45.6 |
| `serialize_oscal(doc, indent=None)` | 135.6 | 132.7 | 128.8 | 125.7 |
| `serialize_oscal(doc)` | 144.0 | 140.4 | 137.6 | 134.1 |
| `doc.model_dump_json()` | 142.0 | 138.8 | 135.3 | 132.4 |
| `pydantic_core.to_json(doc)` | 143.0 | 138.6 | 136.0 | 132.7 |

The after column is 2 to 5% lower in each row, also in the serialization rows that the change does not touch, so read it as no slowdown, not as a speedup. The validation of the four datatypes costs less than the difference between the runs.

`import oscal_bindings` takes 159.5 ms before and 150.0 ms after (median of 9 fresh processes, `python -X importtime`). The runtime no longer imports `email-validator`.

`scripts/bench_memory.py`: the peak of `parse_oscal` for the catalog is 36.5 MB before and 35.3 MB after. The other three rows of [Memory](#memory) are the same.

## Error path: selected union branch

Python 3.13. A failing parse of a union object keeps only the entries of the selected branch (PRS-014). To find the branch, the error path runs `json.loads` on the input again. A parse that succeeds does not run it. Measured on the NIST SP 800-53 rev4 catalog (about 5 MB as indented JSON) with one added parameter whose `select` has `how-many` set to `seven`. Median of 9 parses, two runs each, with a small script around `parse_oscal`:

| | Before | After |
|---|---|---|
| Parse time, GC enabled | 0.099 s (both runs) | 0.108 s and 0.126 s |
| Parse time, GC disabled | 0.066 s and 0.070 s | 0.082 s and 0.085 s |
| Error entries | 2 | 1 |
| `tracemalloc` peak | 17.3 MB | 17.3 MB |

The failing parse takes about 10% to 25% longer, and the peak does not change.

## Design changes with a measured effect

| Change | Effect | Measured on |
|---|---|---|
| Union fields validate `left_to_right` (#43) | About 18% faster parse of the catalog, because validation stops at the first variant that validates, which is the variant that smart mode picks. | The catalog |
| An error entry keeps no copy of an object or array input (#42) | Peak of the 150,000-key invalid mapping: 297 MB to 144 MB. Held after the raise, for a catalog without `metadata`: 25.7 MB to 1.6 KB. | See [Memory](#memory) |

## How to measure

- `hatch run python scripts/bench_serialization.py` reports parse and serialize time, with the GC enabled and disabled.
- `hatch run python scripts/bench_memory.py` reports the peak memory of the rows in [Memory](#memory). Both scripts read the catalog from `tests/.corpus_cache/`, which the first run of `hatch test` fills. Pass `--catalog` or `--catalog-dir` to use another copy.
- Timing is not a CI test: four Pythons under xdist make it flaky. A pull request reports before and after numbers instead, with the GC enabled and disabled, and a change that claims a speedup states its numeric target first.
