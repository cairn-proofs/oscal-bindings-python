# Tasks

## 1. The limit-exceeded error

- [x] 1.1 Add `OscalLimitExceededError` in `src/oscal_bindings/v1/extensions/validate_element.py` (design D3), with the
  keyword `limit`. Verify with a test that it is not a subclass of `OscalParseError` and that it keeps its `limit`.
- [x] 1.2 Raise it from `validate_element` when any entry of the `ValidationError` has the type `recursion_loop`,
  before the branch selection. Raise the error after the `except` block (design D2, D3). Verify with tests for the
  type `catalog-group-with-groups` (a model), `catalog-group` (a union), and `catalog-document` (a document), each at
  1,000 levels. Each test expects the error with the `limit` `element_depth` and no result, and asserts that `__cause__`
  and `__context__` of the error are `None`.
- [x] 1.3 Add three tests. An element at 20 levels is valid. An element within the limit with a schema failure gives an
  invalid result and no error. A group that holds itself in its `groups` list, once and two times, gives the error and
  ends.
- [x] 1.4 Export the class from `src/oscal_bindings/v1/extensions/__init__.py` and `src/oscal_bindings/v1/__init__.py`.
  Add `OscalLimitExceededError` to `PUBLISHED_ALL` in `tests/support/version_package.py`. In
  `openspec/traceability.json`, add an entry for the class with `["ERR-001", "ERR-010", "ERR-011"]` and add `ELV-004`
  to the `validate_element` entry. Verify that `oscal_bindings.OscalLimitExceededError` is the same object as the `v1`
  one and that the public-surface and traceability tests pass.
- [x] 1.5 Replace the three `KNOWN GAP` entries for ELV-004.02, ERR-011.01, and ERR-011.02 in
  `tests/support/spec_not_applicable.py` with tests that cite those scenarios with `@pytest.mark.spec`. Verify that
  `tests/test_spec_coverage.py` passes.
- [x] 1.6 Reword the stale text. Change the docstring of `TestNoUndocumentedLimit` in `tests/test_validate_element.py`
  and the ELV-004.01 reason in `tests/support/spec_not_applicable.py` to say that the binding has no limit on the number
  of failures. Verify that no remaining text says that `validate_element` has no documented limit.

## 2. Documentation

- [x] 2.1 Add the section `## Element validation` to `docs/limits.md` after the table, and one sentence in the intro
  paragraph that points to it (design D5). Verify that `tests/test_lint_config.py` passes and that the section holds the
  five items of D5.
- [x] 2.2 Add the limit-exceeded category and `OscalLimitExceededError` to `docs/errors.md`. Update the docstring of
  `validate_element` with the new `Raises` entry. Verify with `hatch run docs` and the docstring-markup test.
- [x] 2.3 Add the row for `validate_element` over the depth limit, with `OscalLimitExceededError`, to the error
  contract table of `.agents/summary/interfaces.md`. Verify that the table lists the new error.

## 3. Integration

- [x] 3.1 Run `hatch run release` and verify that it passes. Verify that `PERFORMANCE.md` needs no change, because a
  call within the limit runs the same code as before.

## Workflow follow-up

- Archive the change after the project review requirements pass.
