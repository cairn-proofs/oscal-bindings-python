"""Property tests for the major-version package move (``oscal_bindings.v1``).

Counterpart to the example-based back-compat coverage in
`tests/test_oscal_bindings.py`. This module is the property-traceability surface
for the relocation half of the `major-version-namespace` design; properties are
numbered per that document:

- Property 3 — the published surface is preserved by the move (below).
- Property 4 — type identity across the Compat_Shim (below).
- Property 5 — version-constant consistency (below).
- Property 6 — namespace stability across OSCAL 1.x (below).

None of the four uses `@given`, and that is the design's call rather than an
omission. Each quantifies over a space that is either a single fixed input (the
committed pre-move `__all__` snapshot; the one real Active_Schema_Bundle) or
finitely enumerable (the Public_Surface, 34 names). Hypothesis adds nothing to
an input space you can write down, and a strategy that draws from
`oscal_bindings.__all__` would only re-derive the expectation from the code
under test. The enumerable case is `parametrize`d so each name fails
individually; the fixed-input cases are plain assertions.

The pre-move snapshot and the Active_Schema_Bundle lookup are imported from
`support.version_package` — shared with the example-based suite so there is one
snapshot of record, not two that can drift apart.
"""

from __future__ import annotations

import importlib

import pytest
from support.version_package import (
    PRE_MOVE_ALL,
    SEMVER_RE,
    active_schema_path,
    schema_release,
)

import oscal_bindings
import oscal_bindings.v1

#: The Public_Surface, enumerated (Req 5.3/5.6 quantify over exactly this set).
#: Sorted so parametrized ids are stable across runs and xdist workers.
PUBLIC_SURFACE = sorted(oscal_bindings.__all__)


# ---------------------------------------------------------------------------
# Property 3 — the published surface is preserved by the move
#
# Example-based on purpose: the input is the committed pre-move `__all__`
# snapshot, a single fixed value. There is nothing to sample.
# ---------------------------------------------------------------------------


class TestProperty3PublishedSurfacePreserved:
    """Feature: major-version-namespace, Property 3: For all names in the pre-move
    top-level __all__, that name appears in the Version_Package __all__, and the two
    sets are equal in both directions.

    **Validates: Requirements 4.4**
    """

    def test_every_pre_move_name_appears_in_the_version_package_surface(self) -> None:
        """The forward direction: nothing was dropped by the move."""
        dropped = PRE_MOVE_ALL - set(oscal_bindings.v1.__all__)
        assert not dropped, f"names lost in the move: {sorted(dropped)}"

    def test_the_version_package_surface_adds_nothing(self) -> None:
        """The reverse direction, which set containment alone would not catch.

        Req 4.4 is *same* surface, not *superset*: a name that appeared only
        after the move is drift too, and the snapshot is what makes it visible.
        """
        added = set(oscal_bindings.v1.__all__) - PRE_MOVE_ALL
        assert not added, f"names added by the move: {sorted(added)}"

    def test_the_two_surfaces_are_equal(self) -> None:
        """Equality in both directions, stated as the single claim it is."""
        assert set(oscal_bindings.v1.__all__) == PRE_MOVE_ALL

    def test_every_pre_move_name_actually_resolves_on_the_version_package(self) -> None:
        """`__all__` membership is a declaration; this checks it is backed.

        A name listed in `__all__` but never bound would pass set equality and
        still fail at `from oscal_bindings.v1 import <name>`.
        """
        for name in sorted(PRE_MOVE_ALL):
            assert hasattr(oscal_bindings.v1, name), f"{name} declared but not bound"


# ---------------------------------------------------------------------------
# Property 4 — type identity across the Compat_Shim
#
# Enumerable, so parametrized rather than generated: the quantifier runs over
# the 34 names in the Public_Surface, and naming each one gives a per-name
# failure instead of a single opaque one.
# ---------------------------------------------------------------------------


