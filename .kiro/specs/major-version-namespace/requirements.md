# Requirements Document

## Introduction

This feature relocates the `oscal_bindings` public API into a major-version-scoped package, `oscal_bindings.v1`, and makes the code-generation pipeline schema-path-parameterized so that any OSCAL 1.x release can be regenerated in place without creating a new import namespace.

The motivating observation is that OSCAL is backward-compatible within a major version, so the compatibility boundary is the *major* version, not the minor. A namespace per minor release (`v1_2`, `v1_3`) would encode a break that does not exist and would force consumer import churn on every routine schema refresh. A namespace per major version matches both the real compatibility boundary and NIST's own schema `$id` structure, which scopes the namespace to `ns/oscal/1.0/` and carries the release (`1.2.2`) as a separate path element.

The feature also fixes a latent defect surfaced while designing the above: the post-processor maps generated wrapper classes to document names *positionally* (`Model1` → `CatalogDocument`, …), which silently produces wrong names if a schema revision reorders or adds document types.

Three things are explicitly **out of scope**: creating a `v2` package, building a version-dispatch registry, and relaxing `extra='forbid'`. All three are deferred until OSCAL 2.0 exists and the actual differences are knowable.

## Glossary

- **Version_Package**: The major-version-scoped subpackage `oscal_bindings.v1`, holding the generated models and the hand-written layer bound to them.
- **Compat_Shim**: The top-level `oscal_bindings/__init__.py`, reduced to pure re-exports from the Version_Package so existing consumer imports continue to resolve.
- **Public_Surface**: The set of names importable as `from oscal_bindings import <name>`, enumerated by the top-level `__all__`.
- **Schema_Bundle**: A vendored OSCAL JSON Schema set for one OSCAL release, stored under a release-versioned directory (e.g. `schemas/1.2.3/`).
- **Active_Schema_Bundle**: The single Schema_Bundle that the Version_Package is currently generated from.
- **Generate_Script**: The `generate` script under `[tool.hatch.envs.default.scripts]` in `pyproject.toml`, which runs `datamodel-codegen` followed by the Post_Processor.
- **Post_Processor**: `scripts/postprocess_models.py`, which collapses scalar RootModels, strips invalid patterns, and renames generated classes.
- **Document_Rename_Map**: The mapping from generated wrapper class names to their published names (`CatalogDocument`, `ProfileDocument`, …), currently the hardcoded positional `DOCUMENT_RENAMES` dict.
- **Wrapper_Class**: A generated class representing an OSCAL JSON document envelope — one `$schema` field plus exactly one body field named for the document root key.
- **Root_Key**: The single top-level OSCAL document key in a Wrapper_Class (e.g. `catalog`, `system-security-plan`).
- **Schema_Version_Constant**: A module-level constant on the Version_Package recording the exact OSCAL release of the Active_Schema_Bundle.
- **Hand_Written_Layer**: The non-generated modules that import from `models.py` — `parser.py`, `extensions/document.py`, `extensions/builders.py`, `extensions/validate_element.py`, and the `extensions/__init__.py` re-export module.
- **Test_Matrix**: The existing Hatch parallel test matrix running Python 3.11 and Python 3.12.
- **Decision_Record**: The "Major-version namespace" and "Strict models tie coverage to the vendored release" entries under Key Design Decisions in `DEVELOPING.md`, recording the multi-version binding decision. *(Originally a backlog entry; relocated to `DEVELOPING.md` when the backlog moved out of the repo.)*

## Requirements

### Requirement 1: Release-versioned schema vendoring

**User Story:** As a maintainer, I want vendored schemas organized by OSCAL release, so that the schema a binding set was generated from is unambiguous and a refresh is a visible, reviewable change.

#### Acceptance Criteria

