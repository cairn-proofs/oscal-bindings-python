# Implementation Plan: Property-Based Tests

## Overview

Add a Hypothesis-based property test suite that exercises the public API (parsers, `OscalDoc` facade, back-matter builders, `validate_element`). Inputs come from two commit-pinned remote corpora (NIST + AWS, together covering 7 of 8 document types), an optional local corpus named by `OSCAL_BINDINGS_LOCAL_CORPUS` that supplies mapping-collection, and from synthetic Hypothesis strategies for builders/leaf types. This is a test-only feature: the sole change outside `tests/` is uncommenting one `pyproject.toml` line plus a `.gitignore` entry. Tasks build incrementally — dependency enablement first, then the corpus fetcher infrastructure, then fixtures/strategies, then the property modules that wire everything together, closing with a full-matrix verification.

All property tests must be annotated with the tag `Feature: property-based-tests, Property {number}: {property_text}` and configured for at least 100 examples (`max_examples=100` via the `ci` Hypothesis profile).

## Tasks

- [x] 1. Enable Hypothesis and ignore the corpus cache
  - Uncomment / add `extra-dependencies = ["hypothesis"]` under `[tool.hatch.envs.hatch-test]` in `pyproject.toml`
  - Add `/tests/.corpus_cache/` to `.gitignore`
  - Leave all modules under `src/oscal_bindings/` unmodified
  - _Requirements: 1.1, 1.2, 1.3, 3.3_

