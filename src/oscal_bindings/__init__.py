"""OSCAL Python data bindings — compatibility shim over :mod:`oscal_bindings.v1`.

The implementation lives in the major-version package :mod:`oscal_bindings.v1`.
This module defines no symbols of its own: it re-exports that package's public
surface so the flat import paths that predate the ``v1`` namespace keep working
unchanged, and it star-imports :mod:`oscal_bindings.v1.models` so every
generated model name remains importable directly from ``oscal_bindings``.

Because these are re-exports rather than wrappers, a name reached through this
module is the *same object* as the one reached through :mod:`oscal_bindings.v1`,
so ``isinstance`` agrees regardless of which path a class came from.

``__all__`` is taken from :attr:`oscal_bindings.v1.__all__` rather than
restated, so the two surfaces cannot drift apart.

New code should prefer the explicit path::

    >>> from oscal_bindings.v1 import parse_oscal_file, serialize_oscal

The flat path stays supported::

    >>> from oscal_bindings import parse_oscal_file, serialize_oscal
    >>> doc = parse_oscal_file("catalog.json")
    >>> json_str = serialize_oscal(doc)

See :mod:`oscal_bindings.v1` for the documented API surface and
``__oscal_schema_version__`` for the exact OSCAL release the models were
generated from.
"""

from oscal_bindings import v1 as _v1

# The curated public surface, bounded by ``oscal_bindings.v1.__all__``.
from oscal_bindings.v1 import *  # noqa: F403

# Not in ``v1.__all__`` (it is metadata, not API), so re-exported explicitly.
from oscal_bindings.v1 import __oscal_schema_version__ as __oscal_schema_version__

# Generated model names: star-imported from the models module directly rather
# than from ``oscal_bindings.v1``, both for provenance (the names visibly come
# from where they are defined) and because ``oscal_bindings.v1`` defines
# ``__all__``, which would bound the star-import to the curated surface and drop
# the ~180 model names this line exists to carry.
from oscal_bindings.v1.models import *  # noqa: F403

__all__ = list(_v1.__all__)
