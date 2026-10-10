"""Keyword construction and `OscalBaseModel` mechanism tripwires (Property 3).

Task 4.3 of the ``oscal-default-serialization-fix`` spec (#5). Validates
Requirements 1.6, 2.9, 3.3, 3.4.

`OscalBaseModel` lets constructors take Python field names (2.9) while
validation stays alias-only (3.3, 3.4). That rests on two things a well-meant
change could quietly break:

- The ``__pydantic_base_init__`` marker on `OscalBaseModel.__init__` keeps
  pydantic from routing ``model_validate*`` through the override (design.md,
  Hypothesized Root Cause 5).
- The config has no ``validate_by_name`` / ``populate_by_name`` (design.md,
  Hypothesized Root Cause 4, Option A rejected).

Every test here fails loudly with the class/field involved and the root cause
it guards. Parametrizations run over every object model and every
alias-differing field, not a sample, and their sizes are pinned so a codegen
change can't make them vacuous.
"""

from __future__ import annotations

import copy
import json
import pickle
import types
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Any, Union, get_args, get_origin

import pytest
from pydantic import BaseModel, ValidationError
from support.model_instances import (
    ALIAS_FIELDS,
    OBJECT_MODELS,
    ModelCls,
    alias_names,
    harvest_instances,
    kwargs_by_alias,
    kwargs_by_name,
    synthesize_instance,
)

from oscal_bindings import parse_oscal
from oscal_bindings.v1 import models
from oscal_bindings.v1._base import OscalBaseModel

if TYPE_CHECKING:
    from collections.abc import Callable

    from support.corpus import CorpusDoc

# --- Failure-message suffixes --------------------------------------------------

RC5 = (
    "pydantic no longer honors `__pydantic_base_init__`; model_validate* would "
    "route through OscalBaseModel.__init__ and accept name-keyed OSCAL input. "
    "See design.md, Hypothesized Root Cause 5."
)
RC4_TEMPLATE = (
    "validate_by_name/populate_by_name is enabled on {cls}. That makes "
    "name-keyed OSCAL input valid for every model_validate* call without "
    "per-call by_name=False, including user calls (3.3/3.4). Construction by "
    "name comes from OscalBaseModel.__init__ instead. See design.md, "
    "Hypothesized Root Cause 4."
)
CONSTRUCTION = (
    "By-name keyword construction (2.9) is broken: OscalBaseModel.__init__ must "
    "map each Python field name to its alias before validation. See design.md, "
    "Fix Implementation section 3."
)

# --- Pinned inventory ------------------------------------------------------------
# Update these only together with a deliberate schema refresh (`hatch run
# generate`), after checking the new numbers are expected. A drop to zero, or
# any unexplained change, means the parametrizations below have gone stale.

# `class X(OscalBaseModel)` in models.py (design.md, Fix Implementation 5).
N_DIRECT_SUBCLASSES = 183
# Plus `ExternalId1(ExternalId)`, which inherits the base indirectly.
N_OBJECT_MODELS = 184
N_ALIAS_FIELDS = 278
N_ALIAS_CLASSES = 138
N_NESTED_CASES = 437

# Classes in ALIAS_FIELDS with no valid instance in INSTANCES. Neither the
# corpus nor `synthesize_instance` leaves a gap today, so this is empty. If a
# schema refresh adds a class neither can build, list it here with a comment
# explaining why; the coverage test fails if a listed class becomes covered.
UNCOVERED_CLASSES: frozenset[str] = frozenset()

UUID = "11111111-1111-4111-8111-111111111111"


class _Probe:
    """Value no field accepts; used where the probe must be value-independent."""

    def __repr__(self) -> str:
        return "<probe>"


PROBE = _Probe()


def _where(cls: type, field: str | None = None) -> str:
    return f"{cls.__name__}.{field}" if field else cls.__name__


def _errors(exc: ValidationError) -> list[tuple[str, tuple[Any, ...], str]]:
    return [(e["type"], tuple(e["loc"]), e["msg"]) for e in exc.errors()]


def _outcome(cls: ModelCls, kwargs: dict[str, Any]) -> object:
    """The constructed model, or the ValidationError's ``(type, loc, msg)`` list."""
    try:
        return cls(**kwargs)
    except ValidationError as exc:
        return _errors(exc)


