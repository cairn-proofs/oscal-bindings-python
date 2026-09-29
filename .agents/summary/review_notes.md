# Review Notes

Audit of the generated documentation set in `.agents/summary/` for internal consistency and completeness. `check_consistency` and `check_completeness` were both enabled.

> **Revised for the `oscal_bindings.v1` move.** The original audit predates the major-version namespace change. Paths, the schema release, and the post-processor findings below have been updated to the current layout (implementation under `src/oscal_bindings/v1/`, top level a re-export shim, schema bundles under `schemas/<release>/`, wrapper names derived from content). The audit's *conclusions* were re-checked against the moved sources rather than carried over unread.

## Consistency Check

Cross-document facts were verified against the source files (`v1/parser.py`, `v1/extensions/*.py`, `scripts/postprocess_models.py`, `pyproject.toml`, `v1/__init__.py`, and the top-level shim modules).

| Fact | Consistent across docs? | Notes |
|------|-------------------------|-------|
| 8 document types + wrappers | ✅ | Same set in codebase_info, architecture, components, interfaces, data_models, workflows, index |
| Parsers accept `str \| bytes` | ✅ | Stated identically in README, interfaces, workflows, index |
| `v1/models.py` is generated / do-not-edit | ✅ | Consistent everywhere; docs also flag that the top-level `models.py` is a hand-written alias module, not generated |
| Public API is re-export-only in `v1/__init__.py` | ✅ | Matches actual `__all__` (35 curated names) |
| Top level is a pure shim; `__all__` derived from `v1.__all__` | ✅ | codebase_info, architecture, components, interfaces, index agree; asserted by `tests/test_oscal_bindings.py` |
| Active schema release `1.2.3` / `__oscal_schema_version__` | ✅ | index, codebase_info, architecture, data_models, workflows, dependencies agree; asserted against the bundle `$id` in tests |
| Wrapper names derived from content, not ordinals | ✅ | architecture, workflows, interfaces, components, data_models agree; the positional `DOCUMENT_RENAMES` dict no longer exists |
| Exceptions `OscalParseError` (with `.errors`) / `OscalAccessError` | ✅ | Consistent; `validate_element` unknown-type also raises `OscalParseError` |
| Collision handling | ✅ | Steering docs say "5 collisions"; `COLLISION_OVERRIDES` has 10 entries = 5 short-names × 2 namespaces. data_models.md lists all 10 rows and frames them as 5 collision pairs — consistent, no contradiction. |
| `serialize_oscal` defaults (`indent=2`, `by_alias`, `exclude_none`) | ✅ | Matches source |
| `PRESERVE_AS_ROOTMODEL = {Model, Mappings}` | ✅ | architecture, data_models, workflows agree |
| Single runtime dependency (Pydantic v2) | ✅ | dependencies.md matches `pyproject.toml` |

No contradictions found across the document set.

## Completeness Check

| Area | Coverage | Gap / Note |
|------|----------|-----------|
| Public API surface | Complete | All `__all__` symbols documented in interfaces.md |
| Parsing/serialization/validation | Complete | Behavior + error contract covered |
| `OscalDoc` facade incl. `assessment_period()` | Complete | Including nested-task walking and AP/AR-only constraint |
| Builders | Complete | Including the `document_ids` post-construction quirk and `media-type` alias |
| Element validation | Complete | `_ELEMENT_MAP` derivation explained |
| Code generation + post-processing | Complete | All 9 post-processor phases documented, plus the CLI contract, the content-based wrapper derivation, and the three guards (fail-fast ambiguity, count mismatch, accumulated collisions) |
| Version layout + back-compatibility | Complete | Version package, compat shim, alias modules, and the import-path guidance are covered in architecture.md, components.md, and interfaces.md |
| Schema refresh procedure | Complete | workflows.md §1b documents the release-versioned bundle layout and the refresh steps |
| Dependencies / toolchain / Python versions | Complete | Runtime, codegen, dev, build tooling all covered |
| Data models | Partial by design | Individual nested element models (hundreds in `v1/models.py`) are not enumerated field-by-field. This is intentional: they are generated from the schema and best inspected via the models file or NIST OSCAL schema docs. Shared/high-value elements are covered. |
| Tests | Summarized | Test files and grouping classes described; individual test cases not enumerated (not needed for navigation). |

### Language-support gaps
The `codebase-summary` process fully supports Python, which is the entire implementation language here. **No gaps arise from language-support limitations.** The only non-Python artifacts are the OSCAL JSON Schema files under `schemas/`, which are code-generation *input* and are intentionally treated structurally rather than analyzed line-by-line.

## Recommendations

1. **Keep docs in sync with the schema/OSCAL version.** These docs cite OSCAL release 1.2.3. On a refresh, the release string appears in index.md, codebase_info.md, architecture.md, data_models.md, workflows.md, and dependencies.md — plus `ACTIVE_SCHEMA_RELEASE` and `__oscal_schema_version__` in the source. Regenerate the summary when the schema is bumped or when the codegen pipeline (`--target-python-version`, generator version) changes, since class names can shift.
2. **Treat `v1/models.py` field-level detail as reference, not documentation.** For questions about a specific nested element's fields, consult `v1/models.py` or the NIST schema directly rather than expanding these docs — enumerating every generated model would create high-maintenance, quickly-stale content.
3. **Watch the Pydantic major-version coupling.** dependencies.md flags this as the primary upgrade risk; a future Pydantic 3.x would likely require regeneration and extension changes.
4. **`AGENTS.md` Custom Instructions** is the right home for any repo-specific conventions discovered later (e.g. CI specifics, review norms); it is preserved across regenerations.
5. **The package name no longer records the release.** `v1` is deliberately major-only, so these docs and `__oscal_schema_version__` are the only places a reader learns which OSCAL release the bindings cover. Treat a stale release string here as a correctness bug, not cosmetic drift.
6. **Prefer `oscal_bindings.v1` in examples.** The flat paths still work and will keep working, but examples written against `v1` document the intended long-term shape.

## Verification Method

Facts were checked against the actual source read during analysis (not inferred): `src/oscal_bindings/v1/{__init__,parser}.py`, `src/oscal_bindings/v1/extensions/{document,builders,validate_element,__init__}.py`, the top-level shim modules `src/oscal_bindings/{__init__,models,parser}.py` and `src/oscal_bindings/extensions/__init__.py`, `scripts/postprocess_models.py`, `pyproject.toml`, `mise.toml`, `tests/test_oscal_bindings.py`, `tests/test_postprocess.py`, the schema `$id` of `schemas/1.2.3/oscal_complete_schema.json`, and the head of `v1/models.py`.
