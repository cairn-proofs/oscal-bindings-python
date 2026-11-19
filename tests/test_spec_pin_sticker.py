"""Tests for the README sticker of the spec store (``docs/sticker.md`` of the store).

The sticker has two badges. The version badge reads ``version`` from
``spec-pin.json``; the status badge shows the workflow that runs the corpus. The
store states the conditions for showing it (SRF-009, store 0.9.0 and later; the
pinned artifact predates it, so these tests cite no scenario id):

1. ``spec-pin.json`` holds the pinned spec artifact version.
2. The status badge names a workflow that runs the corpus.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from support.spec_artifact import SPEC_ARTIFACT_VERSION

REPO_ROOT = Path(__file__).resolve().parents[1]
OWNER_REPO = "cairn-proofs/oscal-bindings-python"
BRANCH = "main"
WORKFLOW = "build.yml"

VERSION_BADGE = (
    "[![oscal-bindings-specs](https://img.shields.io/badge/dynamic/json?url="
    "https%3A%2F%2Fraw.githubusercontent.com%2F"
    + OWNER_REPO.replace("/", "%2F")
    + f"%2F{BRANCH}%2Fspec-pin.json&query=%24.version&label=oscal-bindings-specs)]"
    "(https://github.com/cairn-proofs/oscal-bindings-specs)"
)
STATUS_BADGE = (
    "[![conformance](https://img.shields.io/github/actions/workflow/status/"
    f"{OWNER_REPO}/{WORKFLOW}?branch={BRANCH}&label=conformance)]"
    f"(https://github.com/{OWNER_REPO}/actions/workflows/{WORKFLOW})"
)


def test_spec_pin_file_holds_the_pinned_version():
    pin = json.loads((REPO_ROOT / "spec-pin.json").read_text(encoding="utf-8"))
    assert pin == {"version": SPEC_ARTIFACT_VERSION}


def test_readme_starts_with_both_badges():
    lines = (REPO_ROOT / "README.md").read_text(encoding="utf-8").splitlines()
    assert lines[:2] == [VERSION_BADGE, STATUS_BADGE]


def test_status_badge_workflow_runs_the_corpus():
    workflow = REPO_ROOT / ".github" / "workflows" / WORKFLOW
    if not workflow.is_file():  # an sdist ships no workflows
        return
    text = workflow.read_text(encoding="utf-8")
    # `hatch test` runs tests/test_conformance.py, which runs every corpus case.
    assert re.search(r"^\s*run: hatch test\b", text, re.MULTILINE)
    assert re.search(rf"^\s+branches:.*\b{BRANCH}\b", text, re.MULTILINE)
