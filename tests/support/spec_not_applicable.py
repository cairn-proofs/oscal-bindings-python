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
    # -- naming-manifest ----------------------------------------------------------
    # -- schema-versioning --------------------------------------------------------
    # -- serialization ------------------------------------------------------------
    # -- yaml-documents -----------------------------------------------------------
}