1. THE Schema_Bundle SHALL store each vendored OSCAL schema set under a directory named for its OSCAL release version.
2. THE Schema_Bundle SHALL retain the existing schema filenames unchanged within its release directory.
3. THE Generate_Script SHALL read from exactly one Active_Schema_Bundle per invocation.
4. THE Generate_Script SHALL select the Active_Schema_Bundle by an explicitly supplied path, independent of directory ordering and independent of how many Schema_Bundles are present in the repository.

### Requirement 2: Parameterized code generation

**User Story:** As a maintainer, I want the codegen pipeline to take schema and output paths as parameters, so that regenerating from a different schema release does not require editing the script body.

#### Acceptance Criteria

1. THE Post_Processor SHALL accept the path to the generated models file as a command-line argument.
2. THE Post_Processor SHALL accept the path to the source schema file as a command-line argument.
3. WHERE a path argument is omitted, THE Post_Processor SHALL fall back to that argument's default — the Active_Schema_Bundle schema path or the Version_Package models path — resolving each omitted argument independently of whether the other path argument is supplied.
4. IF a supplied schema or models path does not exist, THEN THE Post_Processor SHALL exit with a non-zero status and report the missing path.
5. THE Generate_Script SHALL pass the Active_Schema_Bundle path and the Version_Package models path explicitly to both `datamodel-codegen` and the Post_Processor.

### Requirement 3: Schema-derived document rename map

**User Story:** As a maintainer, I want wrapper classes mapped to document names by inspecting their content rather than their position, so that a schema revision that adds or reorders document types cannot silently produce wrong class names.

#### Acceptance Criteria

1. THE Post_Processor SHALL derive the Document_Rename_Map by identifying each Wrapper_Class's Root_Key from the generated model source.
2. THE Post_Processor SHALL determine a Wrapper_Class's Root_Key as its single body field, excluding the `$schema` directive field.
3. THE Post_Processor SHALL derive each published wrapper name from its Root_Key converted to PascalCase with a `Document` suffix.
4. THE Post_Processor SHALL NOT rely on the ordinal suffix of generated wrapper class names to assign document names.
5. IF a candidate Wrapper_Class has more than one body field besides the `$schema` directive, THEN THE Post_Processor SHALL report that first ambiguous class and exit with a non-zero status immediately, leaving the remaining candidate Wrapper_Classes unscanned.
6. IF the number of derived Wrapper_Classes differs from the number of document types in the Active_Schema_Bundle, THEN THE Post_Processor SHALL exit with a non-zero status and report both counts.
7. WHEN the Post_Processor runs against the Active_Schema_Bundle, THE Document_Rename_Map SHALL produce the same eight published wrapper names that the current positional map produces.

### Requirement 4: Major-version package layout

**User Story:** As a consumer, I want the bindings to live under a major-version namespace, so that routine OSCAL minor and patch refreshes never change my import paths.

#### Acceptance Criteria

1. THE Version_Package SHALL contain the generated models module.
2. THE Version_Package SHALL contain the Hand_Written_Layer.
3. THE Version_Package SHALL be named for the OSCAL major version it targets, without minor or patch components.
4. THE Version_Package SHALL expose the same Public_Surface names as the pre-move top-level package.
5. THE Version_Package SHALL be included in the built wheel.
6. WHEN the Active_Schema_Bundle is updated to a different OSCAL 1.x release, THE Version_Package name SHALL remain unchanged.

### Requirement 5: Non-breaking top-level compatibility

**User Story:** As an existing consumer, I want my current imports to keep working after the move, so that adopting the new layout requires no changes on my side.

#### Acceptance Criteria

1. THE Compat_Shim SHALL re-export every name in the pre-move Public_Surface.
2. THE Compat_Shim SHALL define no symbols of its own.
3. WHEN a consumer imports a name from `oscal_bindings`, THE Compat_Shim SHALL resolve it to the identical object exposed by the Version_Package.
4. THE Compat_Shim SHALL preserve the pre-move behavior of importing generated model names directly from `oscal_bindings`.
5. THE Compat_Shim SHALL continue to resolve the pre-move `oscal_bindings.models`, `oscal_bindings.parser`, and `oscal_bindings.extensions` module paths.
6. WHERE a consumer holds a class obtained via the Compat_Shim, THE Version_Package SHALL report that class as the same type object obtained by importing it directly.

