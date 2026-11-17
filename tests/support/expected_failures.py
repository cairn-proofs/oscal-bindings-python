"""Conformance corpus cases that this binding is known to fail.

This binding owns the list. The spec store doesn't track a binding's defects,
so a fix here never needs a store change or release. ``tests/test_conformance.py``
runs each listed case as a strict expected failure: when the defect is fixed,
the case passes unexpectedly and the run fails until its entry is removed. An
entry whose case id isn't in the pinned corpus also fails the run.

A JSON case and its YAML twin that exercise the same defect are both listed.
"""

from __future__ import annotations

ISSUES = "https://github.com/cairn-proofs/oscal-bindings-python/issues"

# Corpus case id -> issue that tracks the defect.
EXPECTED_FAILURES: dict[str, str] = {
    # A round trip keeps six datetime fraction digits and drops the seventh.
    "round-trip/seven-fraction-digits": f"{ISSUES}/19",
    "yaml-round-trip/string-scalars": f"{ISSUES}/19",
    # PRS-014: only failures of the selected nested-union branch.
    "parse/closed-enum-out-of-set": f"{ISSUES}/69",
    # FAC-007: datetime bounds from assessment_period().
    "assessment-period/mixed-offsets": f"{ISSUES}/58",
    "assessment-period/equal-instant": f"{ISSUES}/58",
    "assessment-period/seventh-fraction-digit": f"{ISSUES}/58",
    # BMB-004, ERR-013: resource identifier from a key, builder-error category.
    "build-resource/key": f"{ISSUES}/62",
    "build-resource/key-with-title": f"{ISSUES}/62",
    "build-resource/non-ascii-key": f"{ISSUES}/62",
    "build-resource/key-and-identifier": f"{ISSUES}/62",
    "build-resource/empty-key": f"{ISSUES}/62",
    # FAC-001 to FAC-003, BMB-001 to BMB-003: the runner lacks these operations.
    **dict.fromkeys(
        (
            "facade/catalog",
            "facade/profile",
            "facade/component-definition",
            "facade/system-security-plan",
            "facade/assessment-plan",
            "facade/assessment-results",
            "facade/plan-of-action-and-milestones",
            "facade/mapping-collection",
            "facade/missing-file",
            "build-hash/default-algorithm",
            "build-hash/algorithm-string",
            "build-hash/off-list-algorithm",
            "build-hash/invalid-algorithm",
            "build-rlink/reference-only",
            "build-rlink/media-type-and-hashes",
            "build-resource/generated-identifier",
            "build-resource/omitted-inputs",
            "build-resource/invalid-document-id",
        ),
        f"{ISSUES}/63",
    ),
}
