## 1. Pinned artifact

- [x] 1.1 Add `tests/support/spec_artifact.py` with the pin (version `0.1.0+oscal.1.2.3`, release URL, sha256) and
      `ensure_spec_artifact()`, which reuses the lock, safe extraction, and atomic publish of
      `tests/support/corpus.py` and checks the sha256 before extraction (design.md D1). Verify with synthetic tests
      that mirror `tests/test_corpus_fetcher.py`: a cache hit makes no network call, a hash mismatch raises
      `CorpusError` and publishes nothing, and a fetch failure raises `CorpusError`.
- [x] 1.2 Fetch the real artifact once and verify the cached tree holds `corpus/1.2.3/cases.json` and the `VERSION`
      `0.1.0+oscal.1.2.3`.

## 2. Canonical form

- [x] 2.1 Add `tests/support/canonical_json.py` (design.md D2). Verify with unit tests that copy the cases of the
      store's `scripts/check-canonical-json.ts`: number format, UTF-16 key order, string escapes, datetime
      normalization, and duplicate-key rejection.
- [x] 2.2 Verify that each expected file in the cached corpus is its own canonical form, byte for byte.

## 3. Conformance runner

- [x] 3.1 Add `tests/test_conformance.py`. Generate one test per case from `cases.json` (design.md D5), map exceptions
      to categories (D3), and mark each known defect of `oscal-bindings-python` as a strict expected failure (D4).
      Cover the six operations and the validity check, as the corpus README states. Verify with
      `hatch test tests/test_conformance.py`: 29 cases pass and 2 cases are expected failures, `name-keyed-field`
      (#6) and `seven-fraction-digits` (#19).
- [x] 3.2 Verify that the runner detects a regression: in a scratch run, change one expected file in the cache and
      confirm its case fails, then restore the cache. Also confirm that a known-defect case reports `XFAIL` with its
      issue URL.

## 4. Clean up and verify

- [x] 4.1 Delete `scripts/check_spec_ids.py` and `tests/test_check_spec_ids.py` (design.md D6). Verify no file in the
      repo refers to them.
- [x] 4.2 From a clean clone with an empty `tests/.corpus_cache`, run `hatch run release`. Verify it passes, the
      runner fetched the artifact by URL and checked its hash, and no runner code reads `schemas/`.
