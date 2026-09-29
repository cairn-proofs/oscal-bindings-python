"""Legacy module path for the hand-written extension helpers.

The extensions now live in :mod:`oscal_bindings.v1.extensions`; this module
re-exports their public surface so that
``from oscal_bindings.extensions import OscalDoc`` keeps resolving. Re-export
binds the same objects, so type identity holds across both paths.

An explicit alias module rather than ``sys.modules`` aliasing: it is greppable
and survives static analysis, ``mypy``, and ``pdoc`` without special cases.

``oscal_bindings.v1.extensions`` declares its own ``__all__``, so the
star-import below is bounded by that curated surface and the two cannot drift.
"""

from oscal_bindings.v1 import extensions as _extensions
from oscal_bindings.v1.extensions import *  # noqa: F403

__all__ = list(_extensions.__all__)
