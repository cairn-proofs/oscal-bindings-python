# Review Notes

Audit of the generated documentation set in `.agents/summary/` for internal consistency and completeness. `check_consistency` and `check_completeness` were both enabled.

> **Scope:** the current layout — implementation under `src/oscal_bindings/v1/`, top level a pure re-export, the OSCAL schema supplied by the pinned spec artifact (no copy in the repo), every type name taken from the naming manifest of the pinned spec artifact.

## Consistency Check

Cross-document facts were verified against the source files (`v1/parser.py`, `v1/extensions/*.py`, `scripts/{spec_artifact,manifest,hoist_names,postprocess_models}.py`, `pyproject.toml`, `v1/__init__.py`, and the top-level re-export modules).

| Fact | Consistent across docs? | Notes |
|------|-------------------------|-------|
| 8 document types + wrappers | ✅ | Same set in codebase_info, architecture, components, interfaces, data_models, workflows, index |
| Parsers accept `str \| bytes` | ✅ | Stated identically in README, interfaces, workflows, index |
| `v1/models.py` is generated / do-not-edit | ✅ | Consistent everywhere; docs also flag that the top-level `models.py` is a hand-written alias module, not generated |
| Public API is re-export-only in `v1/__init__.py` | ✅ | Matches actual `__all__` (35 curated names) |
| Top level is a pure re-export; `__all__` derived from `v1.__all__` | ✅ | codebase_info, architecture, components, interfaces, index agree; asserted by `tests/test_oscal_bindings.py` |
| Active schema release `1.2.3` / `__oscal_schema_version__` | ✅ | index, codebase_info, architecture, data_models, workflows, dependencies agree; tests assert it against the release of the pin and the artifact schema `$id` |
| Names come only from `names.json` (hoist + post-processor guards; no naming rule in the binding) | ✅ | architecture, workflows, interfaces, components, data_models, index agree |
| Exceptions `OscalParseError` (with `.errors`) / `OscalAccessError` | ✅ | Consistent; `validate_element` unknown-type also raises `OscalParseError` |
| `serialize_oscal` defaults (`indent=2`, `by_alias`, `exclude_none`) | ✅ | Matches source |
| Two `RootModel`s: `OscalDocument`, `MappingCollectionMappings` | ✅ | architecture, components, data_models, workflows agree |
| Single runtime dependency (Pydantic v2) | ✅ | dependencies.md matches `pyproject.toml` |

No contradictions found across the document set.

## Completeness Check

| Area | Coverage | Gap / Note |
|------|----------|-----------|
| Public API surface | Complete | All `__all__` symbols documented in interfaces.md |
| Parsing/serialization/validation | Complete | Behavior + error contract covered |
| `OscalDoc` facade incl. `assessment_period()` | Complete | Including nested-task walking and AP/AR-only constraint |
| Builders | Complete | Including `document_ids` validation at construction and the `media-type` alias |
| Element validation | Complete | `_ELEMENT_MAP` derivation explained |
| Code generation + post-processing | Complete | Manifest validation, the hoist and its guards, the post-processor steps and its three guards against the manifest, and the CLI contracts. The pipeline takes every name from the naming manifest (spec artifact `0.3.0+oscal.1.2.3`, package version 0.3.2); these docs describe that pipeline only |
| Version layout + import paths | Complete | Version package, top-level re-exports, alias modules, and the import-path guidance are covered in architecture.md, components.md, and interfaces.md |
| Schema refresh procedure | Complete | workflows.md §1c documents how to move the spec artifact pin and what a reviewer checks |
| Dependencies / toolchain / Python versions | Complete | Runtime, codegen, dev, build tooling all covered |
| Data models | Partial by design | Individual nested element models (hundreds in `v1/models.py`) are not enumerated field-by-field. This is intentional: they are generated from the schema and best inspected via the models file or NIST OSCAL schema docs. Shared/high-value elements are covered. |
| Tests | Summarized | Test files and grouping classes described; individual test cases not enumerated (not needed for navigation). |

### Language-support gaps
The `codebase-summary` process fully supports Python, which is the entire implementation language here. **No gaps arise from language-support limitations.** The OSCAL JSON Schema is code-generation *input*. It comes from the pinned spec artifact, not from this repo, and is treated structurally, not analyzed line-by-line.

## Recommendations

1. **Keep docs in sync with the schema/OSCAL version.** These docs cite OSCAL release 1.2.3. On a refresh, the release string appears in index.md, codebase_info.md, architecture.md, data_models.md, workflows.md, and dependencies.md — plus the pin in `scripts/spec_artifact.py` and `__oscal_schema_version__` in the source. Regenerate the summary when the schema is bumped or when the codegen pipeline (`--target-python-version`, generator version, spec artifact pin) changes.
2. **Treat `v1/models.py` field-level detail as reference, not documentation.** For questions about a specific nested element's fields, consult `v1/models.py` or the NIST schema directly rather than expanding these docs — enumerating every generated model would create high-maintenance, quickly-stale content.
3. **Watch the Pydantic major-version coupling.** dependencies.md flags this as the primary upgrade risk; a future Pydantic 3.x would likely require regeneration and extension changes.
4. **`AGENTS.md` Custom Instructions** is the right home for any repo-specific conventions discovered later (e.g. CI specifics, review norms); it is preserved across regenerations.
5. **The package name does not record the release.** `v1` is deliberately major-only, so these docs and `__oscal_schema_version__` are the only places a reader learns which OSCAL release the bindings cover. Treat a stale release string here as a correctness bug, not cosmetic drift.
6. **Prefer `oscal_bindings.v1` in examples.** The top-level paths are equivalent, but examples written against `v1` state which major version they target.

## Verification Method

Facts were checked against the actual source read during analysis (not inferred): `src/oscal_bindings/v1/{__init__,parser}.py`, `src/oscal_bindings/v1/extensions/{document,builders,validate_element,__init__}.py`, the top-level re-export modules `src/oscal_bindings/{__init__,models,parser}.py` and `src/oscal_bindings/extensions/__init__.py`, `scripts/{spec_artifact,pinned_archive,manifest,hoist_names,postprocess_models}.py`, `pyproject.toml`, `mise.toml`, `tests/test_oscal_bindings.py`, `tests/test_postprocess.py`, the schema `$id` of the artifact schema `oscal_complete_schema.json`, and the head of `v1/models.py`.
