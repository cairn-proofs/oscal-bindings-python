"""Property-based tests for `validate_element` (Requirement 9).

Property 8 exercises the documented `LEAF_ELEMENT_TYPES` allow-list from
``tests/strategies.py``: flat, non-recursive leaf types whose instances
Hypothesis can generate cheaply. Extending coverage to the remaining
supported element types is a bounded follow-on: add the name to
`LEAF_ELEMENT_TYPES`, a field strategy in ``strategies.py``, and the model
class to `_LEAF_MODELS` below.

Property 9 checks that any element type name outside
`get_supported_element_types()` is rejected with `OscalParseError`.

Example counts come from the ``ci`` Hypothesis profile registered in
``tests/conftest.py`` (``max_examples=100``); no per-test ``@settings``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from hypothesis import given
from hypothesis import strategies as st
from strategies import LEAF_ELEMENT_TYPES, leaf_instance_strategy

from oscal_bindings.v1 import (
    OscalParseError,
    get_supported_element_types,
    validate_element,
)
from oscal_bindings.v1.models import DocumentId, Hash, Link, Property, Rlink

if TYPE_CHECKING:
    from pydantic import BaseModel

# `validate_element` exposes no public type-name -> model-class lookup, so the
# round-trip check maps each allow-listed name to its public model class
# explicitly rather than reaching into the private `_ELEMENT_MAP`.
_LEAF_MODELS: dict[str, type[BaseModel]] = {
    "hash": Hash,
    "rlink": Rlink,
    "link": Link,
    "property": Property,
    "document-id": DocumentId,
}

_SUPPORTED: frozenset[str] = frozenset(get_supported_element_types())


def _dump(model: BaseModel) -> dict[str, Any]:
    # Python-mode dump, matching how `leaf_instance_strategy` builds its dicts.
    # JSON mode is avoided: it stringifies enum members (e.g. "SHA-256"), which
    # re-validate to a differently-typed value and break equality.
    return model.model_dump(by_alias=True, exclude_none=True)


def test_leaf_models_cover_allow_list() -> None:
    assert set(_LEAF_MODELS) == set(LEAF_ELEMENT_TYPES)


@pytest.mark.parametrize("element_type", LEAF_ELEMENT_TYPES)
@given(data=st.data())
def test_validate_element_round_trips_leaf_types(
    element_type: str, data: st.DataObject
) -> None:
    """Feature: property-based-tests, Property 8: `validate_element` round-trips
    allow-listed leaf types.

    **Validates: Requirements 9.1, 9.2**
    """
    # Req 9.1: the allow-list is drawn from the validator's supported types.
    assert element_type in _SUPPORTED

    element = data.draw(leaf_instance_strategy(element_type), label="element")

    result = validate_element(element, element_type)
    assert result.valid, result.errors
    assert result.errors is None

    # Req 9.2: the validated value round-trips back to an equivalent value.
    model_cls = _LEAF_MODELS[element_type]
    validated = model_cls.model_validate(element)
    redumped = _dump(validated)
    assert redumped == element
    assert model_cls.model_validate(redumped) == validated


# Mix arbitrary text with kebab-case names so unknown-but-plausible type names
# (e.g. "back-matterx", "foo-bar") are exercised, not just random Unicode.
_kebab_names = st.from_regex(r"[a-z]{1,12}(-[a-z]{1,12}){0,3}", fullmatch=True)
_unknown_type_names = st.one_of(st.text(), _kebab_names).filter(
    lambda name: name not in _SUPPORTED
)


@given(
    element_type=_unknown_type_names,
    element=st.one_of(
        st.none(),
        st.dictionaries(st.text(max_size=8), st.text(max_size=8), max_size=3),
    ),
)
def test_validate_element_rejects_unknown_types(
    element_type: str, element: dict[str, Any] | None
) -> None:
    """Feature: property-based-tests, Property 9: `validate_element` rejects
    unknown element types.

    **Validates: Requirements 9.3**
    """
    with pytest.raises(OscalParseError):
        validate_element(element, element_type)
