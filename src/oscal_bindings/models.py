"""Legacy module path for the generated OSCAL models.

The models now live in :mod:`oscal_bindings.v1.models`; this module re-exports
them so that ``from oscal_bindings.models import Catalog`` keeps resolving.
Re-export binds the same class objects, so type identity holds across both
paths.

An explicit alias module rather than ``sys.modules`` aliasing: it is greppable
and survives static analysis, ``mypy``, and ``pdoc`` without special cases.

This file is **not** generated — it is a hand-written shim. The generated models
are in :mod:`oscal_bindings.v1.models`, which carries the codegen banner.
"""

from oscal_bindings.v1.models import *  # noqa: F403
