"""OSCAL Python data bindings — top-level re-export of :mod:`oscal_bindings.v1`.

The implementation lives in the major-version package :mod:`oscal_bindings.v1`.
This module defines no symbols of its own: it re-exports that package's public
surface so callers can use the shorter ``oscal_bindings`` path, and it
star-imports :mod:`oscal_bindings.v1.models` so every generated model name is
importable directly from ``oscal_bindings``.

Because these are re-exports rather than wrappers, a name reached through this
module is the *same object* as the one reached through :mod:`oscal_bindings.v1`,
so ``isinstance`` agrees regardless of which path a class came from.

``__all__`` is taken from :attr:`oscal_bindings.v1.__all__` rather than
restated, so the two surfaces cannot drift apart.

New code should prefer the explicit path::

    >>> from oscal_bindings.v1 import parse_oscal_file, serialize_oscal

The top-level path is equivalent::

    >>> from oscal_bindings import parse_oscal_file, serialize_oscal
    >>> doc = parse_oscal_file("catalog.json")
    >>> json_str = serialize_oscal(doc)

See :mod:`oscal_bindings.v1` for the documented API surface and
``__oscal_schema_version__`` for the exact OSCAL release the models were
generated from.
"""

from typing import Any

from oscal_bindings import v1 as _v1

# Not in ``v1.__all__`` (it is metadata, not API), so re-exported explicitly.
from oscal_bindings.v1 import __oscal_schema_version__ as __oscal_schema_version__

# Generated model names: star-imported from the models module directly rather
# than from ``oscal_bindings.v1``, both for provenance (the names visibly come
# from where they are defined) and because ``oscal_bindings.v1`` defines
# ``__all__``, which would bound the star-import to the curated surface and drop
# the ~180 model names this line exists to carry.
from oscal_bindings.v1.models import *  # noqa: F403

# The curated public surface, bounded by ``oscal_bindings.v1.__all__``.
#
# Not a plain ``from oscal_bindings.v1 import *``: that forces every name in
# ``v1.__all__`` at import time, which would eagerly resolve the lazy YAML
# re-exports and so require PyYAML just to ``import oscal_bindings``. The YAML
# names are re-exported lazily through ``__getattr__`` instead, so the base
# install imports without the ``yaml`` extra (design Decision 5).
_LAZY_YAML = frozenset(
    {"parse_oscal_yaml", "parse_oscal_yaml_file", "serialize_oscal_yaml"}
)
for _name in _v1.__all__:
    if _name not in _LAZY_YAML:
        globals()[_name] = getattr(_v1, _name)

__all__ = list(_v1.__all__)


def __getattr__(name: str) -> Any:
    """Lazily re-export the optional YAML operations from :mod:`oscal_bindings.v1`.

    Accessing one triggers the PyYAML import in ``yaml_io``; without the ``yaml``
    extra that raises :class:`ImportError` with an install hint.
    """
    if name in _LAZY_YAML:
        return getattr(_v1, name)
    message = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(message)