class TestProperty4TypeIdentityAcrossTheShim:
    """Feature: major-version-namespace, Property 4: For any name in the
    Public_Surface, the object reached through the Compat_Shim is the same object as
    the one reached directly through the Version_Package.

    **Validates: Requirements 5.3, 5.6**
    """

    def test_the_public_surface_is_non_empty(self) -> None:
        """Guards the parametrization: an empty surface would vacuously pass."""
        assert PUBLIC_SURFACE
        assert set(PUBLIC_SURFACE) == PRE_MOVE_ALL

    @pytest.mark.parametrize("name", PUBLIC_SURFACE)
    def test_shim_name_is_the_same_object_as_the_version_package_name(
        self, name: str
    ) -> None:
        """Identity, not equality — `is`, per Req 5.3.

        Identity is what makes Req 5.6 (`isinstance` agreeing across import
        paths) fall out for free; equality would not, since two structurally
        identical Pydantic classes are distinct types.
        """
        assert hasattr(oscal_bindings, name), f"{name} not reachable through the shim"
        assert hasattr(oscal_bindings.v1, name), f"{name} not on the Version_Package"
        assert getattr(oscal_bindings, name) is getattr(oscal_bindings.v1, name)


# ---------------------------------------------------------------------------
# Property 5 — version-constant consistency
#
# Example-based on purpose: there is exactly one Active_Schema_Bundle. The
# release is parsed out of the real bundle's `$id` at test time rather than
# restated, so a schema refresh that forgets to bump the constant fails here.
# ---------------------------------------------------------------------------


class TestProperty5VersionConstantConsistency:
    """Feature: major-version-namespace, Property 5: For any Active_Schema_Bundle, the
    Schema_Version_Constant equals the release version parsed out of that bundle's
    schema $id.

    **Validates: Requirements 6.3**
    """

    def test_constant_equals_the_release_parsed_from_the_active_bundle(self) -> None:
        schema_path = active_schema_path()
        assert schema_path.exists(), f"Active_Schema_Bundle missing: {schema_path}"
        assert schema_release(schema_path) == oscal_bindings.v1.__oscal_schema_version__

    def test_constant_is_semver_shaped(self) -> None:
        """Req 6.2 — major.minor.patch, so `major()` below is well defined."""
        version = oscal_bindings.v1.__oscal_schema_version__
        assert isinstance(version, str)
        assert SEMVER_RE.match(version), f"not major.minor.patch: {version!r}"


# ---------------------------------------------------------------------------
# Property 6 — namespace stability across OSCAL 1.x
#
# Example-based on purpose: the claim is about the package *name*, which is a
# single value. Its content is that the name is a function of the major version
# alone — so no 1.x minor or patch bump can perturb it.
# ---------------------------------------------------------------------------


class TestProperty6NamespaceStability:
    """Feature: major-version-namespace, Property 6: For any Active_Schema_Bundle
    within OSCAL 1.x, the Version_Package name is unchanged — it carries a major
    component only.

    **Validates: Requirements 4.6**
    """

    @staticmethod
    def _package_name() -> str:
        return oscal_bindings.v1.__name__.rsplit(".", 1)[-1]

    def test_package_name_is_v_plus_the_major_component(self) -> None:
        major = oscal_bindings.v1.__oscal_schema_version__.split(".")[0]
        assert self._package_name() == f"v{major}"

    def test_package_name_carries_no_minor_or_patch_component(self) -> None:
        """The substance of Req 4.6, stated independently of the major check.

        `v1` is a function of the major version alone, so the minor and patch of
        whatever 1.x release is active must not appear in it — in any spelling.
        A `v1_2` or `v1.2.3` namespace would satisfy the check above only if the
        major matched, and would still break every consumer import on the next
        refresh. Checking for the separators is the version-agnostic form.
        """
        name = self._package_name()
        major, minor, patch = oscal_bindings.v1.__oscal_schema_version__.split(".")

        assert name == f"v{major}"
        assert "_" not in name, f"minor/patch component in the namespace: {name!r}"
        assert "." not in name, f"minor/patch component in the namespace: {name!r}"
        for component in (minor, patch):
            assert name != f"v{major}_{component}"
            assert name != f"v{major}{component}"

    def test_the_package_is_reachable_under_that_exact_name(self) -> None:
        """The name is the consumer-visible import path, not just an attribute."""
        major = oscal_bindings.v1.__oscal_schema_version__.split(".")[0]
        assert importlib.import_module(f"oscal_bindings.v{major}") is oscal_bindings.v1
