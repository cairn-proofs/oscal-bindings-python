"""The pinned spec artifact of the OSCAL bindings contract.

The artifact is published by the spec store cairn-proofs/oscal-bindings-specs.
It holds the contract's main specs, the vendored schemas, and the conformance
corpus. The sha256 is the pin: the tag only names the release. To move to a new
artifact, change all three values together.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from support.corpus import CACHE_ROOT, PinnedArchive, ensure_pinned_archive

if TYPE_CHECKING:
    from pathlib import Path

SPEC_ARTIFACT_VERSION = "0.1.0+oscal.1.2.3"
SPEC_ARTIFACT_SHA256 = (
    "89462f32e54d120c667e3744c3c27da761889d8a8fdd2c6f03b29a70a43ae33a"
)
# The `+` of the version is written as %2B in the URL path.
_URL_VERSION = SPEC_ARTIFACT_VERSION.replace("+", "%2B")
SPEC_ARTIFACT = PinnedArchive(
    name=f"oscal-bindings-specs {SPEC_ARTIFACT_VERSION}",
    url=(
        "https://github.com/cairn-proofs/oscal-bindings-specs/releases/download/"
        f"v{_URL_VERSION}/oscal-bindings-specs-{_URL_VERSION}.tar.gz"
    ),
    sha256=SPEC_ARTIFACT_SHA256,
    cache_dir=f"oscal-bindings-specs-{SPEC_ARTIFACT_VERSION}-{SPEC_ARTIFACT_SHA256[:12]}",
)

# The OSCAL release the corpus is for, from the build metadata of the version.
OSCAL_RELEASE = SPEC_ARTIFACT_VERSION.split("+oscal.")[1]


def ensure_spec_artifact(*, cache_root: Path = CACHE_ROOT) -> Path:
    """Return the root of the cached, hash-checked spec artifact."""
    return ensure_pinned_archive(SPEC_ARTIFACT, cache_root=cache_root)


def corpus_root(*, cache_root: Path = CACHE_ROOT) -> Path:
    """Return the conformance corpus directory inside the spec artifact."""
    return ensure_spec_artifact(cache_root=cache_root) / "corpus" / OSCAL_RELEASE
