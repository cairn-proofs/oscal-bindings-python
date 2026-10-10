"""Generated-model inventory and one valid instance per object model.

Used by ``tests/test_base_model.py`` (task 4.3 of the
``oscal-default-serialization-fix`` spec) to run its construction tests over
every object model instead of a sample.

- `OBJECT_MODELS`: every class in `oscal_bindings.v1.models` that subclasses
  `OscalBaseModel`, sorted by name. 183 inherit it directly
  (``class X(OscalBaseModel)``) and one indirectly (``ExternalId1(ExternalId)``).
- `ALIAS_FIELDS`: every ``(cls, name, alias)`` with ``alias not in (None, name)``.
- `harvest_instances`: walks parsed corpus documents and keeps, per class, the
  instance with the most alias-differing fields set, plus the first non-None
  value seen for every ``(cls, field name)``.
- `synthesize_instance`: builds a small valid instance from the field
  annotations alone (required fields, plus every alias-differing optional field
  at the top level). It's deterministic and needs no corpus, so it covers the
  classes the corpus never instantiates.

Nothing here builds a whole OSCAL document; full documents come only from the
pinned corpora.
"""

from __future__ import annotations

import enum
import types
import typing
from typing import Annotated, Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel, RootModel, TypeAdapter, ValidationError

from oscal_bindings.v1 import models
from oscal_bindings.v1._base import OscalBaseModel

if typing.TYPE_CHECKING:
    from collections.abc import Iterable

ModelCls = type[OscalBaseModel]

OBJECT_MODELS: tuple[ModelCls, ...] = tuple(
    sorted(
        (
            obj
            for obj in vars(models).values()
            if isinstance(obj, type)
            and issubclass(obj, OscalBaseModel)
            and obj is not OscalBaseModel
        ),
        key=lambda c: c.__name__,
    )
)

ALIAS_FIELDS: tuple[tuple[ModelCls, str, str], ...] = tuple(
    (cls, name, info.alias)
    for cls in OBJECT_MODELS
    for name, info in cls.model_fields.items()
    if info.alias is not None and info.alias != name
)


def alias_names(cls: type[BaseModel]) -> dict[str, str]:
    """``{python name: alias}`` for the alias-differing fields of ``cls``."""
    return {
        name: info.alias
        for name, info in cls.model_fields.items()
        if info.alias is not None and info.alias != name
    }


def kwargs_by_name(inst: BaseModel) -> dict[str, Any]:
    """Constructor kwargs keyed by Python name, from ``inst.model_fields_set``."""
    return {name: getattr(inst, name) for name in inst.model_fields_set}


def kwargs_by_alias(inst: BaseModel) -> dict[str, Any]:
    """Constructor kwargs keyed by OSCAL alias, from ``inst.model_fields_set``."""
    fields = type(inst).model_fields
    return {
        fields[name].alias or name: getattr(inst, name)
        for name in inst.model_fields_set
    }


# --- Corpus harvest ----------------------------------------------------------


def harvest_instances(
    roots: Iterable[object],
) -> tuple[dict[ModelCls, OscalBaseModel], dict[tuple[ModelCls, str], Any]]:
    """Walk parsed documents; return ``(instances, field_values)``.

    ``instances`` keeps, per class, the instance with the most alias-differing
    fields in ``model_fields_set`` (first seen wins a tie). ``field_values``
    keeps the first non-None value seen for each ``(cls, python name)``.
    """
    instances: dict[ModelCls, OscalBaseModel] = {}
    scores: dict[ModelCls, int] = {}
    field_values: dict[tuple[ModelCls, str], Any] = {}

    def walk(value: object) -> None:
        if isinstance(value, RootModel):
            walk(value.root)
        elif isinstance(value, OscalBaseModel):
            cls = type(value)
            aliased = alias_names(cls)
            score = sum(1 for n in value.model_fields_set if n in aliased)
            if cls not in instances or score > scores[cls]:
                instances[cls] = value
                scores[cls] = score
            for name in cls.model_fields:
                child = getattr(value, name)
                if child is not None:
                    field_values.setdefault((cls, name), child)
                    walk(child)
        elif isinstance(value, list | tuple):
            for child in value:
                walk(child)
        elif isinstance(value, dict):
            for child in value.values():
                walk(child)

    for root in roots:
        walk(root)
    return instances, field_values


# --- Synthesis from annotations ----------------------------------------------


