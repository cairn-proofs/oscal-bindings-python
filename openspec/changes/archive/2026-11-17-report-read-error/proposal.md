# Proposal

## Why

The store requirement ERR-012 (cairn-proofs/oscal-bindings-specs#41, PR cairn-proofs/oscal-bindings-specs#55) says that a
file-path parse that cannot read the file at a path reports the read-error category of ERR-001. A path that the platform
reports as missing is the exception. It is not-found (ERR-006). A read error names the path. It is not a parse error and
not a not-found error ([#61]).

The binding does not meet ERR-012:

1. The binding has no read-error category. `_read_oscal_file` in `src/oscal_bindings/v1/parser.py` raises
   `OscalParseError` for each read failure. Thus a directory gives a parse error, and the corpus case
   `parse-file/directory` is an expected failure.
2. `_read_oscal_file` calls `Path.exists()` before the read, and raises `FileNotFoundError` when `exists()` is false. On
   Python 3.12, `exists()` is false for `ELOOP` and `EBADF`. Thus a loop of symbolic links gives not-found. On Python 3.14,
   `exists()` is false for each `OSError`. Thus a path with a directory that the caller cannot search gives not-found. The
   category of a read failure changes with the Python version.

The pin is at `v0.8.0+oscal.1.2.3` (#70), the release that has ERR-012. Thus the fix is now possible.

## What Changes

1. A new exception `OscalReadError`, a subclass of `OSError`. It is not a subclass of `OscalParseError` or of
   `FileNotFoundError`. Each file-path parse raises it for a read failure that is not a missing path. Its `errno`,
   `strerror`, and `filename` come from the failure, and its message names the path.
2. A file-path parse raises `FileNotFoundError` only when the read fails with `ENOENT` or `ENOTDIR`. The binding does not
   call `Path.exists()` to find the category.
3. **BREAKING**: a file-path parse does not raise `OscalParseError` for a read failure. Code that catches
   `OscalParseError` for a directory, a permission failure, or an I/O error does not catch the new error. Code that
   catches `OSError` catches both the read error and not-found.
4. The conformance runner maps `OscalReadError` to the category `read-error`. The corpus case `parse-file/directory`
   passes.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

1. `error-tests`: the list of categories and classes gets the read-error category and its class `OscalReadError`.

## Impact

1. Code: `src/oscal_bindings/v1/parser.py` and the re-exports in `src/oscal_bindings/v1/__init__.py` and the alias
   module `src/oscal_bindings/parser.py`. The YAML file parser and `OscalDoc.from_file` use `_read_oscal_file`, so they
   get the same behavior with no edit to their code.
2. Tests: `tests/test_conformance.py`, `tests/support/expected_failures.py`, `tests/test_parser.py`, and
   `tests/test_yaml_io.py`.
3. Docs: the `Raises` sections of `parse_oscal_file` and `parse_oscal_yaml_file`, `README.md`, `AGENTS.md`, and
   `.agents/summary/interfaces.md`.
4. Public API: one new exception class, and the exception that a file-path parse raises for a read failure.

[#61]: https://github.com/cairn-proofs/oscal-bindings-python/issues/61
