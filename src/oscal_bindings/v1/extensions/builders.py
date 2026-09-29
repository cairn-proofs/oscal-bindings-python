"""Convenience constructors for OSCAL `back-matter` resource elements.

These helpers wrap the underlying Pydantic models with the field idioms
already filled in (UUID4 default, kwarg-style construction, no need to
remember the camelCase aliases). Each helper returns a validated model
instance and raises `pydantic.ValidationError` on invalid input.
"""

from __future__ import annotations

import uuid as _uuid

from oscal_bindings.v1.models import Algorithm, DocumentId, Hash, Resource, Rlink


def make_hash(
    value: str,
    algorithm: str | Algorithm = Algorithm.SHA_256,
) -> Hash:
    """Build a `Hash` element.

    Args:
        value: The hex-encoded digest.
        algorithm: Either an `Algorithm` enum member or its string value
            (e.g., `"SHA-256"`). Defaults to SHA-256.
    """
    if isinstance(algorithm, str):
        algorithm = Algorithm(algorithm)
    return Hash(algorithm=algorithm, value=value)


def make_rlink(
    href: str,
    *,
    media_type: str | None = None,
    hashes: list[Hash] | None = None,
) -> Rlink:
    """Build an `Rlink` element pointing at an external resource."""
    return Rlink.model_validate(
        {
            "href": href,
            "media-type": media_type,
            "hashes": hashes,
        }
    )


def make_resource(
    *,
    title: str | None = None,
    description: str | None = None,
    rlinks: list[Rlink] | None = None,
    uuid: str | None = None,
    document_ids: list[DocumentId] | None = None,
) -> Resource:
    """Build a `Resource` element for inclusion in `back-matter.resources`.

    Args:
        title: Optional display title.
        description: Optional short summary.
        rlinks: Optional list of `Rlink`s pointing at equivalent URIs.
        uuid: Resource UUID. A fresh UUID4 is generated if not provided.
        document_ids: Optional list of `DocumentId`s recording document
            identities qualified by scheme. Omitted from the resource when
            not provided.
    """
    resource = Resource(
        uuid=uuid if uuid is not None else str(_uuid.uuid4()),
        title=title,
        description=description,
        rlinks=rlinks,
    )
    if document_ids is not None:
        # `Resource.document_ids` carries a differing alias (`document-ids`) and
        # the model forbids extras / does not populate-by-name, so it cannot be
        # set via the constructor kwarg. Assign post-construction (validation is
        # on the typed `list[DocumentId]` we already hold).
        resource.document_ids = document_ids
    return resource
