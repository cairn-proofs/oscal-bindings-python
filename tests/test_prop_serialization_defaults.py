"""Property 1 (fix checking): default serialization paths emit valid OSCAL.

Two sources of models, the same invariants:

- **Corpus documents** (``all_corpus_docs``): bare ``doc.model_dump_json()``
  and ``pydantic_core.to_json(doc)`` both equal ``serialize_oscal(doc)``
  semantically, and the dumped tree has no ``null`` and only OSCAL schema keys.
- **Leaf models** (``tests/strategies.py``): a drawn allow-listed leaf is
  rebuilt by keyword with each optional field independently left unset, kept
  at a drawn value, or set to an explicit ``None``. Every default path
  (``model_dump``, ``model_dump(mode="json")``, ``model_dump_json``,
  ``to_json(m)``, ``to_json({"k": [m]})``, ``TypeAdapter.dump_python``) emits
  no ``null``, only schema keys, and exactly the aliases of the non-``None``
  fields.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.7**
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pydantic_core
from hypothesis import given
from hypothesis import strategies as st
from strategies import LEAF_ELEMENT_TYPES, leaf_instance_strategy
from support.oscal_shape import DEFAULT_PATHS, assert_valid_oscal_shape

from oscal_bindings import parse_oscal, serialize_oscal
from oscal_bindings.v1.models import (
    BackMatterResourceRlink,
    DocumentId,
    Hash,
    Link,
    Property,
)

if TYPE_CHECKING:
    from pydantic import BaseModel
    from support.corpus import CorpusDoc

LEAF_MODELS: dict[str, type[BaseModel]] = {
    "hash": Hash,
    "back-matter-resource-rlink": BackMatterResourceRlink,
    "link": Link,
    "property": Property,
    "document-id": DocumentId,
}
assert set(LEAF_MODELS) == set(LEAF_ELEMENT_TYPES)

BY_ALIAS_KWARGS: list[dict[str, Any]] = [{}, {"by_alias": True}]

# What to do with each optional field of a drawn leaf.
_UNSET, _KEEP, _NONE = "unset", "keep", "none"


# --- Corpus documents --------------------------------------------------------


@given(data=st.data())
def test_corpus_default_paths_equal_serialize_oscal(
    all_corpus_docs: list[CorpusDoc], data: st.DataObject
) -> None:
    """Bare ``model_dump_json`` and ``to_json`` match ``serialize_oscal`` (2.1-2.3)."""
    corpus_doc = data.draw(st.sampled_from(all_corpus_docs), label="doc")
    where = f"{corpus_doc.corpus_name}:{corpus_doc.rel_path}"
    doc = parse_oscal(corpus_doc.raw_bytes)
    expected = json.loads(serialize_oscal(doc))

    dumped = json.loads(doc.model_dump_json())
    assert dumped == expected, f"{where}: model_dump_json() != serialize_oscal"
    assert json.loads(pydantic_core.to_json(doc)) == expected, (
        f"{where}: pydantic_core.to_json != serialize_oscal"
    )
    assert_valid_oscal_shape(dumped, where)


# --- Leaf models with optional fields unset / valued / None ------------------


@st.composite
def leaf_models_with_nones(draw: st.DrawFn) -> BaseModel:
    """A leaf model built by name, each optional field unset, valued, or None."""
    element_type = draw(st.sampled_from(LEAF_ELEMENT_TYPES), label="type")
    cls = LEAF_MODELS[element_type]
    template = cls.model_validate(draw(leaf_instance_strategy(element_type)))
    kwargs: dict[str, Any] = {}
    for name, field in cls.model_fields.items():
        value = getattr(template, name)
        if field.is_required():
            kwargs[name] = value
            continue
        choice = draw(st.sampled_from([_UNSET, _KEEP, _NONE]), label=name)
        if choice == _NONE or (choice == _KEEP and value is None):
            kwargs[name] = None
        elif choice == _KEEP:
            kwargs[name] = value
    return cls(**kwargs)


def _expected_top_keys(m: BaseModel) -> set[str]:
    return {
        field.alias or name
        for name, field in type(m).model_fields.items()
        if getattr(m, name) is not None
    }


@given(
    m=leaf_models_with_nones(),
    path=st.sampled_from(list(DEFAULT_PATHS)),
    kw=st.sampled_from(BY_ALIAS_KWARGS),
)
def test_leaf_default_paths_emit_oscal_keys_and_no_nulls(
    m: BaseModel, path: str, kw: dict[str, Any]
) -> None:
    """Explicit/implicit None never reach output; keys are aliases (2.1-2.4, 2.7)."""
    dumped = DEFAULT_PATHS[path](m, kw)
    where = f"{type(m).__name__} via {path} {kw}"
    assert_valid_oscal_shape(dumped, where)
    assert isinstance(dumped, dict), where
    assert set(dumped) == _expected_top_keys(m), where
