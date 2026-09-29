# Workflows

## 1. Code Generation (build-time)

Triggered by `hatch run generate`. This is the only supported way to change `v1/models.py`.

```mermaid
flowchart TD
    A["hatch run generate"] --> B["datamodel-codegen<br/>--input schemas/1.2.3/oscal_complete_schema.json<br/>--output src/oscal_bindings/v1/models.py<br/>--collapse-root-models --use-annotated<br/>--field-constraints --reuse-model<br/>--target-python-version 3.11 --use-schema-description"]
    B --> C["raw v1/models.py<br/>(Model, Model1-8, OscalComplete* names,<br/>RootModel scalars, invalid patterns)"]
    C --> D["python scripts/postprocess_models.py<br/>--schema schemas/1.2.3/oscal_complete_schema.json<br/>--models src/oscal_bindings/v1/models.py"]
    D --> E["clean v1/models.py"]
    D -->|"guard trips"| F["non-zero exit,<br/>file NOT written"]
```

Both paths are passed explicitly. Each argument also carries its own independent default (`DEFAULT_MODELS_PATH`, `DEFAULT_SCHEMA_PATH` built from `ACTIVE_SCHEMA_RELEASE`), so a bare or one-argument invocation resolves correctly. A missing path exits non-zero naming it.

`postprocess_models.py` runs these phases in order (`main()`):

1. **`collapse_scalar_root_models`** — scalar `RootModel[...]` classes → `TypeAlias`; unions and `PRESERVE_AS_ROOTMODEL = {Model, Mappings}` kept as `RootModel`.
2. **`ensure_annotated_import`** — guarantees `Annotated` is imported.
3. **`fix_email_str_patterns`** / **`fix_non_string_patterns`** — strip `pattern=` constraints from `EmailStr`, `AwareDatetime`, `AnyUrl`, and numeric fields (regex patterns are invalid there).
4. **`derive_document_renames` + guards + `rename_classes`** — derive the wrapper rename map from the generated source's own content (see below), check it against the schema's document-type count, then apply it longest-key-first.
5. **`rename_root_model`** — standalone `Model` → `OscalDocument` (carefully avoiding `BaseModel`/`RootModel`/`ConfigDict`).
6. **`rename_classes(VARIANT_RENAMES)`** — merge/group numbered variants → descriptive names.
7. **`build_namespace_renames(schema_path)` + `rename_classes`** — strip `OscalComplete...` prefixes using schema definitions; apply `COLLISION_OVERRIDES`; handle numbered variants; sort by length desc to avoid partial replacements.
8. **Cleanup** — drop unused `RootModel` import; collapse 4+ blank lines.
9. **`find_duplicate_class_definitions` → `report_collisions`** — final gate: any name defined twice in the fully renamed source is an uncovered collision; report *all* of them and exit non-zero without writing.

Idempotent: re-running produces the same output for the same schema.

### 1a. Wrapper-name derivation and guards

```mermaid
flowchart TD
    A["iter_class_blocks(content)"] --> B{"class has the<br/>$schema field?"}
    B -->|no| A
    B -->|yes| C{"body fields<br/>besides $schema"}
    C -->|">1"| D["raise AmbiguousWrapperError<br/>→ report FIRST offender, exit 1<br/>(remaining candidates unscanned)"]
    C -->|"0"| E["union root (Model) — skip, not an error"]
    C -->|"1"| F["renames[class] = PascalCase(body_field) + 'Document'"]
    F --> G{"len(renames) ==<br/>len(schema['oneOf'])?"}
    G -->|no| H["report_wrapper_count_mismatch(both counts), exit 1"]
    G -->|"yes / no oneOf"| I["apply renames"]
```

Names track content, not position: reordering the schema's document types reorders the generated ordinals but not the derived names. Ambiguity fails **fast** (the scan's own premise is void); collisions **accumulate** (each is an independent finding a maintainer wants in one report).

## 1b. Refreshing to a new OSCAL release

Bundles are vendored one directory per release under `schemas/<release>/`, retaining the NIST filenames. `schemas/1.2.2/` and `schemas/1.2.3/` are both present; the *active* one is whichever path is passed — there is no glob and no "newest wins", so adding a bundle directory changes nothing on its own.

