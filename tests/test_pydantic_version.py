"""Guard the supported pydantic version range.

The generated ``v1/models.py`` is not compatible with pydantic 2.14+. On that
line, pydantic's parametrized ``RootModel[...]`` classes (``OscalDocument`` and
``MappingCollectionMappings``) appear as named attributes of the models module
on Python 3.11, which the model tripwires in ``test_models_manifest.py`` and
``test_serialization_defaults.py`` reject. The runtime dependency in
``pyproject.toml`` therefore caps pydantic below 2.14
(``pydantic[email]>=2.11,<2.14``).

This module states that bound once, so a slip past it fails here with a message
that names the cause, rather than as a cryptic structural assertion elsewhere.
Lifting the bound is tracked in issue #11 (Add Python 3.15 to the test matrix):
make the models support 2.14, then raise ``SUPPORTED_BELOW`` here and the bound
in ``pyproject.toml`` together.
"""

from __future__ import annotations

import pydantic
from packaging.version import Version

# Keep in step with the upper bound of ``pydantic[email]`` in pyproject.toml.
SUPPORTED_BELOW = Version("2.14")
SUPPORTED_FROM = Version("2.11")


def test_pydantic_is_within_the_supported_range() -> None:
    installed = Version(pydantic.VERSION)
    assert SUPPORTED_FROM <= installed < SUPPORTED_BELOW, (
        f"pydantic {installed} is outside the supported range "
        f">={SUPPORTED_FROM},<{SUPPORTED_BELOW}. The generated models break on "
        f"2.14+ (RootModel classes leak into the models namespace on 3.11). "
        f"Re-lock within the range, or, to support 2.14, do the work in issue "
        f"#11 and raise SUPPORTED_BELOW here and the cap in pyproject.toml "
        f"together."
    )
