"""Synthetic Hypothesis strategies for the property-based test suite.

Two families of strategies live here, and nothing else:

- **Builder kwargs** (`hash_strategy`, `rlink_strategy`, `resource_strategy`):
  each draws a ``dict`` of keyword arguments for the matching back-matter
  builder (`make_hash`, `make_rlink`, `make_resource`).
- **Leaf element dicts** (`leaf_instance_strategy`): each draws a
  validator-ready, alias-keyed ``dict`` for one allow-listed leaf element type
  (`LEAF_ELEMENT_TYPES`).

No strategy here ever synthesizes a full OSCAL document; whole documents come
only from the commit-pinned corpora (Req 8.4, 9.4).

Generated values satisfy the generated models' constraints by construction
(rather than by ``from_regex`` + filtering, which is slow):

- "StringDatatype"-style fields (``^\\S(.*\\S)?$``) are built as
  single-space-joined words drawn from an alphabet with no whitespace or
  control characters, so they can never start/end with whitespace or contain
  a newline.
- Token fields (``^(\\p{L}|_)(\\p{L}|\\p{N}|[.\\-_])*$``) use a conservative
  ASCII-plus-a-few-Latin alphabet, so the check does not depend on Python and
  the Rust regex engine agreeing on a Unicode version.
- UUIDs are version 4 or 5, matching the OSCAL UUID pattern.
- URLs are assembled from safe components (``https://<host>/<path>``).
"""

from __future__ import annotations

import string
from typing import Any

from hypothesis import strategies as st

from oscal_bindings.v1.models import (
    Algorithm,
    DocumentId,
    Hash,
    Link,
    Property,
    Rel,
    Rlink,
    Scheme2,
)

__all__ = [
    "LEAF_ELEMENT_TYPES",
    "hash_strategy",
    "leaf_instance_strategy",
    "resource_strategy",
    "rlink_strategy",
]

# ---------------------------------------------------------------------------
# Primitive building blocks
# ---------------------------------------------------------------------------

# Printable characters with no whitespace (Z*), controls (Cc) or surrogates
# (Cs). Joining words drawn from this alphabet with single ASCII spaces yields
# a non-empty string with no leading/trailing whitespace and no newline.
_WORD_CHARS = st.characters(
    codec="utf-8",
    exclude_categories=("Cc", "Cs", "Zs", "Zl", "Zp"),
)
_word = st.text(alphabet=_WORD_CHARS, min_size=1, max_size=12)

#: Non-empty, trimmed, single-line text (satisfies ``^\S(.*\S)?$`` and
#: ``^[^\n]+$``).
trimmed_text = st.lists(_word, min_size=1, max_size=5).map(" ".join)

_TOKEN_START = string.ascii_letters + "_" + "éßΩ"
_TOKEN_REST = _TOKEN_START + string.digits + ".-"

#: XML NCName-style OSCAL token (``^(\p{L}|_)(\p{L}|\p{N}|[.\-_])*$``).
tokens = st.builds(
    lambda head, tail: head + tail,
    st.sampled_from(_TOKEN_START),
    st.text(alphabet=_TOKEN_REST, max_size=20),
)

#: Hex-encoded digests.
hex_digests = st.text(alphabet="0123456789abcdef", min_size=1, max_size=128)

#: `Algorithm` enum members.
algorithm_members = st.sampled_from(list(Algorithm))

#: `Algorithm` members or their string values (`make_hash` accepts both).
algorithms = algorithm_members | algorithm_members.map(lambda a: a.value)

_HOST_LABEL = st.text(
    alphabet=string.ascii_lowercase + string.digits, min_size=1, max_size=12
)
_PATH_SEGMENT = st.text(
    alphabet=string.ascii_letters + string.digits + "-._~", min_size=1, max_size=12
)

#: Absolute http(s) URLs, e.g. ``https://ab.example/x/y.json``.
hrefs = st.builds(
    lambda scheme, labels, segments: (
        f"{scheme}://{'.'.join(labels)}.example/" + "/".join(segments)
    ),
    st.sampled_from(["http", "https"]),
    st.lists(_HOST_LABEL, min_size=1, max_size=3),
    st.lists(_PATH_SEGMENT, max_size=4),
)

_MEDIA_TYPE_VALUES = [
    "application/json",
    "application/xml",
    "application/pdf",
    "text/xml",
    "text/plain",
    "text/html",
]

#: Concrete media types (satisfy the ``^\S(.*\S)?$`` pattern on `Link`).
media_type_values = st.sampled_from(_MEDIA_TYPE_VALUES)

#: Optional media types (``None`` included).
media_types = st.none() | media_type_values

#: OSCAL UUIDs (version 4 or 5), as strings.
uuids = (st.uuids(version=4) | st.uuids(version=5)).map(str)


def _alias_dict(
    required: dict[str, st.SearchStrategy[Any]],
    optional: dict[str, st.SearchStrategy[Any]] | None = None,
) -> st.SearchStrategy[dict[str, Any]]:
    """Fixed dict where each optional key is either omitted or present."""
    return st.fixed_dictionaries(required, optional=optional or {})


# ---------------------------------------------------------------------------
# Model-instance strategies (used as nested builder arguments)
# ---------------------------------------------------------------------------

#: `Hash` instances.
hash_models = st.builds(Hash, algorithm=algorithm_members, value=hex_digests)

#: `Rlink` instances (built via alias because `media-type` is aliased and the
#: model does not populate by name).
rlink_models = _alias_dict(
    {"href": hrefs},
    {
        "media-type": media_type_values,
        "hashes": st.lists(hash_models, min_size=1, max_size=3),
    },
).map(Rlink.model_validate)

