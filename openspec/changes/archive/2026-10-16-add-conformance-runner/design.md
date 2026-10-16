## Context

See proposal.md, Why. The constraints that shape the approach:

1. The contract is in the store's main specs. The behavior to check is in `corpus/1.2.3/cases.json` of the artifact
   `v0.1.0+oscal.1.2.3`, with sha256 `89462f32e54d120c667e3744c3c27da761889d8a8fdd2c6f03b29a70a43ae33a`. The operations,
   case fields, and categories are described in the artifact's `corpus/1.2.3/README.md`.
2. Conformance compares canonical forms, as the artifact's `docs/canonical-json.md` defines: RFC 8785 (JCS) after
   datetime normalization.
3. `tests/support/corpus.py` already fetches pinned tarballs into the git-ignored cache `tests/.corpus_cache`, with a
   cross-process lock, safe extraction, and an atomic publish. A fetch failure is a hard failure, not a skip.
4. `hatch test` runs on Python 3.11 to 3.14 with `pytest-xdist`. Each worker process collects the tests.
5. Every Hatch env is locked. A new test dependency changes four `hatch-test` lockfiles.

## Goals / Non-Goals

**Goals:**

1. One test for each corpus case, named by the case id, so a failure names the case.
2. A pinned, hash-checked input. The test suite never reads an unpinned copy of the store.
3. Known defects that are visible and self-clearing: when a fix lands, the run fails until the mark is removed.

**Non-Goals:**

1. Fixing #6 or #19. Each has its own issue.
2. A typed `WrongDocumentTypeError`. The runner maps the current error messages, and the deferral noted in
   `pyproject.toml` stays as it is.
3. Running the corpus from a local checkout of the store. A later change can add an override if store development
   needs it.

## Decisions

### D1: Fetch the artifact with the existing cache machinery, and check the hash before extraction

A new module `tests/support/spec_artifact.py` holds the pin (version, URL, sha256) and an `ensure_spec_artifact()`
function. It reuses the lock, the safe extraction, the wrapper-directory strip, and the completion marker of
`tests/support/corpus.py`. It checks the `sha256` of the downloaded bytes before it extracts anything. A mismatch
raises `CorpusError` with the expected and actual hashes. The cache directory name carries the version and the start of
the hash, so a new pin never reuses an old tree.

1. **Why:** the store's design (D5) makes the hash the pin. The corpus machinery already solves concurrency and tar
   safety, and a second copy of that code would drift.
2. **Alternative considered:** read the corpus from the local store checkout through the OpenSpec reference.
   Rejected: a reference reads whatever is on disk, with no pin.
3. **Alternative considered:** vendor the corpus into this repo. Rejected: it makes a second copy of the contract, which
   the store's design rules out.

### D2: Implement the canonical form in the test support code

A new module `tests/support/canonical_json.py` implements the canonical form: duplicate-key rejection, datetime
normalization by property name, and JCS serialization. JCS serialization sorts keys by UTF-16 code units, removes
whitespace, and formats numbers with the ECMAScript number-to-string conversion. Python's `repr` of a float already
gives the shortest round-trip digits, so only the exponent form needs code. The tests check the module two ways: unit
cases that copy the store's canonical-json self-test, and the property that each expected file in the corpus is its own
canonical form.

1. **Why:** about 60 lines, with no new dependency in the four locked `hatch-test` envs.
2. **Alternative considered:** the `rfc8785` package. Rejected: its last release is 0.1.4 from 2024, its package
   metadata carries no license, and it does not do the datetime step, so the test code would still wrap it.

### D3: Map exceptions to categories in the runner

The runner maps each exception to a corpus category:

1. `FileNotFoundError` maps to `not-found`.
2. `OscalAccessError` maps to `access-error`.
3. `OscalParseError` with a message that starts with `Document is not` maps to `document-type-mismatch`.
4. `OscalParseError` with a message that starts with `Unknown element type` maps to `unknown-element-type`.
5. Each other `OscalParseError` maps to `parse-error`.

Any other exception fails the case. The structured failure count for `expected-min-failures` is the length of the
parse error's `errors` list.

1. **Why:** the library has no typed error for categories 3 and 4. The mapping lives in one function, so a typed error
   later changes one place.
2. **Trade-off:** a change to those message prefixes breaks the runner. That failure is loud, not silent.

### D4: Derive the expected failures from the corpus

A case whose `known-defects` names the binding `oscal-bindings-python` gets `pytest.mark.xfail(strict=True)`, with the
issue URL as the reason. The runner hard-codes no case id.

1. **Why:** the store owns the list of known defects. A new corpus release that adds or removes one needs no runner
   edit. `strict=True` turns a fix into a failure, so the mark cannot outlive the defect.

### D5: Generate the tests from the corpus at collection time

`pytest_generate_tests` reads `cases.json` from the cached artifact and parametrizes one test per case. A fetch failure
is a collection error, which fails the run.

1. **Why:** case ids must be known at collection time to name the tests. Each xdist worker collects, and the D1 lock
   makes the download happen once.

### D6: Delete the parked identifier checker

Delete `scripts/check_spec_ids.py` and `tests/test_check_spec_ids.py`.

1. **Why:** the store runs its own checker in CI. This repo cites no spec identifiers. The store design defers
   per-language OpenSpec tooling, and git history keeps the Python port if a later change needs it.

## Risks / Trade-offs

1. [The release asset URL stops working] → The hash check fails loudly. The pin in `spec_artifact.py` names the version
   and the URL, so a fix is one edit.
2. [A pydantic upgrade fixes #6] → The `name-keyed-field` case passes unexpectedly and the run fails. That is the
   intended signal: close #6, then the next corpus release drops the mark.
3. [Network access in CI] → The existing corpus tests already need it on a cache miss. The cache keeps local runs
   offline after the first fetch.
