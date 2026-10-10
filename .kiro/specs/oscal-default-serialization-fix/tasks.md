# Implementation Plan

Shell rule for every task: never prefix commands with `cd`; pass the tool's `cwd` instead. All Python runs through hatch (`hatch test`, `hatch run ...`); never bare `python`, `pytest`, `pip`, or `uv pip`. Commits go on the issue #5 feature branch only, include `#5` and the test status, stage files by name, and are never pushed. Slow commands use `cmd > ./tmp/<name>.log 2>&1; echo "EXIT: $?"`. Never hand-edit `src/oscal_bindings/v1/models.py`; it changes only through `hatch run generate`. `hatch run` expands `{...}` in arguments, so probes live in files under `./tmp/`, not in `python -c`.

- [x] 1. Write bug condition exploration test and capture before-state on the UNFIXED tree
  - **Property 1: Bug Condition** - Default serialization paths emit invalid OSCAL; name kwargs rejected
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists
  - **Before-state first (nothing in this task touches `src/`)**:
    - Create `scripts/bench_serialization.py` per design §11: `--catalog PATH` (default: corpus-cache SP 800-53 rev5 catalog), `--runs N` (default 7, one warm-up), medians for `parse_oscal(bytes)`, `serialize_oscal(doc, indent=None)`, `serialize_oscal(doc)`, `doc.model_dump_json()`, `pydantic_core.to_json(doc)`, plus Python/pydantic versions. Uses only API present before and after the fix
    - Lint/type-check the script (`hatch run lint`, `hatch run typing`) and run it on the unfixed tree: `hatch run python scripts/bench_serialization.py > ./tmp/bench_before.log 2>&1; echo "EXIT: $?"`
    - Commit it on its own. This is an approved commit on the issue #5 feature branch: stage only `scripts/bench_serialization.py`; the message includes `#5` and states the test status (e.g. "Add serialization benchmark script (#5). Tested: lint/typing pass, ran on unfixed tree"). Never push
    - Write `./tmp/serialize_digests.py`: loads every NIST + AWS corpus doc via `tests/support/corpus.py` (`load_corpus_docs`), writes `{path: {"indent2": sha256(serialize_oscal(doc)), "compact": sha256(serialize_oscal(doc, indent=None))}}` as JSON to `--out`. Run with `--out ./tmp/serialize_digests_before.json`
    - Write `./tmp/element_types.py` and save the sorted `get_supported_element_types()` list to `./tmp/element_types_before.txt` (expect 187 names including `root-model`, no `oscal-base-model`)
  - **Scoped PBT Approach**: deterministic bug; scope the property to the concrete failing cases plus a hypothesis sweep over `all_corpus_docs`
  - Create `tests/test_serialization_defaults.py` encoding isBugCondition / expected behavior from design:
    - Serialization clause: `path ∈ DefaultPaths AND NOT (by_alias=True AND exclude_none=True) AND (model has an alias-differing field set OR a None-valued field)`
    - Models × paths matrix: `Capability(uuid, name, description)` required-only, `Rlink` with/without `media_type`, `Resource` with `document-ids`, a corpus `Metadata`, a full `CatalogDocument`, an `OscalDocument`; paths `model_dump()`, `model_dump(mode="json")`, `model_dump_json()`, `pydantic_core.to_json(m)`, `to_json({"k": [m]})`, `TypeAdapter(dict[str, Any]).dump_python({"k": m}, mode="json")` with `by_alias` omitted and True
    - Assert recursively: no `None`/`null`, and every key ∈ `schemaPropertyNames` (all `properties` keys collected recursively from `schemas/1.2.3/oscal_complete_schema.json`, built once per module)
    - Corpus: for the 800-53 catalog, `json.loads(doc.model_dump_json()) == json.loads(serialize_oscal(doc))`
    - Construction clause: `Resource(uuid=U, document_ids=[DocumentId(identifier="x")])` and `Rlink(href=..., media_type=...)` succeed and equal their alias-keyed (`**{"document-ids": ...}`) counterparts
    - Builder clause (Property 4; 1.7, 2.13): `make_resource(document_ids=[])` and `make_resource(document_ids=["x"])` raise `pydantic.ValidationError`
  - Run on UNFIXED code: `hatch test tests/test_serialization_defaults.py > ./tmp/explore_before.log 2>&1; echo "EXIT: $?"`
  - **EXPECTED OUTCOME**: Test FAILS (this is correct - it proves the bug exists)
  - Document counterexamples in the task notes (e.g. `Capability(...).model_dump_json()` emits `"props":null` and `incorporates_components`; `to_json({"result": rlink})` emits `media_type` and `"hashes":null`; `Resource(document_ids=...)` raises `extra_forbidden`; `make_resource(document_ids=[])` returns a model instead of raising)
  - Mark task complete when the script is committed, before-state artifacts exist in `./tmp/`, and the test is written, run, and failing as documented
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 2.12, 2.13_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Validation, serialize_oscal, and public surface unchanged
  - **IMPORTANT**: Follow observation-first methodology. Observe on the UNFIXED tree for inputs where isBugCondition is false, then assert those observations
  - Observe: name-keyed dict input is rejected with `extra_forbidden` (`OscalDocument.model_validate` with `back_matter`; `validate_element({"href": ..., "media_type": ...}, "rlink")`; nested `rlinks[0].media_type` under `resource`). Name-keyed JSON is not rejected as planned: `parse_oscal` drops the key, so `back_matter` is accepted as `None` and `oscal_version` fails as `missing` at `oscal-version` (design Root Cause 6; bugfix 3.3(b))
  - _Corrected after completion: the JSON-mode bullets below describe the original plan. As implemented, and per the corrected 3.3(b), JSON entry points assert "value never kept" (`extra_forbidden` at the name, or `missing` at the alias for a required field, or accepted with the field `None` for an optional one), and `validate_oscal` agrees with the parse functions on accept/reject. Dict-mode assertions are strict `extra_forbidden`, as planned._
  - Observe: `get_supported_element_types()` equals `./tmp/element_types_before.txt`
  - Commit the pre-fix element-type list as a test snapshot (e.g. `tests/support/element_types_snapshot.txt`); add a test asserting set equality and `"oscal-base-model"` absence
  - Create `tests/test_prop_serialization_preservation.py` (uses the `ci` Hypothesis profile, ≥100 examples):
    - Name-keyed-at-depth rejection (Property 2; behavioral tripwire for the `__pydantic_base_init__` marker, complementing the structural tripwire in task 4.3): pick a corpus doc via `st.data()`, pick a random alias-differing key at a random depth (record the JSON path, the owning model class, and the Python name), rename it to its Python field name, and assert the rejection is specifically the renamed key being forbidden, not "some error":
      - `parse_oscal(str)`, `parse_oscal(bytes)`, `parse_oscal_file` (via `tmp_path`), and the matching typed `parse_*`: raise `OscalParseError` whose `.errors` contains an entry with `type == "extra_forbidden"` and `loc` ending in the Python name
      - `validate_oscal`: returns `False` (its contract is a bool; the error type is pinned by the `model_validate_json` assertion on the same bytes)
      - `OscalDocument.model_validate_json(bytes)`, `OscalDocument.model_validate(dict)`, the wrapper's `*Document.model_validate(dict)`, and the owning model class's `model_validate(subtree)` / `model_validate_json(json.dumps(subtree))` called directly: raise `pydantic.ValidationError` with an `extra_forbidden` entry at that key. Direct calls are required because `model_validate*` is exactly the path the marker protects
      - `validate_element` on allow-listed leaf types and a nested `resource.rlinks[i]`: `valid is False` and the errors contain `extra_forbidden` for the renamed key
      - Failure messages name the JSON path and Python name, and point at design root cause 5 (`__pydantic_custom_init__`)
    - Unknown-key rejection unchanged (3.5)
    - `serialize_oscal(doc) == doc.model_dump_json(indent=2, by_alias=True, exclude_none=True)` for sampled corpus docs
    - Builders: `make_hash` / `make_rlink` / `make_resource` with valid args equal the alias-dict-constructed models built the pre-fix way
    - Attribute access by Python name and `OscalDoc` accessors return the same values for sampled corpus docs
  - Existing suites (corpus, mutation, round-trip, facade, builders, version-package, postprocess) are part of this baseline; do not change their validation assertions
  - Run on UNFIXED code: `hatch test > ./tmp/preserve_before.log 2>&1; echo "EXIT: $?"` (the task-1 test is expected to fail; everything else must pass)
  - **EXPECTED OUTCOME**: Preservation tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11_

