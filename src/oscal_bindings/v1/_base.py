"""Hand-written base class for every generated OSCAL object model.

`datamodel-codegen --base-class` makes each generated object model in
`oscal_bindings.v1.models` inherit from `OscalBaseModel`. The two `RootModel`s
(`OscalDocument`, `MappingCollectionMappings`) don't; their serialization
delegates to children that do. The base gives every model valid OSCAL output by default:

- Serialization uses OSCAL (alias) keys on every path: `model_dump*()`,
  `pydantic_core.to_json`, and `TypeAdapter.dump_*`. Pass `by_alias=False`
  to get Python field names instead.
- None-valued fields are always omitted, because OSCAL forbids `null`.
  `exclude_none=False` has no effect.
- Keyword construction accepts Python field names as well as aliases, e.g.
  `BackMatterResourceRlink(href=..., media_type=...)`. Validation
  (`model_validate*`, the parse functions) stays alias-only.

This module imports only `pydantic` and the standard library so that
`models.py -> _base` can't form an import cycle.
"""

from __future__ import annotations

import functools
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    SerializerFunctionWrapHandler,
    model_serializer,
)


@functools.cache
def _kwarg_aliases(cls: type[BaseModel]) -> dict[str, str]:
    """Map Python field name -> alias for each alias-differing field of `cls`.

    Computed lazily on first construction, so classes completed later via
    `model_rebuild()` are handled. A name that is also some field's alias is
    left out: mapping it would be ambiguous.
    """
    fields = cls.model_fields
    all_aliases = {f.alias for f in fields.values() if f.alias is not None}
    return {
        name: f.alias
        for name, f in fields.items()
        if f.alias is not None and f.alias != name and name not in all_aliases
    }


class OscalBaseModel(BaseModel):
    """Base for generated OSCAL object models: alias keys, no nulls, by-name kwargs.

    Subclass configs (`extra='forbid'`) merge with this one. Constructor kwargs
    may use Python field names or aliases; passing both for the same field is
    rejected as `extra_forbidden`. Plain dicts nested inside kwargs, and all
    `model_validate*` input, must use aliases.
    """

    # Don't add validate_by_name / validate_by_alias / populate_by_name: they
    # make name-keyed input valid for every model_validate* call that doesn't
    # pass by_name=False, including user calls (design.md, Root Cause 4).
    model_config = ConfigDict(serialize_by_alias=True)

    def __init__(self, /, **data: Any) -> None:
        for name, alias in _kwarg_aliases(type(self)).items():
            # If the alias is also present, keep the name so extra='forbid'
            # rejects it instead of silently picking one value.
            if name in data and alias not in data:
                data[alias] = data.pop(name)
        super().__init__(**data)

    # Keep pydantic from treating this as a custom __init__. Without the
    # marker, pydantic sets __pydantic_custom_init__ = True and routes
    # model_validate* (dict and JSON) through __init__, which would accept and
    # populate name-keyed OSCAL input at every depth. RootModel.__init__ uses
    # the same marker (design.md, Root Cause 5).
    __init__.__pydantic_base_init__ = True  # type: ignore[attr-defined]

    # No return annotation on purpose: pydantic derives the serialization JSON
    # schema from it, and `-> Any` collapses model_json_schema(mode="serialization")
    # to an empty schema.
    @model_serializer(mode="wrap")
    def _omit_none(self, handler: SerializerFunctionWrapHandler):
        data = handler(self)
        if type(data) is dict:
            return {k: v for k, v in data.items() if v is not None}
        return data
