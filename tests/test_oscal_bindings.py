"""Back-compatibility tests for the ``oscal_bindings`` top-level package.

The public API moved into :mod:`oscal_bindings.v1`, leaving the top level as a
pure re-export shim. These tests are the contract that the move was
behavior-preserving for existing consumers:

* every pre-move public name still imports from ``oscal_bindings`` (Req 5.1);
* all three legacy module paths still resolve (Req 5.5) — importing
  ``oscal_bindings.extensions`` here is also what keeps that alias module
  covered, since nothing else in the suite reaches for the legacy path;
* names reached through the shim are the *same objects* as those reached
  through the Version_Package, so ``isinstance`` agrees across paths
  (Req 5.6);
* the Version_Package surface equals the snapshotted pre-move ``__all__``, in
  both directions, so nothing was added or dropped (Req 4.4);
* ``__oscal_schema_version__`` is semver-shaped and matches the release encoded
  in the Active_Schema_Bundle's schema ``$id`` (Req 6.1-6.3, 9.2).
"""

from __future__ import annotations

import importlib
import json
from typing import TYPE_CHECKING

import pytest
from support.version_package import (
    PRE_MOVE_ALL,
    SEMVER_RE,
    active_schema_path,
    schema_release,
)

import oscal_bindings
import oscal_bindings.extensions
import oscal_bindings.models
import oscal_bindings.parser
import oscal_bindings.v1

if TYPE_CHECKING:
    from types import ModuleType

#: Legacy module path → the ``v1`` module it must re-export from.
LEGACY_MODULE_PATHS = {
    "oscal_bindings.models": "oscal_bindings.v1.models",
    "oscal_bindings.parser": "oscal_bindings.v1.parser",
    "oscal_bindings.extensions": "oscal_bindings.v1.extensions",
}

#: A sample of generated model names that must stay importable straight off the
#: top-level package (the pre-move ``from .models import *`` behavior, Req 5.4).
#: A sample, not the full ~180: the exhaustive check is the star-import itself.
GENERATED_MODEL_NAMES = ("Catalog", "Profile", "Metadata", "Resource", "Rlink", "Hash")


def test_import():
    assert oscal_bindings is not None


class TestPublicSurface:
    """Req 4.4, 5.1 — the published surface survived the move intact."""

    def test_version_package_surface_matches_the_pre_move_snapshot(self):
        assert set(oscal_bindings.v1.__all__) == PRE_MOVE_ALL

    def test_shim_surface_matches_the_pre_move_snapshot(self):
        assert set(oscal_bindings.__all__) == PRE_MOVE_ALL

    @pytest.mark.parametrize("name", sorted(PRE_MOVE_ALL))
    def test_pre_move_name_imports_from_the_top_level(self, name: str):
        assert hasattr(oscal_bindings, name), f"{name} no longer importable"

    @pytest.mark.parametrize("name", GENERATED_MODEL_NAMES)
    def test_generated_model_name_imports_from_the_top_level(self, name: str):
        """Req 5.4 — the star-import of the generated models is preserved."""
        assert hasattr(oscal_bindings, name)
        assert getattr(oscal_bindings, name) is getattr(oscal_bindings.v1.models, name)

    def test_shim_declares_no_symbols_of_its_own(self):
        """Req 5.2 — every curated name on the shim came from ``v1``."""
        for name in oscal_bindings.__all__:
            assert getattr(oscal_bindings, name) is getattr(oscal_bindings.v1, name)