- [x] 2. Implement the Corpus_Fetcher support module
  - [x] 2.1 Create `tests/support/__init__.py` and `tests/support/corpus.py` core structures
    - Define `CorpusError(RuntimeError)`, frozen `CorpusSpec` (name/owner/repo/sha/include_globs plus a `require_oscal_root: bool = True` flag, with `tarball_url` property → `codeload.github.com/{owner}/{repo}/tar.gz/{sha}`), and frozen `CorpusDoc` (corpus_name/rel_path/raw_bytes plus a `root_key` field holding the single top-level OSCAL key)
    - Define the `OSCAL_ROOT_KEYS` frozenset of the 8 document root keys (`catalog`, `profile`, `component-definition`, `system-security-plan`, `assessment-plan`, `assessment-results`, `plan-of-action-and-milestones`, `mapping-collection`)
    - Define `NIST_CORPUS` (usnistgov/oscal-content, pinned 40-hex SHA, `include_globs=("**/*.json",)`, `require_oscal_root=True`) and `AWS_CORPUS` (awslabs/oscal-content-for-aws-services, pinned 40-hex SHA, `include_globs=("component-definitions/**/*.json",)`, `require_oscal_root=True`)
    - Define `CACHE_ROOT = tests/.corpus_cache`
    - **NOTE:** the two corpus commit SHAs are now pinned in the design (NIST `78650f02ad9321bb7b817846f8fbd4f2bcd620de`, AWS `4a1779ffb556c4ab8fb3dad94a19d4d198116803`), each to its repo's HEAD commit as of the pin date, so this task is now executable.
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 2.2 Implement fetch, atomic cache, and concurrency safety in `corpus.py`
    - Implement `_http_get` via `urllib.request` (stdlib only, no `requests`) and `_extract_tar_gz` into a temp dir
    - Implement `ensure_corpus(spec, *, cache_root=CACHE_ROOT)`: cache-hit returns `{repo}-{sha}` dir when `.complete` marker exists (no network); cache-miss downloads, extracts to per-PID temp dir, touches `.complete`, publishes with `os.replace`
    - Implement a per-corpus `FileLock` (`os.open` with `O_CREAT|O_EXCL` spin-with-backoff, or `fcntl.flock`) guarding the fetch so it happens at most once; re-check `.complete` under the lock
    - Wrap network/HTTP failures with empty cache in `CorpusError` whose message contains the corpus `name` and pinned `sha`; never call `pytest.skip`
    - _Requirements: 3.1, 3.2, 4.1, 4.2, 4.3, 5.1, 5.2, 5.3, 5.4_

  - [x] 2.3 Implement `load_corpus_docs(spec, *, cache_root=CACHE_ROOT)`
    - Call `ensure_corpus`, then walk the extracted tree matching `spec.include_globs`, returning `list[CorpusDoc]` with `rel_path` as the identifier and `raw_bytes` read from disk
    - When `spec.require_oscal_root` is set, parse each candidate JSON just far enough to inspect its top-level keys and apply a top-level root-key filter that drops any file whose single top-level key is not in `OSCAL_ROOT_KEYS` (removing non-document JSON — metaschema/config — before yielding `CorpusDoc`s); set `CorpusDoc.root_key` to the matched key. NIST keeps its broad glob and relies on this filter
    - _Requirements: 2.3, 2.4, 6.4_

  - [x] 2.4 Write example/edge tests in `tests/test_corpus_fetcher.py`
    - Cache-miss downloads and stores (monkeypatched HTTP); cache-hit returns without network (monkeypatch `_http_get` to raise, assert not called) — _Requirements: 3.1, 3.2_
    - Assert `tests/.corpus_cache/` is covered by a `.gitignore` pattern — _Requirements: 3.3_
    - Concurrency: N threads requesting the same missing corpus invoke the network at most once and return identical content — _Requirements: 4.1, 4.2, 4.3_
    - Hard-fail: forced HTTP failure with empty cache raises `CorpusError` containing corpus name + SHA, and is an error not a skip — _Requirements: 5.1, 5.2, 5.3, 5.4_
    - AWS docs all live under `component-definitions/`; the set of NIST `root_key`s equals exactly the 7 published types (`catalog`, `profile`, `component-definition`, `system-security-plan`, `assessment-plan`, `assessment-results`, `plan-of-action-and-milestones`) and `mapping-collection` is absent, so the test flags it if a future NIST pin adds one (asserted **after** the root-key filter, which also confirms non-document JSON like metaschema/config is dropped so it never reaches `parse_oscal`); pinned SHAs are well-formed 40-hex strings — _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 2.5 Implement `load_local_corpus_docs()` and its tests
    - In `tests/support/corpus.py`, add `LOCAL_CORPUS_ENV = "OSCAL_BINDINGS_LOCAL_CORPUS"` and `load_local_corpus_docs(*, environ=os.environ) -> list[CorpusDoc]` per the design: unset/empty → `[]`; file → that file with `rel_path` = basename; directory → `**/*.json` with `rel_path` relative to the directory (POSIX-style); same root-key filter as `load_corpus_docs` (factor a shared helper); `corpus_name="local"`; read in place, no network, no `CACHE_ROOT` writes, no copies
    - Set but missing/unreadable, or zero OSCAL docs after the filter → `CorpusError` whose message names `LOCAL_CORPUS_ENV` and excludes document content
    - Declare `CorpusDoc.raw_bytes` as `field(repr=False)` so a failing Hypothesis example never prints local document content
    - Never place the real local document anywhere under the repo; tests use only synthetic `tmp_path` files
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8, 11.11, 11.12, 11.13_
    - Tests in `tests/test_local_corpus.py`: all cases build tiny OSCAL/non-OSCAL JSON under `tmp_path` and drive the env var with `monkeypatch.setenv` / `monkeypatch.delenv`
    - Unset → `[]` — _Requirements: 11.8_
    - Single file → one doc, `corpus_name == "local"`, correct `root_key`, `rel_path` is the basename — _Requirements: 11.1, 11.3, 11.5_
    - Directory with nested OSCAL and non-OSCAL JSON → only OSCAL docs, `rel_path` relative to the directory — _Requirements: 11.2, 11.3, 11.4_
    - Set but missing path → `CorpusError` naming `OSCAL_BINDINGS_LOCAL_CORPUS` — _Requirements: 11.11_
    - Set, no OSCAL docs after filter → `CorpusError` naming the variable; message excludes the file's content — _Requirements: 11.12, 11.13_
    - No `rel_path` is absolute or contains the configured root path — _Requirements: 11.4, 11.5_
    - `_http_get` monkeypatched to raise and `CACHE_ROOT` pointed at an empty `tmp_path` subdir that stays empty — _Requirements: 11.6, 11.7_

- [x] 3. Checkpoint - Ensure the fetcher works
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Add session fixtures and Hypothesis profiles in `tests/conftest.py`
  - [x] 4.1 Add session-scoped corpus fixtures
    - `nist_docs`, `aws_docs` (via `load_corpus_docs`), `local_corpus_docs` (via `load_local_corpus_docs()`, `[]` when the env var is unset), and `all_corpus_docs = [*nist_docs, *aws_docs, *local_corpus_docs]`, plus partitions `ap_ar_docs` (AP + AR only) and `non_ap_ar_docs` (the other 6 types, including any local mapping-collection), each loaded once per session
    - Partition on `CorpusDoc.root_key` using `AP_AR_KEYS = {"assessment-plan", "assessment-results"}` (`ap_ar_docs` keeps `root_key in AP_AR_KEYS`, `non_ap_ar_docs` keeps the rest)
    - Assert non-emptiness of `all_corpus_docs`, `ap_ar_docs`, and `non_ap_ar_docs` — an empty partition is a hard failure (fail-loud), never a skip, since `st.sampled_from([])` raises `InvalidArgument`
    - A `CorpusError` from `load_local_corpus_docs()` (set but invalid/empty) propagates, erroring every dependent test
    - _Requirements: 5.4, 6.1, 7.2, 7.3, 10.3, 11.11, 11.12, 11.14_

  - [x] 4.2 Register Hypothesis profiles at import time
    - Register `ci` (`max_examples=100`, `deadline=None`, `print_blob=True`, suppress `too_slow`/`function_scoped_fixture`) and `dev` (`max_examples=50`); load from `HYPOTHESIS_PROFILE` env (default `ci`)
    - _Requirements: 10.1, 10.4_

