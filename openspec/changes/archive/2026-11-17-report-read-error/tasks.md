# Tasks

## 1. Baseline before the change

- [x] 1.1 Run `hatch run python scripts/bench_serialization.py` and `hatch run python scripts/bench_memory.py` on
  `main`. Record the medians, GC on and GC off, in the scratchpad. Verify that the record is not empty.

## 2. Read error

- [x] 2.1 Add `OscalReadError(OSError)` to `src/oscal_bindings/v1/parser.py`, below `OscalDocumentTypeMismatchError`,
  as [design D1](design.md#d1-oscalreaderror-is-a-subclass-of-oserror) states. Its docstring says that it is not a
  parse error and not a not-found error, and that `except OSError` catches it and `FileNotFoundError`. Re-export it from
  `src/oscal_bindings/v1/__init__.py`, and add it to the import list and `__all__` of the alias module
  `src/oscal_bindings/parser.py`. Add it to `tests/support/version_package.py`, and add an entry with `ERR-001` and
  `ERR-012` to `openspec/traceability.json`. Verify that `from oscal_bindings.parser import OscalReadError` gives the
  same class as `oscal_bindings.v1.OscalReadError`.
- [x] 2.2 Change `_read_oscal_file` to read with no `exists()` call, and map the exception as
  [design D2](design.md#d2-the-read-itself-finds-the-category-with-no-exists-call) states. Update the `Raises` sections
  of `_read_oscal_file`, `parse_oscal_file`, and `parse_oscal_yaml_file` (`src/oscal_bindings/v1/extensions/yaml_io.py`).
  Verify with new tests in `tests/test_parser.py`:
  1. A directory raises an error that is an instance of `OscalReadError` and of `OSError`, and not an instance of
     `OscalParseError` or of `FileNotFoundError`. Its `filename` is the path, and `str` of the error contains the path.
  2. A file with mode `0o000`, a loop of two symbolic links, and a file in a directory with mode `0o000` each raise
     `OscalReadError` whose `str` contains the path, as [design D3](design.md#d3-tests-of-read-failures-that-the-corpus-cannot-hold)
     states. Each test is skipped when `os.geteuid() == 0`.
  3. A path below a regular file (`ENOTDIR`) raises `FileNotFoundError` whose `str` contains the path.
  4. A path that contains a NUL byte raises `FileNotFoundError`, chained from the `ValueError`, and not
     `ValueError` itself.
  5. The existing not-found tests in `tests/test_parser.py` and `tests/test_yaml_io.py` pass with no edit.
- [x] 2.3 Add a test in `tests/test_yaml_io.py`: `parse_oscal_yaml_file` of a directory raises `OscalReadError`. Verify
  that it passes.

## 3. Conformance runner

- [x] 3.1 In `tests/test_conformance.py`, map `OscalReadError` to `read-error` in `category`, and add
  `category(OscalReadError())` to the set in `test_every_category_is_mapped`. Change the reason of that strict expected
  failure to cite only [#62]. Remove `parse-file/directory` from `tests/support/expected_failures.py`. Verify with
  `hatch test tests/test_conformance.py` that `parse-file/directory` passes and that
  `test_every_category_is_mapped` is still an expected failure.

## 4. Docs

- [x] 4.1 Update the error docs for the read-error category. Verify with a `grep` for `FileNotFoundError` in each file
  that each statement about a file-path failure names both categories:
  1. `README.md`: the error paragraph at line 305 names `OscalReadError` and says that `except OSError` catches both
     file categories. The comment at line 196 stays.
  2. `AGENTS.md`: a note in "Repo-Specific Patterns & Gotchas" that a file-path parse finds the category from the read,
     with no `exists()` call.
  3. `.agents/summary/interfaces.md`: a row for the read failure in the error table, below the row at line 125.
  4. `.agents/summary/workflows.md` line 106, `.agents/summary/components.md`, and `.agents/summary/review_notes.md`
     line 20: the read error beside not-found.

## 5. Integration

- [x] 5.1 Run `hatch run release`. Verify that it passes, and that `git diff --exit-code -- src/oscal_bindings/v1/models.py`
  shows no change.
- [x] 5.2 Run the two benchmark scripts of task 1.1 again. Record the before and after medians, GC on and GC off, for
  the PR description. Verify that the record has both runs.

## Workflow follow-up

- Commit as `feat!:` with a `BREAKING CHANGE` footer that says a file-path parse raises `OscalReadError`, not
  `OscalParseError`, for a read failure. Close #61.
- Archive the change after review.

[#62]: https://github.com/cairn-proofs/oscal-bindings-python/issues/62
