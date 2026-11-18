"""Scenarios of the pinned spec artifact that do not apply to this binding.

Each entry maps a scenario identifier to the reason. ``tests/test_spec_coverage.py``
fails when a listed scenario is also cited by a test or a corpus case, or when
an identifier is not a scenario of the pinned artifact (a retired scenario, for
example). A scenario that applies to this binding gets a test with
``@pytest.mark.spec("<id>")`` instead of an entry here.

The sections follow the capabilities of the artifact, so that a change to one
capability touches one section.
"""

from __future__ import annotations

NOT_APPLICABLE: dict[str, str] = {
    # -- backmatter-builders ------------------------------------------------------
    # -- binding-surface ----------------------------------------------------------
    # -- document-facade ----------------------------------------------------------
    # -- document-parsing ---------------------------------------------------------
    # -- element-validation -------------------------------------------------------
    # -- error-model --------------------------------------------------------------
    # -- model-derivation ---------------------------------------------------------
    "MDL-007.01": (
        "The derivation guard runs in the store, which writes the manifest; the "
        "binding reads the manifest and holds no wrapper derivation to abort."
    ),
    "MDL-007.02": (
        "The wrapper count guard belongs to the store's derivation; the binding "
        "reads the finished manifest and does not count derived wrappers."
    ),
    "MDL-007.03": (
        "Reporting uncovered name collisions is a step of the store's derivation; "
        "the binding checks the manifest for unique names (NAM-003), not collisions."
    ),
    "MDL-009.01": (
        "The scenario compares a Go binding and a Rust binding, so no test of "
        "this Python binding can run it."
    ),
    "MDL-021.01": (
        "A missing singular name aborts the store's derivation; the binding "
        "takes singular names from the finished manifest and derives none."
    ),
    "MDL-021.02": (
        "A branch without a distinguishing property aborts the store's derivation; "
        "the binding reads the finished manifest and derives no branches."
    ),
    "MDL-021.04": (
        "Reporting each missing singular name at once is a step of the store's "
        "derivation, which the binding does not run."
    ),
    # -- naming-manifest ----------------------------------------------------------
    # -- schema-versioning --------------------------------------------------------
    # -- serialization ------------------------------------------------------------
    # -- yaml-documents -----------------------------------------------------------
}