- [x] 5. Implement synthetic Hypothesis strategies in `tests/strategies.py`
  - Add `hash_strategy`, `rlink_strategy` (respects `media_type` kwarg alias), and `resource_strategy` producing builder kwargs (hex digests, algorithm enum members, hrefs, optional media types, titles/descriptions/uuid/document_ids)
  - Define an explicit, documented `LEAF_ELEMENT_TYPES` allow-list of simple, flat, non-recursive types — `("hash", "rlink", "link", "property", "document-id")` — instead of enumerating the full `get_supported_element_types()` return (which spans 187 types including recursive/composite bodies)
  - Add `leaf_instance_strategy(element_type)` targeting **only** the allow-listed types: construct the mapped Pydantic model with generated field values and `model_dump(by_alias=True, exclude_none=True)` to a validator-ready dict
  - Never synthesize a full OSCAL document
  - _Requirements: 8.4, 9.1, 9.4_

- [x] 6. Implement round-trip property module `tests/test_prop_roundtrip.py`
  - [x] 6.1 Property 1 — round-trip preserves the model
    - Take the `all_corpus_docs` fixture plus a `data` param and `@given(data=st.data())`; draw `doc = data.draw(st.sampled_from(all_corpus_docs))` inside the test body (the `st.data()` pattern, since `@given` cannot close over a fixture value)
    - `parse_oscal(doc.raw_bytes)` → `serialize_oscal` → `parse_oscal` yields an equal model; include `rel_path` in the failure diagnostic
    - Tag: `Feature: property-based-tests, Property 1`; `max_examples>=100`
    - _Requirements: 6.1, 6.4_

  - [x] 6.2 Property 2 — mutated documents still round-trip
    - Take `all_corpus_docs` plus a `data` param and `@given(data=st.data())`; draw `doc = data.draw(st.sampled_from(all_corpus_docs))` in the test body
    - Mutate the **optional** `metadata.remarks` scalar (not the required `title`/`version`) with a Hypothesis non-empty string via nested reconstruction — rebuild metadata → body → wrapper with `model_copy(update=...)` (optionally through a `set_metadata_remarks(model, text)` helper), then re-serialize and assert the same round-trip equality
    - Tag: `Feature: property-based-tests, Property 2`; `max_examples>=100`
    - _Requirements: 6.2_

  - [x] 6.3 Property 3 — bytes and str inputs parse identically
    - Take `all_corpus_docs` plus a `data` param and `@given(data=st.data())`; draw `doc = data.draw(st.sampled_from(all_corpus_docs))` in the test body
    - Assert `parse_oscal(doc.raw_bytes) == parse_oscal(doc.raw_bytes.decode("utf-8"))`
    - Tag: `Feature: property-based-tests, Property 3`; `max_examples>=100`
    - _Requirements: 6.3_

  - [x] 6.4 Implement the mapping-collection coverage check in `tests/test_corpus_coverage.py`
    - Separate module (not `test_prop_roundtrip.py`), since this is a coverage assertion rather than a property
    - When `OSCAL_BINDINGS_LOCAL_CORPUS` is unset: `pytest.skip` with a reason naming `OSCAL_BINDINGS_LOCAL_CORPUS` (the one sanctioned skip; visible in pytest's short summary)
    - When set: assert `all_corpus_docs` contains at least one doc with `root_key == "mapping-collection"`, with a failure message naming the variable
    - _Requirements: 11.9, 11.10, 11.15_

- [x] 7. Implement facade property module `tests/test_prop_facade.py`
  - [x] 7.1 Property 4 — facade accessors never raise on valid documents
    - Take the `all_corpus_docs` fixture plus a `data` param and `@given(data=st.data())`; draw `doc = data.draw(st.sampled_from(all_corpus_docs))` in the test body
    - Wrapping in `OscalDoc` and accessing `metadata`, `uuid`, `oscal_version`, `body` completes without raising
    - Tag: `Feature: property-based-tests, Property 4`; `max_examples>=100`
    - _Requirements: 7.1_

  - [x] 7.2 Property 5 — `assessment_period()` succeeds for AP/AR
    - Take the `ap_ar_docs` fixture plus a `data` param and `@given(data=st.data())`; draw `doc = data.draw(st.sampled_from(ap_ar_docs))` in the test body
    - `assessment_period()` returns a value without raising
    - Tag: `Feature: property-based-tests, Property 5`; `max_examples>=100`
    - _Requirements: 7.2_

  - [x] 7.3 Property 6 — `assessment_period()` rejects non-AP/AR
    - Take the `non_ap_ar_docs` fixture plus a `data` param and `@given(data=st.data())`; draw `doc = data.draw(st.sampled_from(non_ap_ar_docs))` in the test body
    - `assessment_period()` raises `OscalAccessError`
    - Tag: `Feature: property-based-tests, Property 6`; `max_examples>=100`
    - _Requirements: 7.3_

- [x] 8. Implement builder property module `tests/test_prop_builders.py`
  - [x] 8.1 Property 7 — builders produce schema-valid back-matter
    - `@given(hash_strategy() | rlink_strategy() | resource_strategy())`: `make_X(**kwargs)`, `model_dump(by_alias=True, exclude_none=True)`, then `type(element).model_validate(dumped) == element`
    - Tag: `Feature: property-based-tests, Property 7`; `max_examples>=100`
    - _Requirements: 8.1, 8.2, 8.3_

- [x] 9. Implement validate_element property module `tests/test_prop_validate_element.py`
  - [x] 9.1 Property 8 — `validate_element` round-trips allow-listed leaf types
    - Iterate the `LEAF_ELEMENT_TYPES` allow-list; for each type assert it is in `get_supported_element_types()` (keeps the allow-list consistent), then `@given(leaf_instance_strategy(type))`: `validate_element` reports valid and the value round-trips to an equivalent value
    - Note that extending coverage to the remaining supported types is a bounded follow-on
    - Tag: `Feature: property-based-tests, Property 8`; `max_examples>=100`
    - _Requirements: 9.1, 9.2_

  - [x] 9.2 Property 9 — `validate_element` rejects unknown element types
    - `@given` a type name absent from `get_supported_element_types()`: `validate_element` raises `OscalParseError`
    - Tag: `Feature: property-based-tests, Property 9`; `max_examples>=100`
    - _Requirements: 9.3_

- [x] 10. Final checkpoint - Full-matrix verification
  - Run `hatch test --all` across the Python 3.11 and 3.12 matrix with `parallel = true`
  - Confirm property tests execute at >=100 examples each, complete without cache-contention failures, and that Hypothesis counterexamples surface in pytest output when a property fails
  - With `OSCAL_BINDINGS_LOCAL_CORPUS` unset (the CI configuration), confirm the only skip is the mapping-collection coverage check; CI covers 7 of 8 document types (known limitation)
  - Ensure all tests pass, ask the user if questions arise.
  - _Requirements: 1.2, 10.1, 10.2, 10.3, 10.4_

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP.
- Each task references specific requirements clauses for traceability.
- Every property test is annotated with its `Feature: property-based-tests, Property N` tag and configured for at least 100 examples via the `ci` Hypothesis profile.
- Corpus properties take the corpus partition fixture as a normal argument plus a `data` param and draw `data.draw(st.sampled_from(<fixture>))` inside the test body (the `st.data()` pattern) over session-loaded, non-empty lists, so the fixed corpus is fetched/parsed once and shared across xdist workers through the on-disk cache.
- Property tests validate universal correctness properties; the fetcher example tests cover infrastructure behavior that does not vary with input.
- The local opt-in corpus (`OSCAL_BINDINGS_LOCAL_CORPUS`) is read in place from an external absolute path. The real document is confidential and must never be copied under the repo: the repo is public and the sdist ships all of `tests/`, including untracked non-ignored files. CI leaves the variable unset, so CI covers 7 of 8 document types.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2"] },
    { "id": 3, "tasks": ["2.3"] },
    { "id": 4, "tasks": ["2.4", "2.5", "4.2", "5"] },
    { "id": 5, "tasks": ["4.1"] },
    { "id": 6, "tasks": ["6.1", "6.2", "6.3", "6.4", "7.1", "7.2", "7.3", "8.1", "9.1", "9.2"] }
  ]
}
```
