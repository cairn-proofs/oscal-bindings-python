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
    "NAM-005.03": (
        "A name change is an edit of overrides.json in the spec store; the binding "
        "holds no override data and never writes names.json."
    ),
    "NAM-015.01": (
        "Override validation is a rule of the store generation; the binding reads "
        "no overrides.json and has no generation step."
    ),
    "NAM-015.02": (
        "Override validation is a rule of the store generation; the binding reads "
        "no overrides.json and has no generation step."
    ),
    "NAM-015.03": (
        "Override validation is a rule of the store generation; the binding reads "
        "no overrides.json and has no generation step."
    ),
    "NAM-006.01": (
        "The store check that regenerates names.json and compares it with the "
        "committed file is a store process; the binding has no generator of the "
        "manifest."
    ),
    "NAM-006.02": (
        "Reproducibility of the generation that writes names.json is a property of "
        "the store generator, which the binding does not run."
    ),
    "NAM-006.03": (
        "The store check on the manifest of a previous release is a store process; "
        "the binding pins one artifact and holds no previous manifest."
    ),
    "NAM-016.01": (
        "The check of the previous release manifest belongs to the store "
        "generation; the binding never reads a previous manifest."
    ),
    "NAM-007.01": (
        "Name stability across releases is kept by the store generation from the "
        "previous manifest; the binding takes names from the pinned manifest only."
    ),
    "NAM-007.02": (
        "Qualifying a new clashing definition is a rule of the store generation; "
        "the binding takes names from the pinned manifest only."
    ),
    "NAM-017.01": (
        "Reporting dropped names is output of the store generation; the binding has "
        "no generation step."
    ),
    "NAM-017.02": (
        "Reporting dropped names is output of the store generation; the binding has "
        "no generation step."
    ),
    "NAM-008.01": (
        "The name check against the latest released artifact is a store check on "
        "pull requests; the binding runs no such check."
    ),
    "NAM-008.02": (
        "The name check against the latest released artifact is a store check on "
        "pull requests; the binding runs no such check."
    ),
    "NAM-008.04": (
        "The name check against the latest released artifact is a store check on "
        "pull requests; the binding runs no such check."
    ),
    "NAM-018.01": (
        "Choosing the latest release tag is a rule of the store name check; the "
        "binding selects its artifact by an explicit pin."
    ),
    "NAM-019.01": (
        "Reading release tags and history is a step of the store name check; the "
        "binding does not read git tags of the store."
    ),
    "NAM-019.02": (
        "Reading release tags and history is a step of the store name check; the "
        "binding does not read git tags of the store."
    ),
    # -- schema-versioning --------------------------------------------------------
    # -- serialization ------------------------------------------------------------
    # -- yaml-documents -----------------------------------------------------------
}