class UnsynthesizableError(Exception):
    """`synthesize_instance` couldn't build a valid value for some field."""


# Tried in order for scalar leaves until one validates against the field's
# annotation and constraints (patterns, formats, enums are handled elsewhere).
_SCALAR_CANDIDATES: tuple[object, ...] = (
    "x",
    "11111111-1111-4111-8111-111111111111",
    "https://example.com/x",
    "2024-01-01T00:00:00Z",
    "2024-01-01",
    "P1D",
    "aGVsbG8=",
    "+15555550100",
    "user@example.com",
    1,
    0.5,
    True,
)

_MAX_DEPTH = 8


def _scalar(annotation: Any, metadata: list[Any]) -> object:
    adapter: TypeAdapter[Any] = TypeAdapter(
        Annotated[(annotation, *metadata)] if metadata else annotation
    )
    for candidate in _SCALAR_CANDIDATES:
        try:
            adapter.validate_python(candidate)
        except ValidationError:
            continue
        return candidate
    msg = f"no scalar candidate fits {annotation!r} with {metadata!r}"
    raise UnsynthesizableError(msg)


def _value_for(annotation: Any, metadata: list[Any], depth: int) -> object:
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is Annotated:
        return _value_for(args[0], [*metadata, *annotation.__metadata__], depth)
    if origin is Union or origin is types.UnionType:
        errors = []
        for arm in args:
            if arm is type(None):
                continue
            try:
                return _value_for(arm, metadata, depth)
            except UnsynthesizableError as exc:
                errors.append(str(exc))
        raise UnsynthesizableError("; ".join(errors))
    if origin is list:
        # One item satisfies every `min_length=1` list in the schema.
        return [_value_for(args[0], [], depth)]
    if origin is dict:
        # Every dict-typed field in the schema (`flat`, `combine`) is an
        # empty-object marker with `max_length=0`.
        return {}
    if origin is Literal:
        return args[0]
    return _class_value(annotation, metadata, depth)


def _class_value(annotation: Any, metadata: list[Any], depth: int) -> object:
    """A value for a non-generic annotation: enum, model, or scalar."""
    if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
        return next(iter(annotation))
    if isinstance(annotation, type) and issubclass(annotation, RootModel):
        root = annotation.model_fields["root"]
        return annotation.model_validate(
            _value_for(root.annotation, list(root.metadata), depth)
        )
    if isinstance(annotation, type) and issubclass(annotation, OscalBaseModel):
        return synthesize_instance(annotation, _depth=depth + 1)
    return _scalar(annotation, metadata)


def synthesize_instance(cls: ModelCls, *, _depth: int = 0) -> OscalBaseModel:
    """A small valid ``cls`` built from field annotations, validated by alias.

    Sets every required field. At the top level it also sets each
    alias-differing optional field it can build, so by-name and by-alias
    construction differ on as many keys as possible. Nested models get
    required fields only, which keeps the result small and stops recursion.

    Raises:
        UnsynthesizableError: A required field has no buildable valid value.
    """
    if _depth > _MAX_DEPTH:
        msg = f"{cls.__name__}: recursion deeper than {_MAX_DEPTH}"
        raise UnsynthesizableError(msg)
    aliased = alias_names(cls)
    required: dict[str, Any] = {}
    optional: dict[str, Any] = {}
    for name, info in cls.model_fields.items():
        key = info.alias or name
        if info.is_required():
            try:
                required[key] = _value_for(info.annotation, list(info.metadata), _depth)
            except UnsynthesizableError as exc:
                msg = f"{cls.__name__}.{name}: {exc}"
                raise UnsynthesizableError(msg) from exc
        elif _depth == 0 and name in aliased:
            try:
                optional[key] = _value_for(info.annotation, list(info.metadata), _depth)
            except UnsynthesizableError:
                continue  # optional: best effort
    # Optional values are best effort too: if they don't validate together,
    # add them one at a time and keep the ones that do.
    try:
        return cls.model_validate({**required, **optional})
    except ValidationError:
        pass
    kept: dict[str, Any] = {}
    for key, value in optional.items():
        try:
            cls.model_validate({**required, **kept, key: value})
        except ValidationError:
            continue
        kept[key] = value
    try:
        return cls.model_validate({**required, **kept})
    except ValidationError as exc:
        msg = f"{cls.__name__}: synthesized data invalid: {exc}"
        raise UnsynthesizableError(msg) from exc
