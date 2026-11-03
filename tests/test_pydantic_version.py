"""Guard the supported pydantic version range.

The runtime dependency in ``pyproject.toml`` is ``pydantic[email]>=2.14.2,<3``.
2.14.2 is the first release whose JSON validation rejects a key spelled with a
model's Python field name (``back_matter``) as ``extra_forbidden``. Earlier
2.13/2.14 releases drop the key and lose its value without an error (issue #6,
pydantic GHSA-qpmf-fgh3-ff25). The JSON-mode tests in ``test_base_model.py`` and
``test_prop_serialization_preservation.py`` require that rejection.

This module states the range once, so an install outside it fails here with a
message that names the cause, rather than as a structural assertion elsewhere.
"""

from __future__ import annotations

import pydantic
from packaging.version import Version

# Keep in step with ``pydantic[email]`` in pyproject.toml.
SUPPORTED_FROM = Version("2.14.2")
SUPPORTED_BELOW = Version("3")


def test_pydantic_is_within_the_supported_range() -> None:
    installed = Version(pydantic.VERSION)
    assert SUPPORTED_FROM <= installed < SUPPORTED_BELOW, (
        f"pydantic {installed} is outside the supported range "
        f">={SUPPORTED_FROM},<{SUPPORTED_BELOW}. Below {SUPPORTED_FROM}, JSON "
        f"input silently drops keys spelled with a Python field name (issue #6). "
        f"Re-lock within the range, and change SUPPORTED_FROM/SUPPORTED_BELOW "
        f"here and the range in pyproject.toml together."
    )