class TestLegacyModulePaths:
    """Req 5.5 — ``oscal_bindings.{models,parser,extensions}`` still resolve."""

    @pytest.mark.parametrize("legacy", sorted(LEGACY_MODULE_PATHS))
    def test_legacy_module_imports(self, legacy: str):
        assert importlib.import_module(legacy) is not None

    @pytest.mark.parametrize(("legacy", "target"), sorted(LEGACY_MODULE_PATHS.items()))
    def test_legacy_module_is_distinct_from_its_target(self, legacy: str, target: str):
        """Explicit alias modules, not ``sys.modules`` aliasing.

        The legacy path is its own module object that re-exports; if this ever
        becomes an identity, someone swapped in ``sys.modules`` aliasing and the
        greppability the design asked for is gone.
        """
        assert importlib.import_module(legacy) is not importlib.import_module(target)

    @pytest.mark.parametrize(("legacy", "target"), sorted(LEGACY_MODULE_PATHS.items()))
    def test_legacy_module_reexports_the_same_objects(self, legacy: str, target: str):
        legacy_mod: ModuleType = importlib.import_module(legacy)
        target_mod: ModuleType = importlib.import_module(target)
        exported = getattr(legacy_mod, "__all__", None)
        if exported is None:  # ``models`` re-exports by star-import only
            exported = [n for n in dir(legacy_mod) if not n.startswith("_")]
        assert exported, f"{legacy} re-exports nothing"
        for name in exported:
            assert getattr(legacy_mod, name) is getattr(target_mod, name), name

    def test_legacy_extensions_exposes_the_extension_helpers(self):
        """The legacy ``extensions`` path is a real import, not just a module."""
        from oscal_bindings.extensions import OscalDoc, make_hash

        assert OscalDoc is oscal_bindings.v1.extensions.OscalDoc
        assert make_hash is oscal_bindings.v1.extensions.make_hash

    def test_legacy_parser_exposes_the_parser_helpers(self):
        from oscal_bindings.parser import parse_oscal

        assert parse_oscal is oscal_bindings.v1.parser.parse_oscal

    def test_legacy_models_exposes_the_generated_models(self):
        from oscal_bindings.models import Catalog

        assert Catalog is oscal_bindings.v1.models.Catalog


class TestTypeIdentityAcrossPaths:
    """Req 5.3, 5.6 — one object, reachable by several names."""

    def test_catalog_is_the_same_class_through_every_path(self):
        assert oscal_bindings.Catalog is oscal_bindings.v1.models.Catalog
        assert oscal_bindings.Catalog is oscal_bindings.models.Catalog

    def test_catalog_document_is_the_same_class_through_every_path(self):
        assert (
            oscal_bindings.CatalogDocument is oscal_bindings.v1.models.CatalogDocument
        )
        assert oscal_bindings.CatalogDocument is oscal_bindings.parser.CatalogDocument

    def test_isinstance_agrees_across_paths(self):
        """The consumer-visible consequence of identity, asserted directly."""
        doc = oscal_bindings.v1.parser.parse_catalog(
            json.dumps(
                {
                    "catalog": {
                        "uuid": "11111111-2222-4333-8444-555555555555",
                        "metadata": {
                            "title": "t",
                            "last-modified": "2024-01-01T00:00:00Z",
                            "version": "1.0",
                            "oscal-version": "1.1.2",
                        },
                    }
                }
            )
        )
        assert isinstance(doc, oscal_bindings.CatalogDocument)
        assert isinstance(doc, oscal_bindings.parser.CatalogDocument)
        assert isinstance(doc.catalog, oscal_bindings.Catalog)
        assert isinstance(doc.catalog, oscal_bindings.models.Catalog)


class TestSchemaVersionConstant:
    """Req 6.1-6.4 — the constant is present, well-shaped, and truthful."""

    def test_constant_is_exposed_by_both_the_package_and_the_shim(self):
        assert (
            oscal_bindings.__oscal_schema_version__
            is oscal_bindings.v1.__oscal_schema_version__
        )

    def test_constant_is_semver_shaped(self):
        version = oscal_bindings.v1.__oscal_schema_version__
        assert isinstance(version, str)
        assert SEMVER_RE.match(version), f"not major.minor.patch: {version!r}"

    def test_constant_equals_the_release_in_the_schema_id(self):
        """Req 6.3 — parsed out of the real bundle, not restated.

        The ``$id`` is ``.../ns/oscal/<namespace>/<release>/oscal-complete-schema.json``
        so the release is the path element before the filename.
        """
        schema_path = active_schema_path()
        assert schema_release(schema_path) == oscal_bindings.v1.__oscal_schema_version__

    def test_version_package_name_carries_the_major_version_only(self):
        """Req 4.3, 4.6 — ``v1``, so no 1.x refresh can perturb the path."""
        major = oscal_bindings.v1.__oscal_schema_version__.split(".")[0]
        assert oscal_bindings.v1.__name__.rsplit(".", 1)[-1] == f"v{major}"