def _attempt(fn: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
    """``fn(*args, **kwargs)``, or the `ValidationError` it raised."""
    try:
        return fn(*args, **kwargs)
    except ValidationError as exc:
        return exc


def _has_extra_forbidden(exc: ValidationError, loc: tuple[Any, ...]) -> bool:
    return any(t == "extra_forbidden" and lc == loc for t, lc, _ in _errors(exc))


# --- Shared instances (built once per session) -------------------------------


@dataclass(frozen=True)
class Harvest:
    instances: dict[ModelCls, OscalBaseModel]
    field_values: dict[tuple[ModelCls, str], Any]
    synthesized: frozenset[ModelCls]


def _alias_score(cls: ModelCls, inst: OscalBaseModel) -> int:
    return len(set(alias_names(cls)) & inst.model_fields_set)


@pytest.fixture(scope="session")
def harvest(nist_docs: list[CorpusDoc], aws_docs: list[CorpusDoc]) -> Harvest:
    """One valid instance per object model: corpus first, synthesized otherwise.

    A corpus instance that sets none of its class's alias-differing fields is
    replaced by a synthesized one that does, so by-name and by-alias
    construction actually differ for every class in ALIAS_FIELDS.
    """
    # Skip the >1 MB catalogs: they repeat the same classes and cost ~2 s per
    # xdist worker. No class loses its corpus instance without them.
    docs = [d for d in (*nist_docs, *aws_docs) if len(d.raw_bytes) <= 1_000_000]
    assert docs, "NIST/AWS corpus is empty; cannot harvest instances"
    instances, field_values = harvest_instances(parse_oscal(d.raw_bytes) for d in docs)
    synthesized: set[ModelCls] = set()
    for cls in OBJECT_MODELS:
        if cls.__name__ in UNCOVERED_CLASSES:
            continue
        have = instances.get(cls)
        if have is not None and (not alias_names(cls) or _alias_score(cls, have)):
            continue
        made = synthesize_instance(cls)
        if have is None or _alias_score(cls, made):
            instances[cls] = made
            synthesized.add(cls)
    return Harvest(instances, field_values, frozenset(synthesized))


@pytest.fixture(scope="session")
def instances(harvest: Harvest) -> dict[ModelCls, OscalBaseModel]:
    return harvest.instances


# --- Inventory pins ----------------------------------------------------------


def test_inventory_is_pinned() -> None:
    """OBJECT_MODELS / ALIAS_FIELDS are non-empty and have the pinned sizes."""
    assert OBJECT_MODELS, "OBJECT_MODELS is empty: every test below is vacuous"
    assert ALIAS_FIELDS, "ALIAS_FIELDS is empty: every test below is vacuous"
    direct = [c for c in OBJECT_MODELS if c.__bases__ == (OscalBaseModel,)]
    assert len(direct) == N_DIRECT_SUBCLASSES, (
        f"{len(direct)} classes subclass OscalBaseModel directly, pinned "
        f"{N_DIRECT_SUBCLASSES}. Did codegen stop passing --base-class?"
    )
    indirect = sorted(c.__name__ for c in OBJECT_MODELS if c not in direct)
    assert indirect == ["ExternalId1"], f"unexpected indirect subclasses {indirect}"
    assert len(OBJECT_MODELS) == N_OBJECT_MODELS
    assert len(ALIAS_FIELDS) == N_ALIAS_FIELDS, (
        f"{len(ALIAS_FIELDS)} alias-differing fields, pinned {N_ALIAS_FIELDS}"
    )
    alias_classes = {c for c, _, _ in ALIAS_FIELDS}
    assert len(alias_classes) == N_ALIAS_CLASSES
    assert len(NESTED_CASES) == N_NESTED_CASES, (
        f"{len(NESTED_CASES)} nested-model cases, pinned {N_NESTED_CASES}"
    )


# --- (a) Marker tripwire: structural -------------------------------------------


def test_marker_is_on_base_init() -> None:
    assert getattr(OscalBaseModel.__init__, "__pydantic_base_init__", False) is True, (
        f"OscalBaseModel.__init__ lost its __pydantic_base_init__ marker. {RC5}"
    )


@pytest.mark.parametrize(
    "cls", [OscalBaseModel, *OBJECT_MODELS], ids=lambda c: c.__name__
)
def test_no_custom_init(cls: ModelCls) -> None:
    """pydantic doesn't treat the override as a custom __init__ anywhere."""
    assert cls.__pydantic_custom_init__ is False, (
        f"{cls.__name__}.__pydantic_custom_init__ is True. {RC5}"
    )
    if cls is not OscalBaseModel:
        assert "__init__" not in cls.__dict__, (
            f"generated class {cls.__name__} defines its own __init__, which "
            f"pydantic would treat as custom. {RC5}"
        )


# --- (a) Marker tripwire: behavioral canaries --------------------------------

_METADATA = {
    "title": "t",
    "last-modified": "2024-01-01T00:00:00Z",
    "version": "1",
    "oscal-version": "1.2.3",
}


@dataclass(frozen=True)
class Canary:
    model: type[BaseModel]
    data: dict[str, Any]
    loc: tuple[Any, ...]  # full loc of the name-keyed `media_type`

    def media_type(self, result: BaseModel) -> object:
        """``media_type`` of the Rlink the name key was placed in."""
        if isinstance(result, models.Rlink):
            return result.media_type
        if isinstance(result, models.Resource):
            return result.rlinks[0].media_type  # type: ignore[index]
        catalog = result.root.catalog  # type: ignore[attr-defined]
        return catalog.back_matter.resources[0].rlinks[0].media_type


_RLINK = {"href": "x", "media_type": "t"}
CANARIES = {
    "rlink-top": Canary(models.Rlink, dict(_RLINK), ("media_type",)),
    "resource-nested": Canary(
        models.Resource,
        {"uuid": UUID, "rlinks": [dict(_RLINK)]},
        ("rlinks", 0, "media_type"),
    ),
    "document-deep": Canary(
        models.OscalDocument,
        {
            "catalog": {
                "uuid": UUID,
                "metadata": _METADATA,
                "back-matter": {
                    "resources": [{"uuid": UUID, "rlinks": [dict(_RLINK)]}]
                },
            }
        },
        # OscalDocument is a union: errors carry the matching arm's tag first.
        (
            "CatalogDocument",
            "catalog",
            "back-matter",
            "resources",
            0,
            "rlinks",
            0,
            "media_type",
        ),
    ),
}
CALL_KWARGS = {"no-kwargs": {}, "by-alias-only": {"by_alias": True, "by_name": False}}


@pytest.mark.parametrize("kwargs", CALL_KWARGS.values(), ids=CALL_KWARGS.keys())
@pytest.mark.parametrize("canary", CANARIES.values(), ids=CANARIES.keys())
def test_canary_dict_rejects_name_key(canary: Canary, kwargs: dict[str, Any]) -> None:
    """Dict mode: a name key is ``extra_forbidden`` at its full loc (3.3, 3.4)."""
    where = f"{canary.model.__name__}.model_validate(dict, **{kwargs}) at {canary.loc}"
    result = _attempt(canary.model.model_validate, copy.deepcopy(canary.data), **kwargs)
    if not isinstance(result, ValidationError):
        pytest.fail(
            f"{where}: name-keyed input ACCEPTED "
            f"(media_type={canary.media_type(result)!r}). {RC5}"
        )
    assert _has_extra_forbidden(result, canary.loc), (
        f"{where}: rejected, but not with extra_forbidden at the name key: "
        f"{_errors(result)}. {RC5}"
    )


@pytest.mark.parametrize("kwargs", CALL_KWARGS.values(), ids=CALL_KWARGS.keys())
@pytest.mark.parametrize("canary", CANARIES.values(), ids=CANARIES.keys())
def test_canary_json_never_keeps_name_key(
    canary: Canary, kwargs: dict[str, Any]
) -> None:
    """JSON mode: the value is never kept (3.3(b)).

    pydantic 2.13.x drops the key (design.md Root Cause 6, #6); 2.11.0 rejects
    it with ``extra_forbidden``. Either is fine; keeping ``"t"`` is not.
    """
    where = f"{canary.model.__name__}.model_validate_json(**{kwargs}) at {canary.loc}"
    result = _attempt(
        canary.model.model_validate_json, json.dumps(canary.data), **kwargs
    )
    if isinstance(result, ValidationError):
        assert _has_extra_forbidden(result, canary.loc), (
            f"{where}: rejected, but not with extra_forbidden at the name key: "
            f"{_errors(result)}"
        )
        return
    kept = canary.media_type(result)
    assert kept is None, (
        f"{where}: name-keyed JSON value KEPT (media_type={kept!r}); validation "
        f"now routes through __init__ (variant B0) or by-name validation got "
        f"enabled. {RC5}"
    )


# --- (b) Config tripwire against Option A --------------------------------------


@pytest.mark.parametrize(
    "cls", [OscalBaseModel, *OBJECT_MODELS], ids=lambda c: c.__name__
)
def test_config_is_alias_only(cls: ModelCls) -> None:
    config = cls.model_config
    message = RC4_TEMPLATE.format(cls=cls.__name__)
    assert not config.get("validate_by_name", False), message
    assert not config.get("populate_by_name", False), message
    assert config.get("validate_by_alias", True) is True, (
        f"validate_by_alias is not True on {cls.__name__}: OSCAL input could no "
        f"longer validate by alias. See design.md, Hypothesized Root Cause 4."
    )


# --- (c) Exhaustive construction -----------------------------------------------


ALIAS_FIELD_PARAMS = [
    pytest.param(cls, name, alias, id=f"{cls.__name__}.{name}")
    for cls, name, alias in ALIAS_FIELDS
]


def _probe_value(harvest: Harvest, cls: ModelCls, name: str) -> object:
    inst = harvest.instances.get(cls)
    value = getattr(inst, name, None) if inst is not None else None
    if value is None:
        value = harvest.field_values.get((cls, name))
    return PROBE if value is None else value


def _base_kwargs(harvest: Harvest, cls: ModelCls, name: str) -> dict[str, Any]:
    """The instance's alias kwargs minus ``name``'s field (``{}`` if none)."""
    inst = harvest.instances.get(cls)
    if inst is None:
        return {}
    alias = cls.model_fields[name].alias
    return {k: v for k, v in kwargs_by_alias(inst).items() if k != alias}


@pytest.mark.parametrize(("cls", "name", "alias"), ALIAS_FIELD_PARAMS)
def test_name_and_alias_kwarg_same_outcome(
    harvest: Harvest, cls: ModelCls, name: str, alias: str
) -> None:
    """``cls(name=v)`` and ``cls(alias=v)`` agree, for a real and a bogus ``v``."""
    where = _where(cls, name)
    base = _base_kwargs(harvest, cls, name)
    for value in (_probe_value(harvest, cls, name), PROBE):
        by_name = _outcome(cls, {**base, name: value})
        by_alias = _outcome(cls, {**base, alias: value})
        if isinstance(by_name, list):
            forbidden = [e for e in by_name if e[0] == "extra_forbidden"]
            assert not any(e[1] == (name,) for e in forbidden), (
                f"{where}: kwarg {name!r} rejected as extra_forbidden. {CONSTRUCTION}"
            )
        assert by_name == by_alias, (
            f"{where}: {name}={value!r} gave {by_name!r}, but {alias}= gave "
            f"{by_alias!r}. {CONSTRUCTION}"
        )


@pytest.mark.parametrize(("cls", "name", "alias"), ALIAS_FIELD_PARAMS)
def test_name_and_alias_together_rejected(
    harvest: Harvest, cls: ModelCls, name: str, alias: str
) -> None:
    """Passing both spellings of one field is ``extra_forbidden`` at the name."""
    value = _probe_value(harvest, cls, name)
    kwargs = {**_base_kwargs(harvest, cls, name), name: value, alias: value}
    with pytest.raises(ValidationError) as info:
        cls(**kwargs)
    assert _has_extra_forbidden(info.value, (name,)), (
        f"{_where(cls, name)}: name+alias not rejected as extra_forbidden at "
        f"{name!r}: {_errors(info.value)}. A silent pick of one value would hide "
        f"caller bugs. See design.md, Fix Implementation section 3."
    )


def test_instances_cover_alias_classes(harvest: Harvest) -> None:
    """Every class with alias fields has an instance that sets one, or is listed."""
    alias_classes = {c.__name__: c for c, _, _ in ALIAS_FIELDS}
    unknown = UNCOVERED_CLASSES - alias_classes.keys()
    assert not unknown, f"UNCOVERED_CLASSES names non-alias classes: {unknown}"
    covered = {
        n
        for n, c in alias_classes.items()
        if c in harvest.instances and _alias_score(c, harvest.instances[c])
    }
    stale = UNCOVERED_CLASSES & covered
    assert not stale, f"now covered; remove from UNCOVERED_CLASSES: {sorted(stale)}"
    gaps = alias_classes.keys() - covered - UNCOVERED_CLASSES
    assert not gaps, (
        f"no instance sets an alias-differing field for {sorted(gaps)}; extend "
        f"synthesize_instance or list them in UNCOVERED_CLASSES with a reason"
    )


@pytest.mark.parametrize("cls", OBJECT_MODELS, ids=lambda c: c.__name__)
def test_construction_round_trip(
    instances: dict[ModelCls, OscalBaseModel], cls: ModelCls
) -> None:
    """by-name == by-alias == model_validate(alias dict) == the instance."""
    if cls.__name__ in UNCOVERED_CLASSES:
        pytest.skip(f"{cls.__name__} listed in UNCOVERED_CLASSES")
    inst = instances[cls]
    where = _where(cls)
    try:
        by_name = cls(**kwargs_by_name(inst))
    except ValidationError as exc:
        pytest.fail(f"{where}: by-name construction failed: {exc}. {CONSTRUCTION}")
    by_alias = cls(**kwargs_by_alias(inst))
    validated = cls.model_validate(inst.model_dump(by_alias=True, exclude_none=True))
    assert by_name == inst, f"{where}: by-name construction differs. {CONSTRUCTION}"
    assert by_alias == inst, f"{where}: by-alias construction differs"
    assert validated == inst, f"{where}: model_validate(alias dict) differs"
    assert by_name.model_fields_set == inst.model_fields_set, where


# Nested name-keyed dicts passed inside constructor kwargs stay alias-only.


def _model_types(annotation: Any, is_list: bool = False) -> list[tuple[ModelCls, bool]]:
    """``(model class, inside a list)`` for every OscalBaseModel in an annotation."""
    origin, args = get_origin(annotation), get_args(annotation)
    if origin is Annotated:
        return _model_types(args[0], is_list)
    if origin is Union or origin is types.UnionType:
        return [t for arm in args for t in _model_types(arm, is_list)]
    if origin is list:
        return _model_types(args[0], True)
    if isinstance(annotation, type) and issubclass(annotation, OscalBaseModel):
        return [(annotation, is_list)]
    return []


@dataclass(frozen=True)
class NestedCase:
    outer: ModelCls
    field: str
    inner: ModelCls
    is_list: bool

    @property
    def id(self) -> str:
        return f"{self.outer.__name__}.{self.field}[{self.inner.__name__}]"


NESTED_CASES: tuple[NestedCase, ...] = tuple(
    NestedCase(outer, name, inner, is_list)
    for outer in OBJECT_MODELS
    for name, info in outer.model_fields.items()
    for inner, is_list in _model_types(info.annotation)
    if alias_names(inner)
)


def test_nested_cases_cover_every_nested_alias_class() -> None:
    nested_targets = {
        inner
        for outer in OBJECT_MODELS
        for info in outer.model_fields.values()
        for inner, _ in _model_types(info.annotation)
        if alias_names(inner)
    }
    assert nested_targets, "no nested alias classes: nested test is vacuous"
    assert {c.inner for c in NESTED_CASES} == nested_targets


@pytest.mark.parametrize("case", NESTED_CASES, ids=lambda c: c.id)
def test_nested_name_keyed_dict_in_kwargs_rejected(
    instances: dict[ModelCls, OscalBaseModel], case: NestedCase
) -> None:
    """``Outer(field=<inner dumped by name>)`` is ``extra_forbidden`` at the name."""
    if {case.outer.__name__, case.inner.__name__} & UNCOVERED_CLASSES:
        pytest.skip("class listed in UNCOVERED_CLASSES")
    inner = instances[case.inner]
    names_set = set(alias_names(case.inner)) & inner.model_fields_set
    assert names_set, f"{case.id}: inner instance sets no alias-differing field"
    nested = inner.model_dump(by_alias=False, exclude_none=True)
    alias = case.outer.model_fields[case.field].alias or case.field
    kwargs = {**kwargs_by_alias(instances[case.outer]), alias: nested}
    prefix: tuple[Any, ...] = (alias,)
    if case.is_list:
        kwargs[alias] = [nested]
        prefix = (alias, 0)
    where = f"{case.id} (kwarg {alias!r})"
    result = _attempt(case.outer, **kwargs)
    if not isinstance(result, ValidationError):
        pytest.fail(
            f"{where}: nested name-keyed dict ACCEPTED. Only the constructor's own "
            f"kwargs may be mapped by name; nested plain dicts stay alias-only "
            f"(2.9). See design.md, Hypothesized Root Causes 4 and 5."
        )
    hits = [
        loc
        for t, loc, _ in _errors(result)
        if t == "extra_forbidden"
        and loc[: len(prefix)] == prefix
        and len(loc) - len(prefix) in (1, 2)  # optional union-arm tag
        and loc[-1] in names_set
    ]
    assert hits, (
        f"{where}: rejected, but not with extra_forbidden at a nested name "
        f"key {sorted(names_set)}: {_errors(result)[:5]}"
    )


# --- (d) Copy and pickle unchanged ----------------------------------------------


@pytest.fixture(scope="session")
def sample_docs(
    nist_docs: list[CorpusDoc], aws_docs: list[CorpusDoc]
) -> list[BaseModel]:
    """The smallest NIST/AWS document of each root type."""
    smallest: dict[str, CorpusDoc] = {}
    for doc in [*nist_docs, *aws_docs]:
        have = smallest.get(doc.root_key)
        if have is None or len(doc.raw_bytes) < len(have.raw_bytes):
            smallest[doc.root_key] = doc
    assert len(smallest) >= 7, f"expected 7+ document types, got {sorted(smallest)}"
    return [parse_oscal(d.raw_bytes) for d in smallest.values()]


COPIERS = {
    "pickle": lambda m: pickle.loads(pickle.dumps(m)),  # noqa: S301 - own data
    "copy": copy.copy,
    "deepcopy": copy.deepcopy,
    "model_copy": lambda m: m.model_copy(),
}


def _all_models(
    instances: dict[ModelCls, OscalBaseModel], sample_docs: list[BaseModel]
) -> list[BaseModel]:
    return [*instances.values(), *sample_docs]


def _assert_copies_equal(models_: list[BaseModel]) -> None:
    for m in models_:
        for how, copier in COPIERS.items():
            dup = copier(m)
            where = f"{type(m).__name__} via {how}"
            assert dup == m, where
            assert dup.model_fields_set == m.model_fields_set, where


def test_copy_and_pickle_preserve_models(
    instances: dict[ModelCls, OscalBaseModel], sample_docs: list[BaseModel]
) -> None:
    assert len(instances) == N_OBJECT_MODELS - len(UNCOVERED_CLASSES)
    _assert_copies_equal(_all_models(instances, sample_docs))


def _update_field(cls: ModelCls) -> str | None:
    """An alias-differing field if any, else the first field (None: no fields)."""
    aliased = alias_names(cls)
    return next(iter(aliased or cls.model_fields), None)


@pytest.mark.parametrize("cls", OBJECT_MODELS, ids=lambda c: c.__name__)
def test_model_copy_update_by_name(harvest: Harvest, cls: ModelCls) -> None:
    """``model_copy(update={name: v})`` behaves as on the unfixed tree.

    Observed on the pre-fix tree (origin/main) and unchanged after: the copy's
    attribute is ``v``, ``name`` joins ``model_fields_set``, ``__dict__`` keys
    stay the model's field names, and the original is untouched.
    """
    if cls.__name__ in UNCOVERED_CLASSES:
        pytest.skip(f"{cls.__name__} listed in UNCOVERED_CLASSES")
    inst = harvest.instances[cls]
    name = _update_field(cls)
    if name is None:  # e.g. IncludeAll: an empty-object marker with no fields
        assert inst.model_copy(update={}) == inst
        return
    value = _probe_value(harvest, cls, name)
    before = (getattr(inst, name), set(inst.model_fields_set))
    dup = inst.model_copy(update={name: value})
    where = f"{_where(cls, name)}.model_copy(update=...)"
    assert getattr(dup, name) is value, where
    assert dup.model_fields_set == inst.model_fields_set | {name}, where
    assert set(dup.__dict__) == set(cls.model_fields), where
    assert (getattr(inst, name), set(inst.model_fields_set)) == before, where


class _InitCalledError(AssertionError):
    pass


def test_nothing_but_construction_calls_init(
    monkeypatch: pytest.MonkeyPatch,
    instances: dict[ModelCls, OscalBaseModel],
    sample_docs: list[BaseModel],
) -> None:
    """Copy, pickle, and model_validate* never call OscalBaseModel.__init__."""
    dumped = [
        (type(m), m.model_dump(by_alias=True, exclude_none=True), m.model_dump_json())
        for m in _all_models(instances, sample_docs)
    ]

    def boom(self: object, /, **_data: Any) -> None:
        raise _InitCalledError(type(self).__name__)

    monkeypatch.setattr(OscalBaseModel, "__init__", boom)
    with pytest.raises(_InitCalledError):
        models.Rlink(href="x")  # the patch is live
    try:
        _assert_copies_equal(_all_models(instances, sample_docs))
        for m in instances.values():
            name = _update_field(type(m))
            m.model_copy(update={name: None} if name else {})
        for cls, data, text in dumped:
            cls.model_validate(data)
            cls.model_validate_json(text)
    except _InitCalledError as exc:
        pytest.fail(
            f"OscalBaseModel.__init__ was called for {exc} outside direct "
            f"construction. {RC5}"
        )
