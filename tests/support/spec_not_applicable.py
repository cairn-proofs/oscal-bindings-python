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
    "ELV-004.01": (
        "The scenario starts from a binding that documents a failure limit for element "
        "validation; this binding documents none (the README limit table names no "
        "validate_element row), and ELV-004.03 pins that it lists every failure."
    ),
    "ELV-004.02": (
        "The scenario starts from a binding that documents a depth limit for element "
        "validation; this binding documents none for validate_element (the README "
        "limit table lists only the parse operations), so no such error exists."
    ),
    # -- error-model --------------------------------------------------------------
    # -- model-derivation ---------------------------------------------------------
    # -- naming-manifest ----------------------------------------------------------
    # -- schema-versioning --------------------------------------------------------
    # -- serialization ------------------------------------------------------------
    # -- yaml-documents -----------------------------------------------------------
    "YML-001.01": (
        "The scenario describes a binding that exposes no YAML operation; this binding "
        "offers the whole YAML capability and runs the YAML corpus cases."
    ),
    "YML-005.05": (
        "The scenario needs a documented limit on YAML input bytes; this binding "
        "documents none (the README states that no limit bounds the input size), "
        "so no such limit exists."
    ),
}
