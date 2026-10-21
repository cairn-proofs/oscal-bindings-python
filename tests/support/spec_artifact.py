"""The pinned spec artifact of the OSCAL bindings contract, for the tests.

The pin lives in ``scripts/spec_artifact.py``, which code generation shares.
This module re-exports it and fetches through ``support.corpus``, so the tests
and generation read one cache, and a test can replace
``support.corpus._http_get``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from support.corpus import CACHE_ROOT, ensure_pinned_archive
from support.scripts import load_script

if TYPE_CHECKING:
    from pathlib import Path

_pin = load_script("spec_artifact")

SPEC_ARTIFACT_VERSION: str = _pin.SPEC_ARTIFACT_VERSION
SPEC_ARTIFACT_SHA256: str = _pin.SPEC_ARTIFACT_SHA256
SPEC_ARTIFACT = _pin.SPEC_ARTIFACT
OSCAL_RELEASE: str = _pin.OSCAL_RELEASE


def ensure_spec_artifact(*, cache_root: Path = CACHE_ROOT) -> Path:
    """Return the root of the cached, hash-checked spec artifact."""
    return ensure_pinned_archive(SPEC_ARTIFACT, cache_root=cache_root)


def corpus_root(*, cache_root: Path = CACHE_ROOT) -> Path:
    """Return the conformance corpus directory inside the spec artifact."""
    corpus: Path = _pin.artifact_paths(
        ensure_spec_artifact(cache_root=cache_root)
    ).corpus
    return corpus


def schema_path(*, cache_root: Path = CACHE_ROOT) -> Path:
    """Return the complete OSCAL JSON Schema inside the spec artifact."""
    schema: Path = _pin.artifact_paths(
        ensure_spec_artifact(cache_root=cache_root)
    ).schema
    return schema
