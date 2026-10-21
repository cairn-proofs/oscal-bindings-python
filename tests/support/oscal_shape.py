"""Shared "is this valid OSCAL JSON shape" checks for the serialization tests.

Used by the example-based ``tests/test_serialization_defaults.py`` and the
property-based ``tests/test_prop_serialization_defaults.py`` so both assert
against one schema key set and one table of default serialization paths.

- `schema_property_names`: every ``properties`` key, collected recursively from
  the OSCAL JSON Schema of the pinned spec artifact (computed once, on first
  use, so a fetch failure fails the test that needs it, not collection).
- `oscal_shape_violations` / `assert_valid_oscal_shape`: every ``null`` and
  every key outside `schema_property_names`, at any depth.
- `DEFAULT_PATHS`: the serialization entry points a framework or user may call
  without ``by_alias``/``exclude_none``; each returns the model's own dumped
  tree with any container wrapper removed.
"""

from __future__ import annotations

import functools
import json
from typing import TYPE_CHECKING, Any

import pydantic_core
from pydantic import TypeAdapter

from support.spec_artifact import schema_path

if TYPE_CHECKING:
    from collections.abc import Callable

    from pydantic import BaseModel

CONTAINER_KEY = "k"


def _collect_property_names(node: object, out: set[str]) -> None:
    if isinstance(node, dict):
        props = node.get("properties")
        if isinstance(props, dict):
            out.update(props)
        for value in node.values():
            _collect_property_names(value, out)
    elif isinstance(node, list):
        for value in node:
            _collect_property_names(value, out)


@functools.cache
def schema_property_names() -> frozenset[str]:
    """Every ``properties`` key of the artifact schema, read on first use."""
    names: set[str] = set()
    _collect_property_names(json.loads(schema_path().read_bytes()), names)
    assert names, "no properties found in the artifact schema"
    return frozenset(names)


def oscal_shape_violations(value: object, path: str = "$") -> list[str]:
    """Return every ``null`` and every non-OSCAL key in a dumped model tree."""
    found: list[str] = []
    if value is None:
        found.append(f"{path}: null")
    elif isinstance(value, dict):
        for key, child in value.items():
            if key not in schema_property_names():
                found.append(f"{path}: non-OSCAL key {key!r}")
            found.extend(oscal_shape_violations(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for i, child in enumerate(value):
            found.extend(oscal_shape_violations(child, f"{path}[{i}]"))
    return found


def assert_valid_oscal_shape(value: object, context: str = "") -> None:
    """Fail with the first ten violations (prefixed by ``context``) if any."""
    problems = oscal_shape_violations(value)
    first = "; ".join(problems[:10])
    prefix = f"{context}: " if context else ""
    assert not problems, f"{prefix}{len(problems)} violation(s), first 10: {first}"


# --- Default serialization paths ---------------------------------------------


def _unwrap_list(value: Any) -> Any:
    assert list(value) == [CONTAINER_KEY]
    (item,) = value[CONTAINER_KEY]
    return item


def _path_model_dump(m: BaseModel, kw: dict[str, Any]) -> Any:
    return m.model_dump(**kw)


def _path_model_dump_json_mode(m: BaseModel, kw: dict[str, Any]) -> Any:
    return m.model_dump(mode="json", **kw)


def _path_model_dump_json(m: BaseModel, kw: dict[str, Any]) -> Any:
    return json.loads(m.model_dump_json(**kw))


def _path_to_json(m: BaseModel, kw: dict[str, Any]) -> Any:
    return json.loads(pydantic_core.to_json(m, **kw))


def _path_to_json_container(m: BaseModel, kw: dict[str, Any]) -> Any:
    return _unwrap_list(json.loads(pydantic_core.to_json({CONTAINER_KEY: [m]}, **kw)))


def _path_type_adapter(m: BaseModel, kw: dict[str, Any]) -> Any:
    dumped = TypeAdapter(dict[str, Any]).dump_python(
        {CONTAINER_KEY: m}, mode="json", **kw
    )
    assert list(dumped) == [CONTAINER_KEY]
    return dumped[CONTAINER_KEY]


DEFAULT_PATHS: dict[str, Callable[[BaseModel, dict[str, Any]], Any]] = {
    "model_dump()": _path_model_dump,
    "model_dump(mode=json)": _path_model_dump_json_mode,
    "model_dump_json()": _path_model_dump_json,
    "to_json(m)": _path_to_json,
    "to_json({k: [m]})": _path_to_json_container,
    "TypeAdapter.dump_python({k: m})": _path_type_adapter,
}
