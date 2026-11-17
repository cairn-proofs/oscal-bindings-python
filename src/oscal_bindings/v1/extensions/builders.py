"""Convenience constructors for OSCAL `back-matter` resource elements.

These helpers wrap the underlying Pydantic models with the field idioms
already filled in (UUID4 default, an identifier from a key, kwarg-style
construction, no need to remember the camelCase aliases). Each helper returns a
validated model instance.

Each helper validates a JSON-shaped object with `model_validate` one time, so
the model validates each item of a list input, also an item that the caller
made with `model_construct`. Each helper raises `OscalBuilderError` for each
invalid input. It never raises `pydantic.ValidationError`.
"""

from __future__ import annotations

import contextlib
import uuid as _uuid
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from oscal_bindings.v1.models import (
    BackMatterResource,
    BackMatterResourceRlink,
    DocumentId,
    Hash,
    HashAlgorithm,
)

_M = TypeVar("_M", bound=BaseModel)

#: The namespace of the UUID version 5 that `make_resource` derives from a key.
KEY_NAMESPACE = _uuid.UUID("3942257f-e1cf-5e06-9c6f-eeb97ecabe77")


class OscalBuilderError(ValueError):
    """Raised when an input to a builder is not valid.

    It is not an `OscalParseError`. It is a `ValueError`, so `except ValueError`
    catches it. `errors` holds the structured entries, in the Pydantic entry
    shape (`type`, `loc`, `msg`, `input`). When the failure comes from model
    validation, `__cause__` is the original `pydantic.ValidationError`.
    """

    def __init__(self, message: str, errors: list[Any] | None = None) -> None:
        super().__init__(message)
        self.errors = errors or []


def _key_error(error_type: str, msg: str, value: Any) -> OscalBuilderError:
    entry = {"type": error_type, "loc": ("key",), "msg": msg, "input": value}
    return OscalBuilderError(f"Invalid key: {msg}", [entry])


def _validate(model: type[_M], obj: dict[str, Any]) -> _M:
    try:
        return model.model_validate(obj)
    except ValidationError as exc:
        entries = exc.errors(include_url=False)
        count = len(entries)
        raise OscalBuilderError(
            f"Invalid {model.__name__}: {count} validation "
            f"error{'s' if count != 1 else ''}",
            list(entries),
        ) from exc


def _json_item(item: Any) -> Any:
    """Give a model instance as a JSON-shaped object, and any other item as is."""
    return item.model_dump() if isinstance(item, BaseModel) else item


def _json_list(items: list[Any] | None) -> Any:
    return items if items is None else [_json_item(item) for item in items]


def _compact(**fields: Any) -> dict[str, Any]:
    return {name: value for name, value in fields.items() if value is not None}


def make_hash(
    value: str,
    algorithm: str | HashAlgorithm = HashAlgorithm.SHA_256,
) -> Hash:
    """Build a `Hash` element.

    Args:
        value: The hex-encoded digest.
        algorithm: Either a `HashAlgorithm` enum member or a string. A string
            that is the value of a member (e.g., `"SHA-256"`) gives that
            member. Any other string goes to the model as is, and the model
            accepts it when the schema does (e.g., `"SHA-999"`). Defaults to
            SHA-256.

    Raises:
        OscalBuilderError: if the model rejects the algorithm or the value.
    """
    if isinstance(algorithm, str):
        with contextlib.suppress(ValueError):
            algorithm = HashAlgorithm(algorithm)
    return _validate(Hash, {"algorithm": algorithm, "value": value})


def make_rlink(
    href: str,
    *,
    media_type: str | None = None,
    hashes: list[Hash] | None = None,
) -> BackMatterResourceRlink:
    """Build a `BackMatterResourceRlink` element pointing at an external resource.

    Raises:
        OscalBuilderError: if the model rejects an input, also an item of
            `hashes` that the caller made with `model_construct`.
    """
    return _validate(
        BackMatterResourceRlink,
        _compact(href=href, **{"media-type": media_type}, hashes=_json_list(hashes)),
    )


def make_resource(  # noqa: PLR0913 -- the public signature names each element field
    *,
    title: str | None = None,
    description: str | None = None,
    rlinks: list[BackMatterResourceRlink] | None = None,
    uuid: str | None = None,
    key: str | None = None,
    document_ids: list[DocumentId] | None = None,
) -> BackMatterResource:
    """Build a `BackMatterResource` element for `back-matter.resources`.

    Args:
        title: Optional display title.
        description: Optional short summary.
        rlinks: Optional list of `BackMatterResourceRlink`s pointing at equivalent
            URIs.
        uuid: Resource UUID. When neither `uuid` nor `key` is given, a fresh
            UUID4 is generated.
        key: Optional stable key of the resource, such as a URL. When `key` is
            given and `uuid` is not, the UUID is the UUID version 5 of the
            key in the namespace of the back-matter keys, so the same key
            always gives the same UUID. An empty key, or a key with a `uuid`,
            raises `OscalBuilderError`. See `docs/back-matter-keys.md` in
            https://github.com/cairn-proofs/oscal-bindings-specs.
        document_ids: Optional list of `DocumentId`s recording document
            identities qualified by scheme. Omitted from the resource when
            not provided. Validated like `rlinks`: an empty list or items
            that are not valid `DocumentId`s raise `OscalBuilderError`.

    Raises:
        OscalBuilderError: for an invalid key, or if the model rejects an
            input, also an item of `rlinks` or `document_ids` that the caller
            made with `model_construct`.
    """
    if key is not None:
        if not isinstance(key, str):
            raise _key_error("string_type", "Input should be a valid string", key)
        if uuid is not None:
            raise _key_error(
                "key_with_uuid", "A key and a uuid cannot both be given", key
            )
        if key == "":
            raise _key_error("empty_key", "The key cannot be empty", key)
        uuid = str(_uuid.uuid5(KEY_NAMESPACE, key))
    elif uuid is None:
        uuid = str(_uuid.uuid4())
    return _validate(
        BackMatterResource,
        _compact(
            uuid=uuid,
            title=title,
            description=description,
            rlinks=_json_list(rlinks),
            **{"document-ids": _json_list(document_ids)},
        ),
    )