1. Add the new release's schema set under `schemas/<release>/`.
2. Point the Active_Schema_Bundle at it: the `--input`/`--schema` paths in the `generate` script, and `ACTIVE_SCHEMA_RELEASE` in `scripts/postprocess_models.py`.
3. Update `__oscal_schema_version__` in `src/oscal_bindings/v1/__init__.py` to the new release (a test asserts it against the bundle's schema `$id`).
4. Run `hatch run generate` and review the `v1/models.py` diff as schema-driven change only.
5. Add any newly surfaced collisions to `COLLISION_OVERRIDES` deliberately, guided by the collision report.
6. Run the suite. Within OSCAL 1.x the package name does **not** change — the refresh regenerates `v1` in place.

## 2. Parsing a Document (runtime)

```mermaid
flowchart TD
    A["parse_oscal(data: str | bytes)"] --> B["OscalDocument.model_validate_json(data)"]
    B -->|ValidationError| C["raise OscalParseError(.errors = pydantic errors)"]
    B -->|ValueError / bad UTF-8| D["raise OscalParseError('Invalid JSON: ...')"]
    B -->|ok| E["OscalDocument"]
    E --> F{"typed parser?"}
    F -->|"parse_catalog etc."| G["hasattr(doc.root, 'catalog')?"]
    G -->|yes| H["return doc.root (CatalogDocument)"]
    G -->|no| I["raise OscalParseError('Document is not a Catalog')"]
    F -->|no| E
```

`parse_oscal_file` reads the file as **bytes** (`read_bytes()`) and delegates to `parse_oscal`, so file parsing skips a decode step. A missing file raises `FileNotFoundError` before parsing.

## 3. Uniform Access via `OscalDoc`

```mermaid
flowchart TD
    A["OscalDoc.from_file / from_json / OscalDoc(wrapper)"] --> B{"isinstance OscalDocument?"}
    B -->|yes| C["unwrap .root"]
    B -->|no| D["use wrapper as-is"]
    C --> E{"is a known wrapper type?"}
    D --> E
    E -->|no| F["raise TypeError"]
    E -->|yes| G["store _wrapper"]
    G --> H[".body → getattr(wrapper, _WRAPPER_TO_BODY_ATTR[type])"]
    H --> I[".metadata / .oscal_version / .uuid"]
```

### `assessment_period()` sub-workflow

```mermaid
flowchart TD
    A["doc.assessment_period()"] --> B{"body type?"}
    B -->|AssessmentPlan| C["walk tasks[] (recursively into tasks[].tasks[])"]
    C --> D["on-date → add date to starts+ends<br/>within-date-range → add start & end<br/>at-frequency → contributes nothing"]
    B -->|AssessmentResults| E["results[].start → starts<br/>results[].end (if set) → ends"]
    B -->|other| F["raise OscalAccessError"]
    D --> G["return (min starts | None, max ends | None)"]
    E --> G
```

## 4. Building back-matter resources

```mermaid
sequenceDiagram
    participant C as Caller
    participant R as make_resource
    participant L as make_rlink
    participant H as make_hash
    C->>H: make_hash(digest)          %% default Algorithm.SHA_256
    H-->>C: Hash
    C->>L: make_rlink(href, media_type=, hashes=[Hash])
    L->>L: Rlink.model_validate({"href":..,"media-type":..,"hashes":..})
    L-->>C: Rlink
    C->>R: make_resource(title=, description=, rlinks=[Rlink])
    R->>R: uuid = uuid4() if not provided
    R->>R: if document_ids: set post-construction
    R-->>C: Resource (validated)
```

## 5. Element-level Validation

```mermaid
flowchart TD
    A["validate_element(element, 'observation')"] --> B{"element_type in _ELEMENT_MAP?"}
    B -->|no| C["raise OscalParseError('Unknown element type')"]
    B -->|yes| D["model_class.model_validate(element)"]
    D -->|ok| E["ElementValidationResult(valid=True)"]
    D -->|PydanticValidationError| F["ElementValidationResult(valid=False,<br/>errors=[ValidationError(path, message)])"]
```

`_ELEMENT_MAP` is built once at import time by introspecting `oscal_bindings.v1.models`.

## 6. Developer / Release Workflow

From `DEVELOPING.md` and `pyproject.toml` hatch scripts:

```mermaid
flowchart LR
    G["hatch run generate"] --> T["hatch test --all --cover<br/>(py3.11 + py3.12, parallel)"]
    T --> D["hatch run docs (pdoc → build/api-docs)"]
    G -.-> R["hatch run release = generate + test --all --cover + docs"]
    T -.-> R
    D -.-> R
```

- `hatch run typing` → mypy over `src/oscal_bindings` (which includes `v1`).
- `hatch run docs` → `pdoc oscal_bindings oscal_bindings.v1 -o build/api-docs` — both the top-level package and the version package are documented.
- Coverage `source_pkgs = ["oscal_bindings"]`, which reaches `v1` as a subpackage.
- The wheel packages `src/oscal_bindings`, so `v1` ships with it.
- Test artifacts: `htmlcov/` (HTML coverage, git-ignored), written only under `--cover`.
- Lockfiles (`requirements.txt`, `requirements/*.txt`) are regenerated by `hatch-pip-compile` whenever an env's declared deps change; deliberate upgrades use `PIP_COMPILE_UPGRADE=1` (see DEVELOPING.md "Locked Environments").

### Adding an extension (from `DEVELOPING.md`)
1. Add `v1/extensions/foo.py`.
2. Re-export public symbols from `v1/extensions/__init__.py`.
3. Re-export from `src/oscal_bindings/v1/__init__.py`.
4. Add tests under `tests/`.

Nothing to do at the top level: the top-level `__all__` is derived from `v1.__all__`, so a new name appears on the top-level path automatically. Neither `__init__.py` ever defines new symbols.
