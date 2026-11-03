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
}
