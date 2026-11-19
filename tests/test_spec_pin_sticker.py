"""Tests for the spec version badge of the README.

The badge is the version badge of the store's README sticker
(``docs/sticker.md`` of the store). Shields reads ``version`` from
``spec-pin.json`` on the default branch, so that file must hold the pinned spec
artifact version (SRF-009, store 0.9.0 and later; the pinned artifact predates
it, so these tests cite no scenario id). The sticker's status badge is not
shown.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from support.spec_artifact import SPEC_ARTIFACT_VERSION

REPO_ROOT = Path(__file__).resolve().parents[1]
OWNER_REPO = "cairn-proofs/oscal-bindings-python"
BRANCH = "main"

# (link target, image URL) of the badge, as docs/sticker.md writes it. The
# README holds it as <a><img> in its centered badge row, because Markdown does
# not render inside that HTML block.
VERSION_BADGE = (
    "https://github.com/cairn-proofs/oscal-bindings-specs",
    (
        "https://img.shields.io/badge/dynamic/json?url="
        "https%3A%2F%2Fraw.githubusercontent.com%2F"
        + OWNER_REPO.replace("/", "%2F")
        + f"%2F{BRANCH}%2Fspec-pin.json&query=%24.version&label=oscal-bindings-specs"
    ),
)
_BADGE_ROW = re.compile(r'<p align="center">(.*?)</p>', re.DOTALL)
_BADGE = re.compile(r'<a href="([^"]+)"><img alt="[^"]*" src="([^"]+)"></a>')


def test_spec_pin_file_holds_the_pinned_version():
    pin = json.loads((REPO_ROOT / "spec-pin.json").read_text(encoding="utf-8"))
    assert pin == {"version": SPEC_ARTIFACT_VERSION}


def test_readme_badge_row_starts_with_the_version_badge():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    row = _BADGE_ROW.search(readme)
    assert row is not None
    assert _BADGE.findall(row.group(1))[0] == VERSION_BADGE
