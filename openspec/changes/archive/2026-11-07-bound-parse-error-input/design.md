# Design

## Context

See [proposal.md - Why](proposal.md#why) for the motivation. These facts constrain the approach.

1. `parse_oscal` builds `OscalParseError.errors` from `ValidationError.errors()`. Each entry has `type`, `loc`, `msg`,
   `input`, `url`, and sometimes `ctx`. The `input` is the failing value as a Python object. For a `missing` field it
   is the parent object, and for `extra_forbidden` it is the value of the unknown key.
2. `parse_oscal` raises the schema `OscalParseError` inside the `except` block, `from e`. A limit entry is raised
   outside the block, so that neither `__cause__` nor `__context__` holds the `ValidationError`
   (`test_error_holds_no_input_text` in `tests/test_parser.py`).
3. On the 800-53 catalog with `metadata` removed, `tracemalloc` measures what each option holds after the raise:

   | What the caller keeps | Held |
   |---|---|
   | The `ValidationError` | 25.7 MB |
   | `errors()`, with `input` | 25.2 MB |
   | `errors(include_input=False)` | 0.5 MB, most of it the pydantic-core string cache (D4) |

   So the change must replace the container inputs and drop the reference to the `ValidationError`.
4. `_name_root_keys` (design D7 of the archived `discriminate-document-union` change) reads the keys of the `input`
   dict of an `oscal_document_type` entry to write its message.
5. The tests read `input` only for a scalar: a YAML scalar in `tests/test_yaml_io.py`, and `None` for a limit entry.
6. A name in `v1.__all__` must be in the surface snapshot (`tests/support/version_package.py`) and, unless it is a
   generated model type, in `openspec/traceability.json`.

## Goals / Non-Goals

**Goals:**

1. Bound what a parse error holds after the raise by the number of entries and the size of the scalar inputs, not by
   the size of the document.
2. Keep each scalar `input`, because the bad value is the most useful part of most entries.

**Non-Goals:**

1. Bound the peak memory of a failing parse. `errors()` builds each `input` before the change replaces it.
2. Fewer entries for a nested union ([#43]).
3. A change to `type`, `loc`, `msg`, `url`, or `ctx`.

## Decisions

### D1: A container input becomes the sentinel `OscalParseError.OMITTED_INPUT`

`parse_oscal` sets `input` to `OscalParseError.OMITTED_INPUT` for each schema entry whose `input` is a `dict` or a
`list`. Each other `input` stays. A limit entry keeps `input: None`.

The sentinel is the one instance of a private class in `parser.py`. Its repr is `<omitted input>`. `__copy__`,
`__deepcopy__`, and `__reduce__` give the same object, so `entry["input"] is OscalParseError.OMITTED_INPUT` holds
after a copy or a pickle round trip. The class attribute keeps the public surface as it is: `__all__`, the snapshot in
`tests/support/version_package.py`, and `openspec/traceability.json` do not change.

Alternative: `None`. In Python it reads as a null input, which is a different statement.

Alternative: no `input` key. An absent key states "not kept", but `entry["input"]` then raises `KeyError`, and the
limit entries and three of their assertions change for consistency.

Alternative: a marker string such as `"Redacted"` or `<object with 7 keys>`. A caller cannot tell it from an input
string with the same text, and "redacted" implies that the value is sensitive.

Alternative: a top-level export, `oscal_bindings.OMITTED_INPUT`. It is shorter to import, but it adds a public name, so
the surface snapshot and the traceability record change.

Trade-off: `json.dumps(error.errors)` fails on the sentinel, as it already fails on a `loc` tuple key or a `ctx` value
that is not JSON. A caller passes `default=repr`. The `type` of the entry still tells the caller what failed.

### D2: `parse_oscal` raises outside the `except` block

`parse_oscal` keeps the entries in a local variable in the `except` block and raises after the block, as it does for a
limit entry. The `ValidationError` is then free when the caller catches the `OscalParseError`.

Trade-off: the traceback no longer shows the `ValidationError`. The entries carry its detail.

### D3: The root keys are read before the inputs are replaced

`parse_oscal` applies `_name_root_keys` first, and then replaces the container inputs. The `oscal_document_type` entry
thus names the keys of the object, and its `input` is the sentinel.

### D4: The memory test uses the 800-53 catalog of the NIST corpus fixture

The test takes the 800-53 catalog from `nist_docs`, removes `metadata`, and writes it as compact JSON (5.1 MB). It
measures with `tracemalloc` the memory that dropping the caught `OscalParseError` frees, not the total after the
parse. pydantic-core keeps a JSON string cache across parses: about 0.9 MB on a cold cache and 0.45 MB on a warm one,
which stays after each error is gone. The error itself holds about 1 KB. The bound is one tenth of the input text
(513 KB). Without the sentinel, the same test measures 24.8 MB.

## Risks / Trade-offs

1. [A caller reads a dict or a list from `input`] → The release notes state the change. `loc` gives the location, and
   the caller can read the value from its own input.
2. [A caller serializes the entries with `json.dumps`] → The README shows `default=repr` (D1, trade-off).
3. [The peak memory of a failing parse stays high] → Non-Goals 1. The peak ends when `parse_oscal` returns.
4. [A test or a caller relies on `__cause__` of a schema error] → No test does (Context item 5). The README states
   that the entries carry the detail.

## Migration Plan

1. Release the change in the next minor version, with a release-notes entry.
2. Rollback: revert the commit.

[#43]: https://github.com/cairn-proofs/oscal-bindings-python/issues/43
