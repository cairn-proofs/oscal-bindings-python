# Design

## Context

See [proposal.md - Why](proposal.md#why) for the motivation. These facts constrain the approach.

1. Three file-path parses read the file through `_read_oscal_file` in `parser.py`: `parse_oscal_file`,
   `parse_oscal_yaml_file` (through `_yaml_loader.py`), and `OscalDoc.from_file` (through `parse_oscal_file`). Thus one
   edit to `_read_oscal_file` gives the same behavior to all three.
2. `Path.read_bytes` raises a subclass of `OSError` for each read failure. The subclass follows the `errno`: `ENOENT`
   gives `FileNotFoundError`, `ENOTDIR` gives `NotADirectoryError`, `EISDIR` gives `IsADirectoryError`, and `EACCES`
   gives `PermissionError`. `ELOOP` gives a plain `OSError`.
3. The conformance runner (`category` in `tests/test_conformance.py`) maps a class to a category.
   `test_every_category_is_mapped` is a strict expected failure until each category of the corpus has a class. The
   builder-error category ([#62]) has no class yet.
4. A name in `v1.__all__` must be in the surface snapshot (`tests/support/version_package.py`) and in
   `openspec/traceability.json`.

## Goals / Non-Goals

**Goals:**

1. The category of a read failure is the same on each supported Python version.

**Non-Goals:**

1. A change to the message of the not-found error.

## Decisions

### D1: `OscalReadError` is a subclass of `OSError`

The not-found category is `FileNotFoundError`, which is a subclass of `OSError`. A read error is also a failure of the
operating system to give the bytes of a file. With `OscalReadError(OSError)`, the two file categories have one parent
in the Python hierarchy:

```
OSError
 +-- FileNotFoundError   (not-found)
 +-- OscalReadError      (read error)
```

1. A caller catches each failure to read a file with `except OSError`, and catches no parse error with it.
2. `OscalReadError` has `errno`, `strerror`, and `filename` from `OSError`, with no new code.
3. The binding raises it as `OscalReadError(e.errno, e.strerror, str(path)) from e`. `OSError.__str__` then gives
   `[Errno 21] Is a directory: 'documents/valid'`, which names the path (ERR-012).
4. Python maps an `errno` to a subclass only when the code calls `OSError` itself. A call to a subclass does not get
   this mapping. Thus `OscalReadError(errno.EISDIR, ...)` stays an `OscalReadError`.

The class is in `parser.py`, below `OscalDocumentTypeMismatchError`. It goes through the re-export chain: `v1/__init__.py`
and the explicit import list and `__all__` of the alias module `src/oscal_bindings/parser.py`.

Alternative: `OscalReadError(Exception)`, beside `OscalAccessError`. A caller then needs two `except` clauses to catch
each failure to read a file, and the error has no `errno`. Rejected.

### D2: The read itself finds the category, with no `exists()` call

`_read_oscal_file` calls `read_bytes` with no check before it, and maps the exception:

1. `FileNotFoundError` or `NotADirectoryError` gives `FileNotFoundError` with the current message,
   `OSCAL file not found: <path>`, raised `from` the original error.
2. Each other `OSError` gives `OscalReadError`, as [D1](#d1-oscalreaderror-is-a-subclass-of-oserror) shows.
3. A `ValueError` (a path that the operating system cannot represent, such as one with a NUL byte or an
   unencodable surrogate) gives `FileNotFoundError` with the current message, raised `from` the original error. No
   file can exist at such a path, and the failure has nothing to do with OSCAL. This keeps the current behavior.

The exception that the read raises is the only fact that decides. `Path.exists()` hides the `errno`, and its result for a failure
that is not `ENOENT` changes with the Python version. The check before the read also allowed a race: the path can change
between `exists()` and `read_bytes`. A single read removes the race.

Alternative: keep `exists()` and add a `try` around it. The result of `exists()` is still a bool, so the `errno` stays
hidden. Rejected.

### D3: Tests of read failures that the corpus cannot hold

The corpus holds only the directory case. The unit tests in `tests/test_parser.py` create each other case in `tmp_path`:

1. A file with mode `0o000` (ERR-012.02).
2. A loop of two symbolic links.
3. A file in a directory with mode `0o000`.

A process with root privileges reads each of these paths. Thus each of these tests is skipped when `os.geteuid() == 0`.
Each test sets the mode back in a `finally` block, so that pytest can delete `tmp_path`.

## Risks / Trade-offs

1. [Code that catches `OscalParseError` around a file-path parse stops catching a read failure.] → The commit is a
   `feat!` with a `BREAKING CHANGE` footer, and the README says that `except OSError` catches both file categories.
2. [A test run as root skips the permission tests.] → The CI runner is not root, so CI runs them.

[#62]: https://github.com/cairn-proofs/oscal-bindings-python/issues/62
