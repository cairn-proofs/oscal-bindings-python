"""Property 3: keyword construction accepts field names (Hypothesis).

Task 4.3 of the ``oscal-default-serialization-fix`` spec (#5). Complements the
exhaustive tests in ``tests/test_base_model.py`` with random field values
drawn from the leaf strategies in ``tests/strategies.py``.

**Validates: Requirements 1.6, 2.9**
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError
from strategies import LEAF_ELEMENT_TYPES, leaf_instance_strategy
from support.model_instances import alias_names, kwargs_by_name

from oscal_bindings.v1.models import (
    BackMatterResourceRlink,
    DocumentId,
    Hash,
    Link,
    Property,
)

if TYPE_CHECKING:
    from oscal_bindings.v1._base import OscalBaseModel

LEAF_CLASSES: dict[str, type[OscalBaseModel]] = {
    "hash": Hash,
    "back-matter-resource-rlink": BackMatterResourceRlink,
    "link": Link,
    "property": Property,
    "document-id": DocumentId,
}
assert set(LEAF_CLASSES) == set(LEAF_ELEMENT_TYPES)

# Leaf types with at least one alias-differing field (Rlink, Link, Property).
ALIASED_LEAF_TYPES = tuple(t for t, c in LEAF_CLASSES.items() if alias_names(c))
assert len(ALIASED_LEAF_TYPES) >= 3, ALIASED_LEAF_TYPES

HINT = (
    "By-name keyword construction (2.9) is broken: OscalBaseModel.__init__ must "
    "map Python field names to aliases. See design.md, Fix Implementation "
    "section 3 and Hypothesized Root Cause 5."
)


def _attempt(cls: type[OscalBaseModel], kwargs: dict[str, Any]) -> object:
    """``cls(**kwargs)``, or the `ValidationError` it raised."""
    try:
        return cls(**kwargs)
    except ValidationError as exc:
        return exc


@st.composite
def leaf_draws(
    draw: st.DrawFn, types: tuple[str, ...] = LEAF_ELEMENT_TYPES
) -> tuple[type[OscalBaseModel], dict[str, Any]]:
    """A leaf model class and a valid alias-keyed dict for it."""
    element_type = draw(st.sampled_from(types))
    return LEAF_CLASSES[element_type], draw(leaf_instance_strategy(element_type))


@given(drawn=leaf_draws(), data=st.data())
def test_name_alias_and_mixed_kwargs_agree(
    drawn: tuple[type[OscalBaseModel], dict[str, Any]], data: st.DataObject
) -> None:
    """by-name == by-alias == mixed == model_validate(alias dict).

    **Validates: Requirements 1.6, 2.9**
    """
    cls, alias_dict = drawn
    reference = cls.model_validate(alias_dict)
    by_name_kwargs = kwargs_by_name(reference)
    aliases = alias_names(cls)
    mixed = {
        (aliases.get(n, n) if data.draw(st.booleans(), label=n) else n): v
        for n, v in by_name_kwargs.items()
    }
    where = f"{cls.__name__} with fields {sorted(by_name_kwargs)}"
    by_name = _attempt(cls, by_name_kwargs)
    by_mixed = _attempt(cls, mixed)
    for result in (by_name, by_mixed):
        assert not isinstance(result, ValidationError), (
            f"{where}: name kwargs rejected: {result}. {HINT}"
        )
    by_alias = cls(**alias_dict)
    assert by_name == reference, f"{where}: by-name differs. {HINT}"
    assert by_mixed == reference, f"{where}: mixed {sorted(mixed)} differs. {HINT}"
    assert by_alias == reference, f"{where}: by-alias differs"


@given(drawn=leaf_draws(ALIASED_LEAF_TYPES), data=st.data())
def test_name_and_alias_of_one_field_rejected(
    drawn: tuple[type[OscalBaseModel], dict[str, Any]], data: st.DataObject
) -> None:
    """Supplying both spellings of a drawn field is ``extra_forbidden``.

    **Validates: Requirements 2.9**
    """
    cls, alias_dict = drawn
    aliases = alias_names(cls)
    name = data.draw(st.sampled_from(sorted(aliases)), label="field")
    alias = aliases[name]
    value = alias_dict.get(alias, "x")
    kwargs = {**alias_dict, name: value, alias: value}
    result = _attempt(cls, kwargs)
    assert isinstance(result, ValidationError), (
        f"{cls.__name__}.{name}: name and alias {alias!r} both ACCEPTED; one "
        f"value was silently dropped. See design.md, Fix Implementation 3."
    )
    locs = [tuple(e["loc"]) for e in result.errors() if e["type"] == "extra_forbidden"]
    assert (name,) in locs, (
        f"{cls.__name__}.{name}: name+alias rejected, but not as "
        f"extra_forbidden at {name!r}: {result.errors()}"
    )