### Requirement 6: Schema version introspection

**User Story:** As a consumer, I want to read which OSCAL release my bindings were generated from, so that I can reason about coverage without inspecting the package internals.

#### Acceptance Criteria

1. THE Version_Package SHALL expose a Schema_Version_Constant recording the full OSCAL release version of the Active_Schema_Bundle.
2. THE Schema_Version_Constant SHALL be a string containing major, minor, and patch components.
3. THE Schema_Version_Constant SHALL match the release version encoded in the Active_Schema_Bundle's schema `$id`.
4. THE Compat_Shim SHALL re-export the Schema_Version_Constant.

### Requirement 7: Schema refresh to the current OSCAL release

**User Story:** As a consumer, I want the bindings generated from the current OSCAL 1.x release, so that documents from up-to-date producers parse.

#### Acceptance Criteria

1. THE Active_Schema_Bundle SHALL be the most recent OSCAL 1.x release available at implementation time.
2. WHEN the Version_Package is regenerated from the refreshed Active_Schema_Bundle, THE Public_Surface SHALL retain all eight wrapper names.
3. IF the refreshed Active_Schema_Bundle introduces class-name collisions not covered by the Post_Processor's existing overrides, THEN THE Post_Processor SHALL complete processing of all Wrapper_Classes, accumulate every uncovered collision, and exit with a non-zero status reporting all accumulated collisions, rather than emit duplicate class definitions.
4. WHEN the refresh completes, THE Schema_Version_Constant SHALL report the refreshed release version.

### Requirement 8: Documentation and decision record

**User Story:** As a maintainer, I want the layout decision and its rationale recorded, so that the next person does not re-litigate it or reach for minor-version namespacing.

#### Acceptance Criteria

1. THE Decision_Record SHALL state that binding namespaces are scoped to the OSCAL major version.
2. THE Decision_Record SHALL state that a minor-version namespace was considered and rejected, with the compatibility-boundary reasoning.
3. THE Decision_Record SHALL identify the arrival of OSCAL 2.0 as the trigger for adding a second Version_Package.
4. THE Decision_Record SHALL record that `extra='forbid'` makes major-version coverage contingent on tracking the current release, and SHALL name the Schema_Version_Constant as the introspection mechanism.
5. THE project documentation SHALL replace claims of single-version bindings with the major-version-namespace description, in the developer guide, the agent navigation guide, and the user-facing readme.
6. THE project documentation SHALL document the schema refresh procedure against the release-versioned Schema_Bundle layout.

### Requirement 9: Test and tooling compatibility

**User Story:** As a maintainer, I want the existing checks to pass unchanged in substance after the move, so that the relocation is verifiably behavior-preserving.

#### Acceptance Criteria

1. THE existing test suite SHALL pass on both Python 3.11 and Python 3.12 cells of the Test_Matrix after the move.
2. THE test suite SHALL include coverage asserting that pre-move import paths still resolve.
3. THE type-checking script SHALL cover the Version_Package.
4. THE coverage configuration SHALL report on the Version_Package.
5. THE documentation build SHALL produce API documentation for the Version_Package.

### Requirement 10: Scope guardrails

**User Story:** As a maintainer, I want the speculative parts of multi-version support left undone, so that we do not carry abstraction weight for a second major version that does not exist yet.

#### Acceptance Criteria

1. THE feature SHALL NOT introduce a second Version_Package.
2. THE feature SHALL NOT introduce a version-dispatch registry or a version-sniffing pre-parse.
3. THE feature SHALL NOT change the `extra='forbid'` model configuration.
4. THE feature SHALL NOT alter the runtime dependency set.
5. THE feature SHALL NOT introduce a shared abstraction layer between Version_Packages.
