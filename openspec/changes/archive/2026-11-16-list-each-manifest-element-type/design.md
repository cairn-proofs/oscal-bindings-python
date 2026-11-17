# Design

## Context

1. `_build_element_map()` in `v1/extensions/validate_element.py` reads `dir(models)` and keeps each `BaseModel`
   subclass, except `BaseModel`, `OscalBaseModel`, and the pydantic parametrizations. `models.py` imports
   `RootModel`, so the map holds `root-model`. `validate_element` calls `model_validate` on the class of the name.
2. `models.py` defines each manifest type in the form of its kind:
   1. An `object`, `document`, `document-union`, or `single-or-many` type is a `BaseModel` subclass. There are 187.
   2. An `enum` type is an `Enum` subclass. There are 44.
   3. A `union` type is a module-level `TypeAlias` of the form `A | B`. At run time it is a `types.UnionType`. There
      are 13.
   4. The 14 scalar aliases, such as `LocationUuid`, are `Annotated` objects, not `types.UnionType`.
3. `_pascal_to_kebab` gives the 244 names of `expected/element-types.json` from the 244 manifest names. Python
   `sorted()` gives code-point order. Thus no naming rule changes.
4. In `tests/test_conformance.py`, `OPERATIONS` has no `element-types` entry, and `test_case` reads `case["input"]`.
   The `element-types/all` case has no `input`.

## Goals / Non-Goals

**Goals:**

1. Keep the time and the result of `validate_element` the same for each name that the list holds today.
2. Add no cost at import.

**Non-Goals:**

1. A change to `models.py` or to the post-processor.
2. A change to the location or the message of a failure.

## Decisions

### D1. Find the types in the `models` module by their run-time form

`_build_element_map()` keeps each name of `vars(models)` that holds one of these values:

1. A `BaseModel` subclass that `models` defines (`__module__` is `models.__name__`), and that is not a pydantic
   parametrization. The `__module__` check removes `BaseModel`, `OscalBaseModel`, and `RootModel`. The two
   parametrizations of `RootModel` have `__module__` equal to `models.__name__`, so the parametrization check stays.
2. An `Enum` subclass that `models` defines.
3. A `types.UnionType` value.

Alternative: the post-processor writes a list of the manifest names into `models.py`. This puts a second form of the
manifest into generated code, and the `models.py` drift check must then cover it. The conformance case and
`test_element_types_are_manifest_class_names` already compare the list with the contract and with the manifest. Thus
the run-time forms are sufficient.

### D2. A `TypeAdapter` validates an enum or a union, and the adapter is made on first use

1. For a `BaseModel` name, `validate_element` calls `model_validate`, as today.
2. For an enum or a union name, `validate_element` uses a `TypeAdapter`. For a union, the adapter type is
   `Annotated[<Alias>, Field(union_mode="left_to_right")]`, the same mode as the union fields of the models.
3. A cache keeps one adapter for each name. The first call for the name makes the adapter.

A `TypeAdapter` in lax mode accepts the string value of an enum, as ELV-001 requires. To make all 57 adapters at import
adds a cost at import. Models keep `model_validate`, because a `TypeAdapter` for each model also adds a cost and gives
no new behavior.

### D3. The corpus case replaces the snapshot of the list

1. The runner gets an `_element_types` operation. It compares `get_supported_element_types()` with the JSON list of
   `expected`, item by item. `test_case` passes the input path only when the case has `input`.
2. `tests/support/element_types_snapshot.txt` and `test_supported_element_types_match_pre_fix_snapshot` go away. The
   snapshot pinned the list from before this change, and the corpus case now pins the contract list.
3. `test_element_types_are_manifest_class_names` covers each manifest kind and has no `root-model` exception. It also
   checks that each name maps to the object of the same name in `models`.

## Risks / Trade-offs

1. [A future `models.py` holds a module-level union that is not a manifest type] -> The corpus case and the manifest
   test fail. Each names the extra entry.
2. [A caller uses `root-model`] -> The name never validated an OSCAL value. The pull request and the notes of the next
   release name the removal.
