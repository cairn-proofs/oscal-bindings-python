# Design

## Context

See [proposal.md - Why](proposal.md#why) for the motivation. The facts below constrain the approach.

1. Codegen emits the document union as `class Model(RootModel[CatalogDocument | ...])` with a plain union `root`
   field. `rename_document_union` in `scripts/postprocess_models.py` finds that class by its union of the manifest
   members and renames it to `OscalDocument`.
2. The post-processor writes text. It does not run black after its own edits, so each emitted line must already have
   the committed format (see `_alias_text` and `LINE_LENGTH`).
3. Guard 2 rejects each module-level assignment that is not a scalar alias. A module-level dict in `models.py`, such
   as a root-key map, fails guard 2. The guards do not check module-level functions. But the convention is that
   `models.py` is a pure generate and post-process output, with no hand-written logic.
4. Each `document` entry of the manifest has a `body-field` (for example `component-definition`). This is the root key
   of the document type.
5. The YAML loader (`extensions/_yaml_loader.py`) resolves its walk against `OscalDocument.model_json_schema()`. Its
   `branches` method reads both `anyOf` and `oneOf` at the root.
6. Some tests match an error location as a subsequence that contains the member class name (for example
   `_has_error` in `tests/test_prop_serialization_preservation.py`). One test reads the members from
   `typing.get_args` of the `root` annotation (`tests/test_models_manifest.py`).

## Goals / Non-Goals

**Goals:**

1. Validate a parse input against one document type, selected from its root key.
2. Keep the first location segment of each error entry as it is now: the member class name.
3. Keep the root-key map a fact of the manifest. Add no naming rule and no hand-maintained list to the binding.

**Non-Goals:**

1. A change to the public names, the parse functions, or `OscalParseError`.
2. A discriminator for the 13 nested union aliases ([#43]).
3. A bound on the `input` of each error entry ([#42], item 2).

## Decisions

### D1: A callable `Discriminator`, not `union_mode='left_to_right'`

The `root` field becomes a tagged union with a callable `Discriminator`. Pydantic then validates only the member that
the callable selects.

Alternative: `Field(union_mode='left_to_right')`. It is a smaller change with almost the same speed (212 ms against
226 ms in [#41]). But after a fault in one member, pydantic tries each later member. Thus the error still lists every
member and holds a copy of the body for each one ([#42]). The discriminator removes both costs.

Alternative: a plain string discriminator (`Field(discriminator='catalog')`). Pydantic supports a string discriminator
only for one field that all members share, with a literal value in each member. The document types do not share a
field, so a string discriminator does not apply.

### D2: The tag of each member is its class name

Each member is `Annotated[<Member>, Tag('<Member>')]`, for example `Tag('CatalogDocument')`. Pydantic puts the tag as
the first segment of the location. Thus an entry keeps today's location, for example
`('CatalogDocument', 'catalog', …)`.

Alternative: the root key as the tag, as [#41] suggests. Then each location starts with the root key two times, for
example `('catalog', 'catalog', …)`. Each location that a caller matches today changes, and the first segment holds no
information that the second segment does not. The class-name tag changes only the number of entries. This is a
deviation from the sketch in [#41]. Record it in the pull request.

### D3: The discriminator logic lives in `_base.py`, the generated module holds only the map

`oscal_bindings.v1._base` gets one hand-written function:

```python
def root_key_discriminator(root_keys: Mapping[str, str]) -> Discriminator: ...
```

`root_keys` maps each root key to the tag of its member (`{"catalog": "CatalogDocument", ...}`). The function returns
a `Discriminator` over a callable with this behavior:

1. For a `dict`, it returns the tag of the first key, in input order, that is in `root_keys`.
2. For a model instance, it returns the first class name in `type(value).__mro__` that is a tag. A subclass of a member
   then selects its member.
3. For other input, it returns `None`.

The `Discriminator` sets `custom_error_type='oscal_document_type'` and
`custom_error_message='Not an OSCAL document: no known root key'`. Pydantic uses the custom error only when the
callable returns `None` or an unknown tag. A fault inside the selected member keeps the errors of that member.

The post-processor emits the map as a dict literal inside the `root` annotation of `OscalDocument`:

```python
class OscalDocument(RootModel[CatalogDocument | ... | PlanOfActionAndMilestonesDocument]):
    root: Annotated[
        Annotated[CatalogDocument, Tag('CatalogDocument')]
        | ...,
        root_key_discriminator(
            {
                'catalog': 'CatalogDocument',
                ...
            }
        ),
    ]
```

Why: guard 2 stays as it is, the generated module holds no logic, and unit tests cover the callable without codegen.
`OscalBaseModel` sets the precedent: `models.py` imports hand-written behavior from `_base.py`.

Alternative: emit a module-level map and a function into `models.py`. The map fails guard 2, and a relaxed guard 2
lets other assignments through. A generated function is hand-written logic in a generated file.

### D4: The root-key map comes from the manifest `body-field`

A new post-processor step, `discriminate_document_union`, runs after `rename_document_union`. For the
`document-union` entry it reads the `body-field` of the `document` entry of each member. It adds a step failure, and
writes nothing, in each of these cases:

1. A member has no `document` entry, or its entry has no `body-field`.
2. Two members have the same `body-field`.
3. The member class has no required field whose alias (or name, when it has no alias) is the `body-field`.
4. The `OscalDocument` class has no `root` field of a plain union of the members.

Item 3 ties the manifest to the generated class, so a wrong `body-field` fails `hatch run generate`, not a parse at run
time. The step keeps the codegen member order, so the diff of `models.py` touches only the `root` field and the imports.

### D5: The base `RootModel[...]` keeps the plain union

Only the `root` field annotation changes. The base subscript keeps `CatalogDocument | ...`. Thus `rename_document_union`
and guard 1 ("root model" form) work as they are, and mypy sees the same root type. Pydantic builds the core schema from
the `root` field annotation, so the base subscript does not affect validation.

### D6: The JSON Schema of the root becomes `oneOf`

For a tagged union with a callable discriminator, pydantic 2.14.2 emits `oneOf` of the member `$ref`s at the root, with
no `discriminator` mapping. A probe on a two-member model showed this shape. Today the root is `anyOf`. The YAML loader
reads both forms (Context item 5). Task 3.5 checks that the YAML tests pass and records the new root shape for the pull
request.

### D7: The parse operation names the root keys of an object with no known root key

The message of a `Discriminator` custom error is fixed text, and an exception from the callable is not a validation
error: it escapes the validation as a raw `PydanticCustomError`. So `parse_oscal` rewrites the entry, as it does for a
limit entry (`_limit_entry`). When the only error is `oscal_document_type` and its `input` is a dict with keys, the
message becomes `Not an OSCAL document: no known root key (found: 'assessment_plan')`. The type, the location, and the
`input` of the entry stay. Each parse operation, the facade, and the YAML path use `parse_oscal`, so each one gets the
message. A direct `OscalDocument.model_validate*` call keeps the fixed message.

This entry is the rejection of a root key in the form of a field name, for example `assessment_plan`. Before the
change, smart mode reported `extra_forbidden` at that key for every member. That entry did not identify the document
type, because each member reported the same key. The store requirement PRS-005 requires a parse error and no populated
field, and the entry gives both. Below the root, the selected member still rejects a field-name key as
`extra_forbidden`. The name-keyed property tests expect `oscal_document_type` at `()` only for a root-key site.

Alternative: put the field name of each root key in the root-key map. A name-keyed root then selects its member, and
the member reports `extra_forbidden` at the key. It routes on internal names, and it adds a `missing` entry for the
OSCAL key.

### D8: The cyclic GC cost of a parse is an application setting, not a library setting

One parse of the 800-53 catalog creates about 174,000 objects that the cyclic GC tracks: for each model, the
instance, its `__dict__`, and the pydantic fields-set `set`, and also the lists. At the default threshold of 2000, a
parse starts 87 collections. On Python 3.14, each collection also scans a part of the old generation, so the GC time of
a parse increases with the objects that the application holds:

| Other documents that the process holds | `parse_oscal` | GC time |
|---|---|---|
| 0 | 85 ms | 28 ms |
| 1 | 113 ms | 58 ms |
| 3 | 195 ms | 139 ms |
| 3, after `gc.freeze()` | 74 ms | 16 ms |
| 1, `gc.set_threshold(50_000)` | 65 ms | 9 ms |

The library does not change the GC state. `gc.disable()` and `gc.set_threshold()` are process-wide and not
thread-safe, so a call in `parse_oscal` changes the behavior of the application and of its other threads. The README
documents `gc.freeze()` and a higher threshold as application settings.

Alternative: fewer tracked objects for each model. The instance, its `__dict__`, and the fields-set are pydantic
internals, so the binding cannot remove them.

### D9: The benchmark measures the binding, not the GC cost of the harness

`scripts/bench_serialization.py` held the parsed document for the serialize cases and the result of the previous run
during each timed parse. Thus the parse median included the GC cost of about two documents. The script now:

1. Times the parse case before it parses the document for the serialize cases.
2. Drops the result of each run after its time is read, so the next run holds no previous result and the time does
   not include the deallocation.
3. Reports a median with GC enabled and a median with GC disabled for each case.

## Risks / Trade-offs

1. [Callers pin the count or the content of `OscalParseError.errors`] → The release notes state the change. D2 keeps
   each location of the remaining entries.
2. [In JSON mode, pydantic gives the callable a Python value of the input. This can cost time on a large document] →
   The [#41] prototype measured this path at 226 ms against 194 ms for the member alone. Task 4.2 measures it again on
   the regenerated module and requires at least 2× against today.
3. [A later manifest adds a document type with no `body-field`] → D4 item 1 fails `hatch run generate` and names the
   entry.
4. [A future pydantic changes the location segment of a tagged union] → A parser test pins the first segment for a
   catalog fault.
5. [Two root keys in one input] → D3 item 1 selects the first one. The selected member rejects the other key as
   `extra_forbidden`, so the input still fails. The spec pins this case.

## Migration Plan

1. Run `hatch run generate` and commit the regenerated `models.py` with the post-processor change. The CI drift check
   requires the two to match.
2. State the error-shape change in the release notes of the next version.
3. Rollback: revert the commit. No data or format migration exists.

[#41]: https://github.com/cairn-proofs/oscal-bindings-python/issues/41
[#42]: https://github.com/cairn-proofs/oscal-bindings-python/issues/42
[#43]: https://github.com/cairn-proofs/oscal-bindings-python/issues/43
