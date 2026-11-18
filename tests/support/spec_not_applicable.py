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
    "SRF-002.01": (
        "A rule that classifies an example operation: this binding exposes "
        "no asynchronous or other adaptation function, and its traceability "
        "record holds no binding-local entry."
    ),
    "SRF-003.02": (
        "The binding exposes no binding-local operation, so its "
        "traceability record has no binding-local entry to check."
    ),
    "SRF-005.01": (
        "The binding declares no binding-local operation, so no operation "
        "of it is promoted to a contract requirement."
    ),
    "SRF-005.02": (
        "The binding declares no binding-local operation, so no promoted "
        "operation exists that could need deprecation."
    ),
    "SRF-006.02": (
        "The store's own checks fail on a stale requirement index; the "
        "binding does not generate or check the index, it only reads the "
        "pinned one."
    ),
    # -- document-facade ----------------------------------------------------------
    # -- document-parsing ---------------------------------------------------------
    # -- element-validation -------------------------------------------------------
    # -- error-model --------------------------------------------------------------
    # -- model-derivation ---------------------------------------------------------
    # -- naming-manifest ----------------------------------------------------------
    # -- schema-versioning --------------------------------------------------------
    "VER-003.01": (
        "The store decides how its artifact version increments; the binding "
        "only pins one version and never releases the artifact."
    ),
    "VER-003.02": (
        "The store decides how its artifact version increments for a corpus "
        "fixture fix; the binding does not release the artifact."
    ),
    "VER-003.03": (
        "The store decides how its artifact version increments for a "
        "stricter parse rule; the binding does not release the artifact."
    ),
    "VER-003.04": (
        "The store decides how its artifact version increments for an "
        "addition; the binding does not release the artifact."
    ),
    "VER-003.05": (
        "The store decides how its artifact version increments for a prose "
        "clarification; the binding does not release the artifact."
    ),
    "VER-004.02": (
        "The store sets the artifact version when it moves to a compatible "
        "OSCAL release; the binding only pins the resulting version."
    ),
    "VER-004.03": (
        "The store sets the artifact version when it moves to a new OSCAL "
        "major version; the binding only pins the resulting version."
    ),
    "VER-004.04": (
        "Version precedence is a Semantic Versioning comparison that the "
        "store applies to its releases; no code of the binding compares "
        "artifact versions."
    ),
    "VER-006.01": (
        "The scenario describes the store's own corpus:check; the binding "
        "runs no such check and its runner ignores known-defects."
    ),
    "VER-006.02": (
        "The scenario describes a check of the store's tracked files; the "
        "binding does not hold or check store content."
    ),
    "VER-006.03": (
        "The scenario describes a check of how the store lists known "
        "implementations; the binding does not hold or check store content."
    ),
    # -- serialization ------------------------------------------------------------
    # -- yaml-documents -----------------------------------------------------------
}
