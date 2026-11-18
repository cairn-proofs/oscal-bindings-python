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
    "PRS-010.01": (
        "The binding documents no limit on the bytes of a JSON input (README, "
        "Resource limits: no limit bounds the input size), so the scenario's "
        "precondition never holds."
    ),
    "PRS-011.01": (
        "Optional rule (PRS-011): the binding documents no limit on the number "
        "of structured entries of a parse error, so no entry limit stops a "
        "parse."
    ),
    "PRS-011.02": (
        "Optional rule (PRS-011): the binding documents no limit on the number "
        "of structured entries of a parse error, so there is no entry limit to "
        "stay within."
    ),
    "PRS-011.03": (
        "Optional rule (PRS-011): the binding documents no limit on the number "
        "of structured entries of a parse error, so there is no entry limit to "
        "reach."
    ),
    "PRS-012.02": (
        "The binding documents no limit on validation time, so no such limit "
        "stops a parse after a short list of entries."
    ),
    "PRS-012.03": (
        "The binding documents no limit on the bytes of a JSON input, so no "
        "byte limit applies to an invalid document."
    ),
    # -- element-validation -------------------------------------------------------
    # -- error-model --------------------------------------------------------------
    "ERR-001.08": (
        "The scenario compares two bindings in different languages; a single "
        "binding cannot show agreement between a raising binding and a "
        "returning binding."
    ),
    "ERR-010.01": (
        "The scenario compares two bindings in different languages; a single "
        "binding cannot show agreement between a raising binding and a "
        "returning binding."
    ),
    "ERR-011.01": (
        "The binding documents no limit for element validation (README, "
        "Resource limits lists parse operations only), so the limit-exceeded "
        "category is not reachable."
    ),
    "ERR-011.02": (
        "The binding documents no limit for element validation (README, "
        "Resource limits lists parse operations only), so the limit-exceeded "
        "category is not reachable."
    ),
    # -- model-derivation ---------------------------------------------------------
    # -- naming-manifest ----------------------------------------------------------
    # -- schema-versioning --------------------------------------------------------
    # -- serialization ------------------------------------------------------------
    # -- yaml-documents -----------------------------------------------------------
}