- [x] 3. Fix default serialization and by-name construction via `OscalBaseModel`

  - [x] 3.1 Add `src/oscal_bindings/v1/_base.py`
    - `OscalBaseModel(BaseModel)` with `model_config = ConfigDict(serialize_by_alias=True)`
    - Wrap `model_serializer` `_omit_none` that drops None values from dict output; no return annotation (comment why: `-> Any` collapses `model_json_schema(mode="serialization")`)
    - `__init__(self, /, **data)` mapping Python field-name kwargs to aliases via `functools.cache`'d `_kwarg_aliases(cls)`; leave the name in place if the alias is also passed, so `extra='forbid'` rejects it; exclude names that are also some field's alias
    - `__init__.__pydantic_base_init__ = True` with a comment explaining it keeps `model_validate*` from routing through `__init__`. Without it, name-keyed dict and JSON input would be accepted and populated at every depth (design Root Cause 5, variant B0)
    - Mechanism is Option B, re-verified before task 3 (design Root Causes 4–5). Do NOT add `validate_by_name` or `validate_by_alias` to `model_config`. Config-level `validate_by_name` makes name-keyed input valid for any call without per-call `by_name=False`, including direct `Model.model_validate`. Say so in a one-line comment next to `model_config`
    - Imports only `pydantic`, `functools`, `typing` (no import cycle with `models.py`)
    - The wrap serializer is final. Do not implement per-field `exclude_if`; it is recorded in DEVELOPING (task 3.7) as a documented fallback only
    - _Bug_Condition: isBugCondition(input) from design (default path without both kwargs, alias-differing or None-valued field present; or name-keyed constructor kwarg)_
    - _Expected_Behavior: alias keys only, no `null`, `json.loads(doc.model_dump_json()) == json.loads(serialize_oscal(doc))`; `by_alias=False` yields names without nulls; `exclude_none=False` is a no-op; name kwargs == alias kwargs_
    - _Preservation: name-keyed dict input rejected with `extra_forbidden` at every depth; name-keyed JSON never populated, with the pre-existing drop unchanged (3.3(b)); `serialize_oscal` byte-identical_
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.6, 2.7, 2.8, 2.9, 3.3, 3.4_

  - [x] 3.2 Wire the base through codegen and regenerate
    - Add `--base-class oscal_bindings.v1._base.OscalBaseModel` to the `generate` script in `pyproject.toml`
    - `hatch run generate > ./tmp/generate.log 2>&1; echo "EXIT: $?"`
    - Confirm the `models.py` diff is only the import block plus `(BaseModel)` → `(OscalBaseModel)` on 183 classes; `OscalDocument` and `Mappings` stay `RootModel[...]`; post-processor unchanged
    - _Bug_Condition: isBugCondition(input) from design_
    - _Expected_Behavior: every object model inherits the base behavior_
    - _Preservation: `models.py` reproducible from `hatch run generate`, no hand edits (3.12)_
    - _Requirements: 2.1, 2.2, 3.10, 3.12_

  - [x] 3.3 Exclude the base from element types
    - In `v1/extensions/validate_element.py` `_build_element_map`, change the guard to `obj not in (BaseModel, OscalBaseModel)`; keep the `root-model` entry (do not switch to a `__module__` filter)
    - `validate_element` keeps calling `model_validate(element)` without extra kwargs. Under Option B, dict-mode name keys are rejected at every depth by default (design Root Cause 5), so per-call `by_alias` / `by_name` would be redundant
    - _Preservation: element-type set equals the committed snapshot_
    - _Requirements: 3.4, 3.7_

  - [x] 3.4 Simplify builders
    - `make_rlink` → `Rlink(href=href, media_type=media_type, hashes=hashes)`
    - `make_resource` → single `Resource(uuid=..., title=..., description=..., rlinks=..., document_ids=document_ids)`; drop the post-construction assignment and its comment
    - `document_ids` is now validated at construction (fixes 1.7). Update the `make_resource` docstring to say invalid `document_ids` raise `ValidationError`
    - Add tests in `tests/test_builders.py`: `make_resource(document_ids=[])` raises `pydantic.ValidationError`; `make_resource(document_ids=["x"])` and a list mixing a `DocumentId` with a non-`DocumentId` item raise `pydantic.ValidationError`; a valid non-empty `list[DocumentId]` yields a model equal to the pre-fix result
    - Signatures unchanged
    - _Expected_Behavior: name kwargs construct equal models (2.9); invalid `document_ids` raise `ValidationError` (2.13, Property 4)_
    - _Preservation: equal models for valid arguments; documented `ValidationError` contract (3.8)_
    - _Requirements: 1.6, 1.7, 2.9, 2.13, 3.8_

  - [x] 3.5 Update `parser.py` docstring only
    - Keep the explicit `by_alias=True, exclude_none=True` in `serialize_oscal`; note that default `model_dump_json()` now yields equivalent output
    - Do not add per-call `by_alias=True, by_name=False` to parse/validate functions. Under Option B the config has no `validate_by_name`, so it's already the effective setting. In JSON mode it still gives the silent drop, so it would suggest protection that isn't there (design Root Causes 4 and 6, Fix Implementation §8)
    - Don't change parse-function behavior or docstrings about name-keyed input; the JSON-mode drop stays as is (3.3(b)) and is documented in README (task 3.7)
    - _Preservation: `serialize_oscal` byte-identical (3.1); parse accept/reject and values unchanged, including the drop (3.2, 3.3)_
    - _Requirements: 3.1, 3.2, 3.3_

  - [x] 3.6 Raise the pydantic floor and add test-only schema deps
    - `pyproject.toml`: `dependencies = ["pydantic[email]>=2.11"]`
    - Add `jsonschema` and `regex` to `[tool.hatch.envs.hatch-test].extra-dependencies`
    - `hatch run lock > ./tmp/lock.log 2>&1; echo "EXIT: $?"`; review the lockfile diff (expected: `>=2.11` header lines, new `jsonschema`/`regex` and transitive pins in both `hatch-test` lockfiles; pydantic stays 2.13.5); flag any unusual package names
    - `hatch run security > ./tmp/security.log 2>&1; echo "EXIT: $?"`
    - One-off floor check through hatch (never commit it; not added to CI):
      - Temporarily append to `pyproject.toml` an unlocked env: `[tool.hatch.envs.floor]` with `type = "virtual"`, `python = "3.12"`, `dependencies = ["pydantic[email]==2.11.0", "pytest", "hypothesis", "jsonschema", "regex"]`, and `[tool.hatch.envs.floor.scripts] check = "pytest tests/test_serialization_defaults.py tests/test_parser.py tests/test_prop_serialization_preservation.py tests/test_base_model.py"`. Include `test_base_model.py` only if task 4.3 has landed. The preservation module confirms 3.3 holds at the floor, and its JSON assertions accept either the 2.13 drop or `extra_forbidden`. `type = "virtual"` keeps it out of the pip-compile lock flow, and the `lock` script names envs explicitly, so no lockfile changes
      - Confirm the pin took: write `./tmp/pydantic_version.py` (prints `pydantic.VERSION`) and run `hatch run floor:python ./tmp/pydantic_version.py` (expect `2.11.0`)
      - `hatch run floor:check > ./tmp/floor.log 2>&1; echo "EXIT: $?"`; report the result
      - Also record, for #6, whether 2.11.0 drops or rejects name-keyed JSON. Write `./tmp/json_drop_floor.py` (`Rlink.model_validate_json('{"href":"x","media_type":"t"}')`, print the outcome) and run `hatch run floor:python ./tmp/json_drop_floor.py`. Result: 2.11.0 rejects with `extra_forbidden` (2.13.5 drops; 2.12.x untested). The floor check passed 145/145 on 2.11.0
      - Clean up: `hatch env remove floor`, revert the `pyproject.toml` addition, and confirm `git diff pyproject.toml` shows only the intended floor and test-dep changes before the task-3 commit
      - If the temporary env can't be made to work, stop and report; record it as a manual step (same commands) in the PR description rather than falling back to uv/pip or a bare interpreter
    - _Requirements: 2.10, 3.12_

  - [x] 3.7 Update documentation
    - README **Serialization**: aliases on and None omitted by default on all paths (`model_dump*`, `to_json`, `TypeAdapter`); `serialize_oscal` still recommended for documents; opt-outs: `by_alias=False` emits names, `exclude_none=False` is a no-op (OSCAL forbids `null`; use attribute access or `model_fields_set` to detect unset fields); name-keyed policy:
      - Constructor kwargs accept names or aliases; plain dicts nested in kwargs are alias-only
      - Dict input (`model_validate`, `validate_element`) rejects name keys at every depth
      - JSON input never populates a field from a name key
      - A "Known issue" note: on recent pydantic (observed on 2.13.x) a name-keyed JSON key is silently dropped rather than rejected; 2.11.0 rejects it with `extra_forbidden`. Link [#6](https://github.com/cairn-proofs/oscal-bindings-python/issues/6)

      **Requirements**: Pydantic ≥2.11. Drop back-matter alias caveats
    - DEVELOPING: `--base-class` in Code Generation Pipeline. Key Design Decisions entry "Valid OSCAL by default":
      - wrap serializer chosen; `exclude_if` measured as a fallback only, not implemented, and would raise the pydantic floor to 2.12
      - `__pydantic_base_init__` rationale (Option B, with the B0 leak evidence)
      - why config `validate_by_name` + per-call `by_alias=True, by_name=False` (Option A) was rejected: alias-only becomes opt-in per call, nested dicts in constructor kwargs would accept names, and JSON mode only drops (design Root Cause 4)
      - the JSON-mode drop as a known upstream behavior (design Root Cause 6; pydantic#13275)

      Benchmark table placeholder filled in task 5
    - AGENTS.md: replace the "Models forbid extras and don't populate-by-name" gotcha with the new policy. Include "don't add `validate_by_name` to the base config" and the JSON-mode drop. Add `_base.py` to the directory map; note `--base-class` in the codegen pipeline
    - `.agents/summary`: `data_models.md` populate-by-name row, `dependencies.md` floor + test deps, `architecture.md` builders paragraph and base-class layer, `components.md` `_base.py` and `_build_element_map`
    - Update comments in `tests/strategies.py` and `tests/test_prop_builders.py` that describe the old workaround (comments only, no assertion changes)
    - _Requirements: 2.8, 2.11_

  - [x] 3.8 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Default serialization paths emit valid OSCAL; name kwargs accepted
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - `hatch test tests/test_serialization_defaults.py > ./tmp/explore_after.log 2>&1; echo "EXIT: $?"`
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.9, 2.13_

  - [x] 3.9 Verify preservation tests still pass
    - **Property 2: Preservation** - Validation, serialize_oscal, and public surface unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - `hatch test > ./tmp/preserve_after.log 2>&1; echo "EXIT: $?"`
    - Re-run `./tmp/serialize_digests.py --out ./tmp/serialize_digests_after.json` and diff against `serialize_digests_before.json`: every corpus doc identical at both indent settings
    - Re-run `./tmp/element_types.py` and diff against `element_types_before.txt`: identical
    - **EXPECTED OUTCOME**: Tests PASS and both diffs are empty (confirms no regressions)
    - _Requirements: 3.1–3.11_

  - [x] 3.10 Commit the fix and docs (checkpoint)
    - Only after 3.8 and 3.9 pass and the full suite is green on 3.11 and 3.12 (`hatch test --all > ./tmp/commit3.log 2>&1; echo "EXIT: $?"`)
    - Stage by name only files created or modified for this feature: `src/oscal_bindings/v1/_base.py`, `src/oscal_bindings/v1/models.py` (regenerated), `validate_element.py`, `builders.py`, `parser.py`, `pyproject.toml`, the re-locked `requirements.txt` / `requirements/*.txt`, the task 1–3 test files and snapshot, README/DEVELOPING/AGENTS.md, the touched `.agents/summary/*.md`, the comment-only test edits, and `tasks.md`. Never stage `.github/dependabot.yml`, `.kiro/steering/*`, `./tmp/`, `htmlcov/`, or `.coverage`. Check `git status` before committing
    - Message includes `#5` and test status (e.g. "Default to valid OSCAL serialization via OscalBaseModel (#5). Tested: hatch test passes; serialize_oscal digests and element types unchanged; floor check on pydantic 2.11.0 <result>")
    - Never push

- [x] 4. Add fix-checking and property tests
  - [x] 4.1 Opt-out and construction unit tests in `tests/test_serialization_defaults.py`
    - `by_alias=False` gives Python names at depth with no `null`; `exclude_none=False` output equals default output; `include`/`exclude`/`exclude_unset` still honored
    - Construction smoke cases on `Rlink` / `Resource`: name kwargs, alias kwargs, mixed, unknown kwarg → `ValidationError` (`extra_forbidden`). Exhaustive construction, both-name-and-alias, and nested-dict rejection live in 4.3
    - `Rlink.model_json_schema(mode="serialization")` still lists `href`, `media-type`, `hashes`
    - Structure (3.12): every `BaseModel` subclass in `models.py` other than `OscalDocument`/`Mappings` is an `OscalBaseModel` subclass; `models.py` has no `(BaseModel)` class header
    - Framework-shaped calls: `pydantic_core.to_json([doc])`, `TypeAdapter(dict[str, Any]).dump_python({"result": doc}, mode="json", by_alias=True)`, argument-less `model_dump_json()`; re-parse with `parse_oscal` and compare to `serialize_oscal`
    - _Requirements: 2.3, 2.4, 2.8, 2.9, 3.12_

  - [x] 4.2 Write property test for default-path serialization
    - **Property 1: Bug Condition** - Default serialization paths emit valid OSCAL (fix checking)
    - `tests/test_prop_serialization_defaults.py`: from `all_corpus_docs` via `st.data()`, default `model_dump_json()` equals `serialize_oscal` semantically, `to_json` agrees, no nulls or non-schema keys
    - Using leaf strategies in `tests/strategies.py`, randomly set optional fields to None or values; assert the same invariants across all default paths
    - `ci` Hypothesis profile (≥100 examples)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.7_

  - [x] 4.3 Write keyword-construction tests and `OscalBaseModel` tripwires
    - **Property 3: Bug Condition** - Keyword construction accepts field names
    - Permanent tests in `tests/test_base_model.py` (exhaustive, parametrized) and `tests/test_prop_base_model.py` (Hypothesis, `ci` profile). No one-off scripts. Every assertion message names the class/field and points at the design root cause it guards: 5 for the marker, 4 for config
    - Shared fixtures (module scope): `OBJECT_MODELS` = every class in `v1.models` that subclasses `OscalBaseModel` (excluding `OscalBaseModel` itself); `ALIAS_FIELDS` = every `(cls, name, alias)` from `cls.model_fields` with `alias not in (None, name)`. Assert both are non-empty and `len(OBJECT_MODELS) == 184` (183 direct `OscalBaseModel` subclasses plus `ExternalId1`, an indirect subclass) so the parametrization can't silently go vacuous. `INSTANCES` = one valid instance per class harvested by walking every parsed NIST/AWS corpus doc, topped up from the leaf strategies in `tests/strategies.py`
    - (a) Marker tripwire, structural:
      - `getattr(OscalBaseModel.__init__, "__pydantic_base_init__", False) is True`
      - For every class in `OBJECT_MODELS` plus `OscalBaseModel`: `cls.__pydantic_custom_init__ is False`, and `"__init__" not in cls.__dict__` for generated classes
      - Behavioral canary, dict mode: `Rlink.model_validate({"href": "x", "media_type": "t"})`, a nested `Resource.model_validate({..., "rlinks": [{"href": "x", "media_type": "t"}]})`, and an `OscalDocument.model_validate` of a minimal catalog with `back-matter.resources[0].rlinks[0].media_type` all raise `ValidationError` with `extra_forbidden` at the name key (full `loc`). Each is called twice, with no kwargs and with `by_alias=True, by_name=False`
      - Behavioral canary, JSON mode: the same three inputs via `model_validate_json` never keep the value. Either the result's `media_type is None` (2.13.5 drop), or `ValidationError` with `extra_forbidden` at the name key. Fail if `media_type == "t"`: that means validation now routes through `__init__` (variant B0) or by-name validation got enabled
      - Failure message: "pydantic no longer honors `__pydantic_base_init__`; model_validate* would route through OscalBaseModel.__init__ and accept name-keyed OSCAL input. See design.md, Hypothesized Root Cause 5."
    - (b) Config tripwire against a switch to Option A (design Root Cause 4):
      - For `OscalBaseModel` and every class in `OBJECT_MODELS`: `not cls.model_config.get("validate_by_name", False)`, `cls.model_config.get("validate_by_alias", True) is True`, and `not cls.model_config.get("populate_by_name", False)`
      - Failure message: "validate_by_name/populate_by_name is enabled on <cls>. That makes name-keyed OSCAL input valid for every model_validate* call without per-call by_name=False, including user calls (3.3/3.4). Construction by name comes from OscalBaseModel.__init__ instead. See design.md, Hypothesized Root Cause 4."
    - (c) Exhaustive construction, parametrized over every entry in `ALIAS_FIELDS` (not sampled):
      - Outcome equivalence, value-independent (covers every class even without a harvested instance): for a probe value `v` (the harvested value when available, else a sentinel), `cls(**{name: v})` and `cls(**{alias: v})` produce the same outcome: equal models, or `ValidationError`s with identical `(type, loc, msg)` lists, and never an `extra_forbidden` entry for `name`
      - Valid-value equality: for every class in `INSTANCES`, `cls(**by_name_kwargs(inst)) == cls(**by_alias_kwargs(inst)) == cls.model_validate(inst.model_dump(by_alias=True, exclude_none=True)) == inst`, with kwargs built from the attribute values of `inst.model_fields_set`. Assert `INSTANCES` covers every class that appears in `ALIAS_FIELDS`; any gap must be listed in an explicit, commented `UNCOVERED_CLASSES` constant (expected empty or near-empty), and the test fails if the constant lists a class that is now covered
      - Both name and alias of the same field: `cls(**{name: v, alias: v})` raises `ValidationError` with `extra_forbidden` at `(name,)`
      - Nested name-keyed dict in kwargs: for every harvested instance with a model-typed field whose nested model has an alias-differing field set, pass that nested value as `nested.model_dump(by_alias=False, exclude_none=True)` under the outer kwarg; assert `ValidationError` with `extra_forbidden` at the nested name key. Assert at least one case per nested class that has alias-differing fields
    - (d) Copy and pickle unchanged, for every instance in `INSTANCES` plus sampled corpus documents:
      - `pickle.loads(pickle.dumps(m)) == m`, `copy.copy(m) == m`, `copy.deepcopy(m) == m`, `m.model_copy() == m`, each preserving `model_fields_set`
      - `m.model_copy(update={name: v})` sets the attribute by Python name exactly as on the unfixed tree (observe the behavior first, then assert it)
      - None of these, nor `model_validate` / `model_validate_json`, call `OscalBaseModel.__init__`: monkeypatch it to raise and assert all of the above still succeed
    - Property 3 PBT (`tests/test_prop_base_model.py`): for a Hypothesis-drawn leaf model class and random valid field values, keyword-by-name == keyword-by-alias == `model_validate(alias dict)`; supplying both name and alias of a drawn field is rejected with `extra_forbidden`
    - _Requirements: 1.6, 2.9, 3.3, 3.4_

  - [x] 4.4 Corpus schema validation integration test
    - For every NIST and AWS corpus doc, validate `json.loads(doc.model_dump_json())` against `schemas/1.2.3/oscal_complete_schema.json` with a Draft-07 validator extended (`jsonschema.validators.extend`) so `pattern` uses the `regex` module (`\p{L}`/`\p{N}`); build the validator once per session
    - If runtime is too slow on the full corpus, switch to `jsonschema-rs`, re-lock, and record the choice in DEVELOPING.md
    - _Requirements: 2.5_

  - [x] 4.5 Run the new tests
    - `hatch test tests/test_serialization_defaults.py tests/test_prop_serialization_defaults.py tests/test_prop_serialization_preservation.py tests/test_base_model.py tests/test_prop_base_model.py tests/test_builders.py > ./tmp/fixcheck.log 2>&1; echo "EXIT: $?"`
    - **EXPECTED OUTCOME**: all pass
    - _Requirements: 2.1–2.9, 2.13, 3.3, 3.4_

  - [x] 4.6 Commit the fix-checking tests (checkpoint)
    - Only after 4.5 passes and `hatch test --all > ./tmp/commit4.log 2>&1; echo "EXIT: $?"` is green
    - Stage by name only the task-4 test files (`tests/test_serialization_defaults.py`, `tests/test_prop_serialization_defaults.py`, `tests/test_base_model.py`, `tests/test_prop_base_model.py`, the schema-validation test, any `tests/strategies.py` / `conftest.py` additions), any DEVELOPING.md note from 4.4, and `tasks.md`. Never stage `.github/dependabot.yml`, `.kiro/steering/*`, or `./tmp/`
    - Message includes `#5` and test status (e.g. "Add fix-checking and OscalBaseModel tripwire tests (#5). Tested: hatch test --all passes")
    - Never push

- [x] 5. Benchmark after the fix
  - `hatch run python scripts/bench_serialization.py > ./tmp/bench_after.log 2>&1; echo "EXIT: $?"`
  - Compare with `./tmp/bench_before.log`; record both tables (parse, serialize compact/indented, `model_dump_json`, `to_json`, versions) in DEVELOPING.md and note the accepted serialize-time regression and the documented `exclude_if` fallback (~1.35×, needs pydantic ≥2.12) for the PR description
  - _Requirements: 2.12_

- [x] 6. Checkpoint - Ensure all tests pass
  - `hatch run release > ./tmp/release.log 2>&1; echo "EXIT: $?"` (generate reproducibility, lint, typing incl. `_base.py` and name-kwarg `builders.py`, security, `hatch test --all --cover` on 3.11 + 3.12, docs)
  - Confirm `git diff --exit-code src/oscal_bindings/v1/models.py` is clean after the release run's `generate`
  - Inspect `./tmp/release.log` for failures; fix and re-run
  - Commit the task-5 benchmark tables (DEVELOPING.md), any fixes from the release run, and `tasks.md`, staged by name; never `.github/dependabot.yml` or `.kiro/steering/*`. Message includes `#5` and test status (e.g. "Record serialization benchmarks (#5). Tested: hatch run release passes"). Never push
  - _Requirements: 3.12_
