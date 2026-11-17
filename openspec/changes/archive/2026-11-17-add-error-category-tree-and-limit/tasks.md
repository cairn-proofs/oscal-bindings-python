# Tasks

## 1. Baseline before the change

- [x] 1.1 Run `hatch run python scripts/bench_serialization.py` and `hatch run python scripts/bench_memory.py` on
  `main`. Record the medians, GC on and GC off, in the scratchpad. Verify that the record is not empty.

## 2. Document-type mismatch

- [x] 2.1 Add `OscalDocumentTypeMismatchError` to `src/oscal_bindings/v1/parser.py`, and make the eight typed parsers
  raise it, as [design D1](design.md#d1-a-category-is-a-class-and-the-tree-is-the-class-hierarchy) item 1 states.
  Re-export it from `src/oscal_bindings/v1/__init__.py`, and add it to the import list and `__all__` of the legacy
  alias module `src/oscal_bindings/parser.py` (design D1 item 3). Add it to `tests/support/version_package.py` and to
  `openspec/traceability.json` ([design D6](design.md#d6-traceability)). Verify with new tests in
  `tests/test_parser.py`:
  1. A profile through `parse_catalog` raises an error that is an instance of `OscalDocumentTypeMismatchError` and of
     `OscalParseError`, with the message that names the catalog.
  2. Input that is not valid JSON raises an `OscalParseError` that is not an instance of
     `OscalDocumentTypeMismatchError`.
  3. `from oscal_bindings.parser import OscalDocumentTypeMismatchError` gives the same class as `oscal_bindings.v1`.

## 3. Unknown element type

- [x] 3.1 Add `OscalUnknownElementTypeError` to `src/oscal_bindings/v1/extensions/validate_element.py`, and make
  `validate_element` raise it, as [design D1](design.md#d1-a-category-is-a-class-and-the-tree-is-the-class-hierarchy)
  item 2 states. Update the `Raises` section of the docstring. Re-export the class through `extensions/__init__.py` and
  `v1/__init__.py`, and add it to `tests/support/version_package.py` and to `openspec/traceability.json`. Change
  `tests/test_validate_element.py` lines 90 and 98 to expect the new class. Change
  `tests/test_prop_validate_element.py` line 117 and its module docstring at line 11 to the new class. Verify with a new
  test that the error is not an instance of `OscalParseError`.

## 4. Limit property

- [x] 4.1 Add the keyword `limit` to `OscalParseError`, and document the attribute in its docstring, as
  [design D3](design.md#d3-the-limit-property-is-an-attribute-not-a-class) states. Add ERR-009 and ERR-010 to the
  `OscalParseError` entry of `openspec/traceability.json`.
- [x] 4.2 Set `limit` at each of the six raise sites, as
  [design D4](design.md#d4-each-raise-site-sets-the-identifier-and-the-entry-types-stay) item 3 states. Verify with new
  tests in `tests/test_parser.py` and `tests/test_yaml_io.py`:
  1. Each of the six limits gives its identifier from the spec.
  2. The alias-character test input stays within the alias node limit.
  3. `test_aliases_that_nest_past_the_limit_are_rejected` in `tests/test_yaml_io.py` asserts `limit == "yaml_depth"`,
     so the `emit` depth site is covered as well as the compose-stage site.
  4. A schema failure, a document-type mismatch, and a YAML alias cycle each give `limit is None`.
- [x] 4.3 Add a `limit` column to the table in the README section "Resource limits", and add one sentence on the test
  `error.limit is not None` for an `OscalParseError` and `getattr(error, "limit", None) is not None` for any error
  ([design D3](design.md#d3-the-limit-property-is-an-attribute-not-a-class)). Verify that the table has six rows, each
  with the identifier of the spec.

## 5. Conformance runner and docs

- [x] 5.1 Change `category` and `test_every_category_is_mapped` in `tests/test_conformance.py`, as
  [design D5](design.md#d5-the-runner-reads-the-class-only) states. Verify that `grep -n "startswith"` over
  `tests/test_conformance.py` finds no category test, and that `hatch test tests/test_conformance.py` passes.
- [x] 5.2 Update the error text in `README.md`, `AGENTS.md` (the `validate_element` gotcha), and
  `.agents/summary/interfaces.md`, `workflows.md`, `components.md`, and `review_notes.md` for the two new classes.
  Verify that `grep -rniE "unknown.*OscalParseError|OscalParseError.*unknown" README.md AGENTS.md .agents/summary/`
  finds nothing.

## 6. Final verification

- [x] 6.1 Repeat task 1.1. Verify that no median moves by more than the run-to-run spread of the two runs.
- [x] 6.2 Run `hatch run release`. Verify that it passes.

## Workflow follow-up

- Open the pull request with `Closes #60`. Report the benchmark runs of tasks 1.1 and 6.1 in it, and name the break of
  `validate_element` for an unknown element type.
- Archive the change in the pull request, before the merge.
