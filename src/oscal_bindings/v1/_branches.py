"""Selection of the nested-union branch in validation failures (PRS-014).

An object that holds the distinguishing property of exactly one branch of a
nested union selects that branch. Each entry for a failure of the object is a
failure of that branch, so the entries of the other branches are dropped. Both
the parsers and ``validate_element`` use this module.
"""

from __future__ import annotations

import functools
import types
from typing import TYPE_CHECKING, Any, get_args

from pydantic import BaseModel

from oscal_bindings.v1 import models as _models

if TYPE_CHECKING:
    from collections.abc import Callable


@functools.cache
def branch_properties() -> dict[str, dict[str, str]]:
    """Map each nested-union branch class name to the properties of its union.

    The value is a map of every branch name of the union to its distinguishing
    property: the one OSCAL property that only that branch defines. The
    manifest records the same property, and a test compares the two. A union
    in which a branch has no such property, or more than one, is left out, so
    no object selects a branch of it and every entry of it is kept.
    """
    unions: dict[str, dict[str, str]] = {}
    for value in vars(_models).values():
        if not isinstance(value, types.UnionType):
            continue
        branches = get_args(value)
        if not branches[1:] or not all(
            isinstance(b, type) and issubclass(b, BaseModel) for b in branches
        ):
            continue
        names = [
            {f.alias or key for key, f in b.model_fields.items()} for b in branches
        ]
        properties: dict[str, str] = {}
        for branch, own in zip(branches, names, strict=True):
            unique = own.difference(*(o for o in names if o is not own))
            if len(unique) == 1:
                properties[branch.__name__] = next(iter(unique))
        if len(properties) == len(branches):
            for branch in branches:
                unions[branch.__name__] = properties
    return unions


def select_branch_errors(errors: list[Any], load_input: Callable[[], Any]) -> list[Any]:
    """Keep only the entries of the selected nested-union branch (PRS-014).

    ``errors`` are Pydantic entries. ``load_input`` returns the validated
    value as a JSON-shaped object and is called only when an entry passes
    through a branch. An entry whose location passes through a branch that an
    object does not select is dropped. An object that holds none, or more than
    one, distinguishing property keeps the entries of every branch. A
    ``load_input`` that raises ``ValueError`` or ``RecursionError`` (a JSON
    text deeper than the recursion limit of the JSON module) keeps every entry.
    """
    branches = branch_properties()
    if not any(
        isinstance(part, str) and part in branches
        for entry in errors
        for part in entry["loc"]
    ):
        return errors
    try:
        node = load_input()
    except (ValueError, RecursionError):
        return errors
    kept = []
    for entry in errors:
        current: Any = node
        selected = True
        for part in entry["loc"]:
            if isinstance(current, dict) and part in branches and part not in current:
                held = [b for b, prop in branches[part].items() if prop in current]
                if len(held) == 1 and held[0] != part:
                    selected = False
                    break
            elif isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, list) and isinstance(part, int):
                current = current[part] if 0 <= part < len(current) else None
            # Any other part is a tag of the document union.
        if selected:
            kept.append(entry)
    return kept
