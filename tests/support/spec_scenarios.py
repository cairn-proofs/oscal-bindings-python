"""The scenarios of the pinned spec artifact, and who cites them (issue #49).

The artifact holds the main specs under ``openspec/specs/<capability>/spec.md``.
Each scenario has a heading of the form ``#### Scenario: MDL-021.03 <title>``.
A local test cites a scenario with ``@pytest.mark.spec("MDL-021.03")``, and a
test can cite more than one. A corpus case cites a scenario in its
``requirements`` list. ``tests/support/spec_not_applicable.py`` records the
scenarios that do not apply to this binding, each with a reason.

``problems`` compares the four and reports every offender. The checks read the
sources, not a test run, so they give the same result under ``pytest-xdist``.
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from support.spec_artifact import corpus_root, ensure_spec_artifact

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

#: A scenario identifier, such as ``MDL-021.03``.
SCENARIO_ID = re.compile(r"[A-Z]{3}-\d{3}\.\d{2}")
_SCENARIO_TOKEN = re.compile(r"\b[A-Z]{3}-\d{3}\.\d{2}\b")
_HEADING = re.compile(r"^#### Scenario: (\S+) (.*)$", re.MULTILINE)

REPO = Path(__file__).resolve().parent.parent.parent

#: Directories and files whose text may name a scenario. A name outside the
#: pinned artifact is a stale citation. ``openspec/changes/archive`` holds
#: history and is not read, and the checker's own test uses made-up identifiers.
_TEXT_ROOTS = ("src", "scripts", "tests", ".agents", "openspec", "docs")
_TEXT_FILES = ("README.md", "DEVELOPING.md", "AGENTS.md", "PERFORMANCE.md")
_TEXT_SUFFIXES = {".py", ".md", ".json", ".toml", ".yml", ".yaml"}
_SKIP_PARTS = {".corpus_cache", "__pycache__", "archive"}
_SKIP_FILES = {"test_spec_coverage.py"}


@dataclass(frozen=True)
class Scenario:
    """One scenario of the pinned artifact."""

    id: str
    capability: str
    title: str

    @property
    def requirement(self) -> str:
        """The requirement identifier, such as ``MDL-021``."""
        return self.id.split(".", 1)[0]


def artifact_scenarios() -> dict[str, Scenario]:
    """Return each scenario of the pinned artifact, by identifier."""
    specs = ensure_spec_artifact() / "openspec" / "specs"
    found: dict[str, Scenario] = {}
    for path in sorted(specs.glob("*/spec.md")):
        for match in _HEADING.finditer(path.read_text("utf-8")):
            found[match.group(1)] = Scenario(
                match.group(1), path.parent.name, match.group(2).strip()
            )
    return found


def corpus_citations() -> dict[str, list[str]]:
    """Return the corpus cases that cite each scenario, by scenario identifier.

    A case cites a requirement or a scenario in ``requirements``. Only a
    scenario identifier counts here: a requirement does not say which of its
    scenarios the case runs.
    """
    cases = json.loads((corpus_root() / "cases.json").read_text("utf-8"))["cases"]
    cited: dict[str, list[str]] = {}
    for case in cases:
        for ref in case.get("requirements", []):
            if SCENARIO_ID.fullmatch(ref):
                cited.setdefault(ref, []).append(case["id"])
    return cited


def _is_spec_marker(node: ast.AST) -> bool:
    """Return True for a call of ``pytest.mark.spec(...)``."""
    func = node.func if isinstance(node, ast.Call) else None
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "spec"
        and isinstance(func.value, ast.Attribute)
        and func.value.attr == "mark"
        and isinstance(func.value.value, ast.Name)
        and func.value.value.id == "pytest"
    )


def marker_citations(
    tests_dir: Path = REPO / "tests",
) -> tuple[dict[str, list[str]], list[str]]:
    """Read the ``pytest.mark.spec(...)`` calls of the test modules.

    Returns the places that cite each identifier (``path:line``), and the
    problems of the markers themselves: an argument that is not a string
    literal, or a marker with no argument. A marker counts wherever it stands:
    on a test, on a class, in ``pytestmark``, or in ``pytest.param(marks=...)``.
    """
    cited: dict[str, list[str]] = {}
    errors: list[str] = []
    for path in sorted(tests_dir.rglob("test_*.py")):
        if _SKIP_PARTS & set(path.parts):
            continue
        tree = ast.parse(path.read_text("utf-8"))
        where = path.relative_to(tests_dir.parent).as_posix()
        for node in ast.walk(tree):
            if not _is_spec_marker(node):
                continue
            assert isinstance(node, ast.Call)
            place = f"{where}:{node.lineno}"
            if not node.args:
                errors.append(f"{place}: pytest.mark.spec() cites no scenario")
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    cited.setdefault(arg.value, []).append(place)
                else:
                    errors.append(f"{place}: a spec marker argument is not a string")
    return cited, errors


def text_citations(root: Path = REPO) -> dict[str, list[str]]:
    """Return the scenario identifiers that the repository text names, with places.

    The text is the source, the scripts, the tests, the summaries, and the
    top-level documents. It finds a stale citation in a docstring or a comment.
    """
    files: list[Path] = [root / name for name in _TEXT_FILES]
    for name in _TEXT_ROOTS:
        files.extend(p for p in (root / name).rglob("*") if p.is_file())
    found: dict[str, list[str]] = {}
    for path in sorted(files):
        if (
            path.suffix not in _TEXT_SUFFIXES
            or _SKIP_PARTS & set(path.parts)
            or path.name in _SKIP_FILES
            or not path.is_file()
        ):
            continue
        text = path.read_text("utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), start=1):
            for token in _SCENARIO_TOKEN.findall(line):
                found.setdefault(token, []).append(
                    f"{path.relative_to(root).as_posix()}:{number}"
                )
    return found


def problems(  # noqa: PLR0913, PLR0917 -- the four sources and two extras
    scenarios: Mapping[str, Scenario],
    markers: Mapping[str, Iterable[str]],
    corpus: Mapping[str, Iterable[str]],
    record: Mapping[str, str],
    text: Mapping[str, Iterable[str]] | None = None,
    marker_errors: Iterable[str] = (),
) -> list[str]:
    """Return every way that the citations disagree with the pinned artifact.

    1. A scenario that no test cites, no corpus case cites, and the record does
       not list.
    2. A test, a record entry, or a text citation that names a scenario the
       artifact does not have, such as a retired one.
    3. A scenario that the record lists and that a test or a corpus case cites.
    4. A record entry with no reason, and a marker that is not well formed.
    """
    found = list(marker_errors)
    for ident, places in sorted(markers.items()):
        if not SCENARIO_ID.fullmatch(ident):
            found.append(f"{', '.join(places)}: {ident!r} is not a scenario identifier")
        elif ident not in scenarios:
            found.append(
                f"{', '.join(places)}: a test cites {ident}, which the artifact lacks"
            )
    for ident, reason in sorted(record.items()):
        if ident not in scenarios:
            found.append(f"record: {ident} is not a scenario of the artifact")
        if not reason.strip():
            found.append(f"record: {ident} has no reason")
    for ident, places in sorted((text or {}).items()):
        if ident not in scenarios:
            found.append(
                f"{', '.join(places)}: names {ident}, which the artifact lacks"
            )
    for ident in sorted(scenarios):
        cited_by = [*markers.get(ident, ()), *corpus.get(ident, ())]
        if ident in record and cited_by:
            found.append(
                f"{ident} is in the record of scenarios that do not apply, "
                f"and {cited_by[0]} cites it"
            )
        if ident not in record and not cited_by:
            found.append(
                f"{ident} ({scenarios[ident].capability}: {scenarios[ident].title}) "
                "is cited by no test and no corpus case, and is not recorded"
            )
    return found
