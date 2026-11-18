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
