"""Property tests for the back-matter builders (Property 7, Req 8).

Feature: property-based-tests, Property 7: builders produce schema-valid
back-matter. *For any* Hypothesis-generated inputs to `make_hash`,
`make_rlink`, or `make_resource`, the produced element re-validates against its
own model.

One `@given` test per builder so each of Req 8.1 / 8.2 / 8.3 fails (and
reports its counterexample) on its own. Each test checks two re-validations:

- **Python mode** — ``model_dump(by_alias=True, exclude_none=True)`` fed back
  through ``model_validate`` reproduces an equal element. This matters most
  for `make_resource`, which assigns ``document_ids`` post-construction on a
  model without ``validate_assignment``: the re-validation is what proves the
  assigned value is schema-valid.
- **JSON mode** — the element's JSON text re-validates via
  ``model_validate_json`` and dumps back to the identical JSON. This is the
  wire-level "schema-valid" check. It compares JSON, not model equality,
  because `Hash.algorithm` is typed ``StringDatatype | Algorithm``: a
  JSON ``"SHA-256"`` string re-validates as the plain-string arm, not the
  enum member, so the models can differ in Python type while agreeing on the
  wire.

Inputs come from `strategies` (builder kwargs only; no full documents,
Req 8.4). Example counts come from the active Hypothesis profile
(`ci`: ``max_examples=100``) registered in `tests/conftest.py`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hypothesis import given
from strategies import hash_strategy, resource_strategy, rlink_strategy

from oscal_bindings import make_hash, make_resource, make_rlink
from oscal_bindings.v1.models import Algorithm

if TYPE_CHECKING:
    from pydantic import BaseModel


def _assert_revalidates(element: BaseModel) -> None:
    """Assert ``element`` re-validates against its own model (both modes)."""
    model_cls = type(element)

    dumped = element.model_dump(by_alias=True, exclude_none=True)
    assert model_cls.model_validate(dumped) == element

    wire = element.model_dump_json(by_alias=True, exclude_none=True)
    reparsed = model_cls.model_validate_json(wire)
    assert reparsed.model_dump_json(by_alias=True, exclude_none=True) == wire


# Feature: property-based-tests, Property 7: builders produce schema-valid
# back-matter (make_hash)
@given(hash_strategy())
def test_make_hash_produces_schema_valid_hash(kwargs: dict[str, Any]) -> None:
    """**Validates: Requirements 8.1**"""
    element = make_hash(**kwargs)

    _assert_revalidates(element)
    assert element.value == kwargs["value"]
    # The builder coerces a string algorithm to the (plain, non-str) enum;
    # an omitted algorithm exercises the SHA-256 default.
    expected = Algorithm(kwargs.get("algorithm", Algorithm.SHA_256))
    assert element.algorithm is expected


# Feature: property-based-tests, Property 7: builders produce schema-valid
# back-matter (make_rlink)
@given(rlink_strategy())
def test_make_rlink_produces_schema_valid_rlink(kwargs: dict[str, Any]) -> None:
    """**Validates: Requirements 8.2**"""
    element = make_rlink(**kwargs)

    _assert_revalidates(element)
    assert element.href == kwargs["href"]
    assert element.media_type == kwargs.get("media_type")
    assert element.hashes == kwargs.get("hashes")


# Feature: property-based-tests, Property 7: builders produce schema-valid
# back-matter (make_resource)
@given(resource_strategy())
def test_make_resource_produces_schema_valid_resource(
    kwargs: dict[str, Any],
) -> None:
    """**Validates: Requirements 8.3**"""
    element = make_resource(**kwargs)

    _assert_revalidates(element)
    for field in ("title", "description", "rlinks", "document_ids"):
        assert getattr(element, field) == kwargs.get(field)
    if "uuid" in kwargs:
        assert element.uuid == kwargs["uuid"]
    else:
        # Omitted uuid exercises the UUID4 default, which must itself be valid.
        assert element.uuid
