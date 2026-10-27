"""The pinned spec artifact of the OSCAL bindings contract.

The artifact is published by the spec store cairn-proofs/oscal-bindings-specs.
It holds the contract's main specs, the vendored schemas, the naming manifest,
and the conformance corpus. The sha256 is the pin: the tag only names the
release. To move to a new artifact, change the version and the sha256 together.

Generation and the tests share this pin and one cache, ``tests/.corpus_cache/``
at the repository root, so the artifact is downloaded once. Run this file to
fetch the artifact and print its paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from pinned_archive import PinnedArchive, ensure_pinned_archive, http_get

if TYPE_CHECKING:
    from collections.abc import Callable

SPEC_ARTIFACT_VERSION = "0.3.0+oscal.1.2.3"
SPEC_ARTIFACT_SHA256 = (
    "80914b77562a45bb5c0eb2d51b9d2cd0c33f82cf80a215be81e24c958dbcb1fe"
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

# The OSCAL release of the artifact, from the build metadata of the version.
OSCAL_RELEASE = SPEC_ARTIFACT_VERSION.split("+oscal.")[1]

# The repository root, from this file's location (scripts/spec_artifact.py).
REPO_ROOT: Path = Path(__file__).resolve().parent.parent
# The git-ignored cache that generation and the tests share.
CACHE_ROOT: Path = REPO_ROOT / "tests" / ".corpus_cache"


@dataclass(frozen=True)
class ArtifactPaths:
    """The paths that generation and the tests read inside the artifact root."""

    root: Path
    schema: Path
    """``schemas/<release>/oscal_complete_schema.json``: the complete schema."""
    names: Path
    """``manifest/<release>/names.json``: the naming manifest."""
    names_schema: Path
    """``manifest/names.schema.json``: the JSON Schema of ``names.json``."""
    corpus: Path
    """``corpus/<release>``: the conformance corpus directory."""


def artifact_paths(root: Path) -> ArtifactPaths:
    """Return the paths inside the artifact rooted at ``root``.

    The paths are computed, not checked. Use the root that
    ``ensure_spec_artifact`` returns.
    """
    return ArtifactPaths(
        root=root,
        schema=root / "schemas" / OSCAL_RELEASE / "oscal_complete_schema.json",
        names=root / "manifest" / OSCAL_RELEASE / "names.json",
        names_schema=root / "manifest" / "names.schema.json",
        corpus=root / "corpus" / OSCAL_RELEASE,
    )


def ensure_spec_artifact(
    *,
    cache_root: Path = CACHE_ROOT,
    fetch: Callable[[str], bytes] = http_get,
) -> Path:
    """Return the root of the cached, hash-checked spec artifact.

    A cache miss downloads the artifact with ``fetch``. A failure raises
    ``pinned_archive.CorpusError``.
    """
    return ensure_pinned_archive(SPEC_ARTIFACT, cache_root=cache_root, fetch=fetch)


def main() -> int:
    """Fetch the artifact and print its root and the paths inside it."""
    paths = artifact_paths(ensure_spec_artifact())
    for label, path in (
        ("root", paths.root),
        ("schema", paths.schema),
        ("names", paths.names),
        ("names-schema", paths.names_schema),
        ("corpus", paths.corpus),
    ):
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