#: Document-id schemes: the enumerated DOI scheme or an arbitrary URI.
document_id_schemes = st.sampled_from(list(Scheme2)) | hrefs

#: `DocumentId` instances.
document_id_models = _alias_dict(
    {"identifier": trimmed_text},
    {"scheme": document_id_schemes},
).map(DocumentId.model_validate)


# ---------------------------------------------------------------------------
# Builder kwargs strategies (Req 8)
# ---------------------------------------------------------------------------


def hash_strategy() -> st.SearchStrategy[dict[str, Any]]:
    """Kwargs for `make_hash`: ``value`` always, ``algorithm`` optionally.

    ``algorithm`` is an `Algorithm` member or its string value; omitting it
    exercises the builder's SHA-256 default.
    """
    return _alias_dict({"value": hex_digests}, {"algorithm": algorithms})


def rlink_strategy() -> st.SearchStrategy[dict[str, Any]]:
    """Kwargs for `make_rlink`: ``href`` always; ``media_type``/``hashes`` optionally.

    Uses the Python kwarg name ``media_type`` (the builder maps it onto the
    ``media-type`` alias). ``media_type`` may be explicitly ``None``.
    """
    return _alias_dict(
        {"href": hrefs},
        {
            "media_type": media_types,
            "hashes": st.none() | st.lists(hash_models, min_size=1, max_size=3),
        },
    )


def resource_strategy() -> st.SearchStrategy[dict[str, Any]]:
    """Kwargs for `make_resource`; every key is optional.

    ``title`` is single-line; ``rlinks``/``document_ids`` are non-empty lists
    of model instances (the model requires ``min_length=1``); ``uuid`` is a
    v4/v5 UUID string. Omitting ``uuid`` exercises the builder's UUID4
    default.
    """
    return _alias_dict(
        {},
        {
            "title": trimmed_text,
            "description": trimmed_text,
            "rlinks": st.lists(rlink_models, min_size=1, max_size=3),
            "uuid": uuids,
            "document_ids": st.lists(document_id_models, min_size=1, max_size=3),
        },
    )


# ---------------------------------------------------------------------------
# validate_element leaf types (Req 9)
# ---------------------------------------------------------------------------

# `get_supported_element_types()` returns the kebab-case name of EVERY
# BaseModel subclass in models.py (~187), including full document bodies
# (e.g. "catalog", "system-security-plan") and deeply nested / recursive
# composite types. Generating instances of all of them would be a
# combinatorial blow-up and would stall on recursive, heavily constrained
# models. Property 8 therefore exercises this explicit allow-list of simple,
# flat, non-recursive leaf types. Each name is checked against
# `get_supported_element_types()` by the Property 8 test module. ("prop" is
# NOT a supported name: the model class is `Property` -> "property".)
# Extending coverage to more supported types is a bounded follow-on: add the
# name here and a matching entry in `_LEAF_FIELD_STRATEGIES`.
LEAF_ELEMENT_TYPES: tuple[str, ...] = (
    "hash",  # Hash: {algorithm, value}
    "rlink",  # Rlink: {href, media-type?, hashes?}
    "link",  # Link: {href, rel?, media-type?, resource-fragment?, text?}
    "property",  # Property: {name, value, uuid?, ns?, class?, group?, remarks?}
    "document-id",  # DocumentId: {identifier, scheme?}
)

_FieldStrategy = st.SearchStrategy[dict[str, Any]]

# element type -> (model class, alias-keyed field strategy)
_LEAF_FIELD_STRATEGIES: dict[str, tuple[type[Any], _FieldStrategy]] = {
    "hash": (
        Hash,
        _alias_dict({"algorithm": algorithm_members, "value": hex_digests}),
    ),
    "rlink": (
        Rlink,
        _alias_dict(
            {"href": hrefs},
            {
                "media-type": media_type_values,
                "hashes": st.lists(hash_models, min_size=1, max_size=3),
            },
        ),
    ),
    "link": (
        Link,
        _alias_dict(
            {"href": hrefs},
            {
                "rel": tokens | st.sampled_from(list(Rel)),
                "media-type": media_type_values,
                "resource-fragment": _PATH_SEGMENT,
                "text": trimmed_text,
            },
        ),
    ),
    "property": (
        Property,
        _alias_dict(
            {"name": tokens, "value": trimmed_text},
            {
                "uuid": uuids,
                "ns": hrefs,
                "class": tokens,
                "group": tokens,
                "remarks": trimmed_text,
            },
        ),
    ),
    "document-id": (
        DocumentId,
        _alias_dict({"identifier": trimmed_text}, {"scheme": document_id_schemes}),
    ),
}

assert set(_LEAF_FIELD_STRATEGIES) == set(LEAF_ELEMENT_TYPES)


def leaf_instance_strategy(element_type: str) -> st.SearchStrategy[dict[str, Any]]:
    """Validator-ready dict for one allow-listed leaf ``element_type``.

    Constructs the mapped Pydantic model via ``model_validate`` over
    alias-keyed generated values (models forbid extras and do not populate by
    name), then returns ``model_dump(by_alias=True, exclude_none=True)``.

    Raises:
        ValueError: If ``element_type`` is not in `LEAF_ELEMENT_TYPES`.
    """
    if element_type not in _LEAF_FIELD_STRATEGIES:
        msg = (
            f"{element_type!r} is not an allow-listed leaf type; "
            f"expected one of {LEAF_ELEMENT_TYPES}"
        )
        raise ValueError(msg)
    model_cls, fields = _LEAF_FIELD_STRATEGIES[element_type]
    return fields.map(
        lambda data: model_cls.model_validate(data).model_dump(
            by_alias=True, exclude_none=True
        )
    )
