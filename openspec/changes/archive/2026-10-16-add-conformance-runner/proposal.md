## Why

The bindings contract is in the spec store cairn-proofs/oscal-bindings-specs, with a conformance corpus, published as
the pinned artifact `v0.1.0+oscal.1.2.3`. No test in this repo runs that corpus, so nothing shows that this binding
conforms, and nothing detects a regression against the contract. This change is the Python part of phase 1 of the plan
in the store change `reverse-engineer-oscal-bindings-spec` (its design.md, D8). It is tracked in #14.

## What Changes

1. Add a conformance runner to the test suite. `hatch test` runs each case of the corpus in the pinned artifact and
   compares the result with the expected result:
   1. A round trip parses with the generic parser and the typed parser, serializes, and compares the canonical form of
      the output with the expected canonical form.
   2. An error case checks the error category, and for a schema failure, the number of structured failure entries.
   3. An element case checks the validity result or the unknown-element-type error.
   4. Each case also checks the non-raising validity check: true for a round-trip input, false for a parse-error
      input.
2. Fetch the artifact by its URL and check its `sha256` before use. The test suite caches it with the existing corpus
   cache. A hash mismatch or a failed fetch fails the run. It never skips.
3. Mark the two known defects as expected failures: the name-keyed field (#6) and the seventh fraction digit (#19). A
   fix makes the case pass unexpectedly, and the run then fails until the mark is removed.
4. Delete the parked spec identifier checker, `scripts/check_spec_ids.py` and `tests/test_check_spec_ids.py`. The store
   has its own checker. This repo cites no spec identifiers.

## Capabilities

### New Capabilities

None. The runner is test tooling. The library behavior does not change, and the behavior it checks is specified in the
store's main specs.

### Modified Capabilities

None.

## Impact

1. New test modules under `tests/`, and a new support module next to `tests/support/corpus.py`.
2. No change to `src/`, to `scripts/postprocess_models.py`, to `hatch run generate`, or to the vendored `schemas/`.
3. No new dependency. The canonical JSON form is implemented in the test support code.
4. `hatch test` needs network access on a cache miss, the same as the existing corpus tests.
