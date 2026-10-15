"""Tests for the spec identifier checker (`scripts/check_spec_ids.py`).

Each test mutates a small in-memory corpus that passes every rule, then checks
that the expected rule fails, or that nothing fails. The corpus is generic: the
checker has no project-specific behavior.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

# The checker is parked here until task 7.3 of the change
# reverse-engineer-oscal-bindings-spec in cairn-proofs/oscal-bindings-specs.
# PyYAML is not a declared test dependency, so the module skips when absent.
pytest.importorskip("yaml", reason="scripts/check_spec_ids.py needs PyYAML")

REPO_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_spec_ids.py"

WID = "openspec/specs/widget-parsing/spec.md"
OUT = "openspec/specs/widget-output/spec.md"


def _load() -> ModuleType:
    """Load the checker script as a module (it lives outside the package)."""
    spec = importlib.util.spec_from_file_location("check_spec_ids", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def ids() -> ModuleType:
    return _load()


def _spec(capability: str, body: str) -> str:
    head = f"# {capability} Specification\n\n## Purpose\nTest.\n\n"
    return f"{head}## Requirements\n\n{body}"


def _req(rid: str, title: str, scenarios: list[str], text: str = "Text.") -> str:
    out = f"### Requirement: {rid} {title}\n\n{text}\n\n"
    for scenario in scenarios:
        out += f"#### Scenario: {scenario}\n\n- **WHEN** x\n- **THEN** y\n\n"
    return out


def _ledger(extra: str = "", retired: str = "[]") -> str:
    return (
        "prefixes:\n"
        "  WID:\n    capability: widget-parsing\n    next: 5\n"
        "  OUT:\n    capability: widget-output\n    next: 2\n"
        f"{extra}retired: {retired}\n"
    )


WID_BODY = (
    _req("WID-001", "Parse a widget", ["WID-001.01 Empty input"])
    + _req("WID-002", "Widget key form", ["WID-002.01 Valid key", "WID-002.02 Bad key"])
    + _req("WID-003", "Unique widget keys", ["WID-003.01 Duplicate key"])
    + _req("WID-004", "Widget size", ["WID-004.01 Zero size"])
)
WID_004 = _req("WID-004", "Widget size", ["WID-004.01 Zero size"])
EXTRA_SCENARIO = "#### Scenario: {sid}\n\n- **WHEN** x\n- **THEN** y\n\n"


class Corpus:
    """The working files and the base-ref specs of one test."""

    def __init__(self, ids: ModuleType) -> None:
        self.ids = ids
        self.files: dict[str, str] = {
            ids.LEDGER: _ledger(),
            WID: _spec("widget-parsing", WID_BODY),
            OUT: _spec(
                "widget-output",
                _req(
                    "OUT-001",
                    "Write a widget",
                    ["OUT-001.01 Default form"],
                    text="The key follows [WID-002].",
                ),
            ),
            "docs/guide.md": (
                "See [the key form](../openspec/specs/widget-parsing/spec.md"
                "#requirement-wid-002-widget-key-form).\n"
            ),
        }
        self.base = {
            k: v for k, v in self.files.items() if k.startswith("openspec/specs/")
        }

    def replace(self, target: dict[str, str], file: str, old: str, new: str) -> None:
        assert old in target[file], f"fixture has no {old!r}"
        target[file] = target[file].replace(old, new, 1)

    def run(self) -> list[str]:
        return self.ids.check_spec_ids(self.files, self.base)


@pytest.fixture
def corpus(ids: ModuleType) -> Corpus:
    return Corpus(ids)


def _fails(out: list[str], rule: str, needle: str) -> bool:
    return any(line.startswith(f"[{rule}]") and needle in line for line in out)


# --- Baseline -------------------------------------------------------------------


def test_baseline_has_zero_failures(corpus: Corpus) -> None:
    assert corpus.run() == []


# --- Heading form ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("old", "new", "needle"),
    [
        ("Requirement: WID-002 Widget", "Requirement: Widget", '"Widget key form"'),
        ("Requirement: WID-002 Widget", "Requirement: WID-2 Widget", '"WID-2 Widget'),
        ("Requirement: WID-002 Widget", "Requirement: WID-0002 Widget", "WID-0002"),
    ],
    ids=["no-identifier", "under-padded", "over-padded"],
)
def test_requirement_id(corpus: Corpus, old: str, new: str, needle: str) -> None:
    corpus.replace(corpus.files, WID, old, new)
    assert _fails(corpus.run(), "requirement-id", needle)


@pytest.mark.parametrize(
    ("new", "needle"),
    [
        ("Scenario: WID-002.1 Valid key", '"WID-002.1 Valid key"'),
        ("Scenario: WID-002.001 Valid key", '"WID-002.001 Valid key"'),
        ("Scenario: Valid key", '"Valid key"'),
    ],
    ids=["under-padded", "surplus-zero", "no-identifier"],
)
def test_scenario_id(corpus: Corpus, new: str, needle: str) -> None:
    corpus.replace(corpus.files, WID, "Scenario: WID-002.01 Valid key", new)
    assert _fails(corpus.run(), "scenario-id", needle)


def test_wide_scenario_number_is_well_formed(corpus: Corpus) -> None:
    anchor = "#### Scenario: WID-002.02"
    corpus.replace(
        corpus.files,
        WID,
        anchor,
        EXTRA_SCENARIO.format(sid="WID-002.100 Many") + anchor,
    )
    assert corpus.run() == []


def test_scenario_under_another_requirement(corpus: Corpus) -> None:
    anchor = "#### Scenario: WID-002.02"
    corpus.replace(
        corpus.files,
        WID,
        anchor,
        EXTRA_SCENARIO.format(sid="WID-003.02 Misplaced") + anchor,
    )
    assert _fails(
        corpus.run(), "scenario-parent", '"WID-003.02 Misplaced" is under WID-002'
    )


def test_headings_in_code_fences_are_ignored(corpus: Corpus) -> None:
    corpus.files[WID] += "```\n### Requirement: Not a heading\n```\n"
    assert corpus.run() == []


# --- Ledger and prefixes --------------------------------------------------------


def test_missing_ledger(corpus: Corpus, ids: ModuleType) -> None:
    del corpus.files[ids.LEDGER]
    assert _fails(corpus.run(), "ledger", "does not exist")


@pytest.mark.parametrize(
    ("text", "needle"),
    [
        ("prefixes: [\n", "is not valid YAML"),
        ("retired: []\n", "has no prefixes map"),
        (
            "prefixes:\n  WID:\n    capability: widget-parsing\n    next: 5\n",
            "no retired list",
        ),
        (_ledger().replace("next: 5", "next: 0"), '"WID" needs a capability'),
        (_ledger().replace("next: 5", "next: true"), '"WID" needs a capability'),
        (_ledger().replace("  WID:", "  wid:"), '"wid" needs a capability'),
        (
            _ledger(retired="\n  - { id: WID-004 }"),
            "needs a well-formed id and a reason",
        ),
        (_ledger(retired="\n  - { id: nope, reason: x }"), "needs a well-formed id"),
        (
            _ledger(retired="\n  - { id: WID-004, reason: x, replaced_by: nope }"),
            "replaced_by of WID-004 is not a well-formed identifier",
        ),
    ],
    ids=[
        "invalid-yaml",
        "no-prefixes",
        "no-retired",
        "zero-next",
        "bool-next",
        "lowercase-prefix",
        "no-reason",
        "bad-id",
        "bad-replaced-by",
    ],
)
def test_malformed_ledger(
    corpus: Corpus, ids: ModuleType, text: str, needle: str
) -> None:
    corpus.files[ids.LEDGER] = text
    assert _fails(corpus.run(), "ledger", needle)


def test_wrong_prefix(corpus: Corpus) -> None:
    corpus.files[WID] += _req("OUT-009", "Stray", [])
    assert _fails(
        corpus.run(), "prefix", '"OUT-009 Stray" uses OUT, not the prefix WID'
    )


def test_capability_without_prefix(corpus: Corpus) -> None:
    corpus.files["openspec/specs/new-thing/spec.md"] = _spec("new-thing", "")
    assert _fails(corpus.run(), "prefix", "capability new-thing has no prefix")


def test_capability_with_two_prefixes(corpus: Corpus, ids: ModuleType) -> None:
    corpus.files[ids.LEDGER] = _ledger(
        "  WDG:\n    capability: widget-parsing\n    next: 1\n"
    )
    assert _fails(corpus.run(), "prefix", "widget-parsing has 2 prefixes")


# --- Allocation and retirement --------------------------------------------------


def test_duplicate_identifier(corpus: Corpus) -> None:
    corpus.replace(
        corpus.files, WID, "Requirement: WID-003 Unique", "Requirement: WID-002 Unique"
    )
    assert _fails(corpus.run(), "duplicate-id", "WID-002 is on 2 headings")


def test_number_at_next(corpus: Corpus) -> None:
    corpus.files[WID] += _req("WID-005", "Too far", ["WID-005.01 Example"])
    assert _fails(corpus.run(), "next", '"WID-005 Too far" is at or above next (5)')


def test_requirement_removed_without_ledger_entry(corpus: Corpus) -> None:
    corpus.replace(corpus.files, WID, WID_004, "")
    assert _fails(corpus.run(), "missing-id", "WID-004 is neither live nor retired")


def test_scenario_removed_without_ledger_entry(corpus: Corpus) -> None:
    anchor = "#### Scenario: WID-002.02"
    corpus.replace(
        corpus.base, WID, anchor, EXTRA_SCENARIO.format(sid="WID-002.03 Gone") + anchor
    )
    assert _fails(corpus.run(), "vanished-scenario", "WID-002.03 is in the base specs")


def test_retired_scenario_may_vanish(corpus: Corpus, ids: ModuleType) -> None:
    anchor = "#### Scenario: WID-002.02"
    corpus.replace(
        corpus.base, WID, anchor, EXTRA_SCENARIO.format(sid="WID-002.03 Gone") + anchor
    )
    corpus.files[ids.LEDGER] = _ledger(retired="\n  - { id: WID-002.03, reason: test }")
    assert corpus.run() == []


def test_unreadable_base(corpus: Corpus, ids: ModuleType) -> None:
    out = ids.check_spec_ids(corpus.files, RuntimeError("bad ref"))
    assert _fails(
        out, "vanished-scenario", "cannot read the main specs at the base ref"
    )


def test_retired_identifier_on_a_heading(corpus: Corpus, ids: ModuleType) -> None:
    corpus.files[ids.LEDGER] = _ledger(retired="\n  - { id: WID-004, reason: test }")
    assert _fails(corpus.run(), "retired-reuse", "retired identifier WID-004")


def _relocate(corpus: Corpus, target: str) -> None:
    corpus.replace(corpus.files, WID, WID_004, "")
    corpus.files[OUT] += _req("OUT-002", "Widget size", ["OUT-002.01 Zero size"])
    corpus.files[corpus.ids.LEDGER] = _ledger(
        retired=f"\n  - {{ id: WID-004, reason: moved, replaced_by: {target} }}"
    ).replace("next: 2", "next: 3")


def test_relocated_requirement(corpus: Corpus) -> None:
    _relocate(corpus, "OUT-002")
    assert corpus.run() == []


def test_relocation_to_missing_identifier(corpus: Corpus) -> None:
    _relocate(corpus, "OUT-099")
    assert _fails(corpus.run(), "replaced-by", "replaced_by OUT-099")


def test_retired_requirement_retires_its_scenarios(
    corpus: Corpus, ids: ModuleType
) -> None:
    corpus.replace(corpus.files, WID, WID_004, "")
    corpus.files[ids.LEDGER] = _ledger(retired="\n  - { id: WID-004, reason: test }")
    corpus.files["docs/other.md"] = "Follows [WID-004.01].\n"
    assert corpus.run() == []


def test_padding_is_canonical_in_ledger(corpus: Corpus, ids: ModuleType) -> None:
    corpus.replace(corpus.files, WID, WID_004, "")
    corpus.files[ids.LEDGER] = _ledger(retired="\n  - { id: WID-4, reason: test }")
    assert corpus.run() == []


# --- Citations and links --------------------------------------------------------


def test_citation_of_unknown_identifier(corpus: Corpus) -> None:
    corpus.files["docs/other.md"] = "Follows [WID-099].\n"
    assert _fails(corpus.run(), "citation", "docs/other.md:1: citation [WID-099]")


def test_bracketed_token_without_ledger_prefix_is_not_a_citation(
    corpus: Corpus,
) -> None:
    corpus.files["docs/other.md"] = "Follows [CM-8](#cm-8-inventory) and [AC-2].\n"
    assert corpus.run() == []


def test_code_is_not_a_citation(corpus: Corpus) -> None:
    corpus.files["docs/other.md"] = (
        "Write `[WID-099]` like this.\n\n```\n[WID-098]\n```\n"
    )
    assert corpus.run() == []


def test_link_to_missing_heading(corpus: Corpus) -> None:
    corpus.files["docs/other.md"] = (
        "[Gone](../openspec/specs/widget-parsing/spec.md#requirement-wid-099-gone)\n"
    )
    assert _fails(corpus.run(), "link", "#requirement-wid-099-gone")


def test_link_to_missing_spec(corpus: Corpus) -> None:
    corpus.files["docs/other.md"] = (
        "[Gone](../openspec/specs/nothing/spec.md#purpose)\n"
    )
    assert _fails(
        corpus.run(), "link", "names no heading in openspec/specs/nothing/spec.md"
    )


def test_external_and_local_links_are_ignored(corpus: Corpus) -> None:
    corpus.files["docs/other.md"] = (
        "[a](https://example.com/x#y) [b](#local) [c](../README.md#z) [d](guide.md)\n"
    )
    assert corpus.run() == []


# --- Scope ----------------------------------------------------------------------


def test_change_specs_are_out_of_scope(corpus: Corpus) -> None:
    corpus.files["openspec/changes/x/specs/y/spec.md"] = _spec(
        "y", "### Requirement: No id\n\n#### Scenario: No id either\n\n"
    )
    assert corpus.run() == []


# --- Markdown helpers -----------------------------------------------------------


@pytest.mark.parametrize(
    ("heading", "anchor"),
    [
        ("Requirement: WID-002 Widget key form", "requirement-wid-002-widget-key-form"),
        ("Scenario: WID-002.01 Valid key", "scenario-wid-00201-valid-key"),
        ("Use `media-type` and back_matter!", "use-media-type-and-back_matter"),
        ("Already-hyphenated  double space", "already-hyphenated--double-space"),
    ],
)
def test_slug_matches_github(ids: ModuleType, heading: str, anchor: str) -> None:
    assert anchor in ids.anchors(f"## {heading}\n")


def test_repeated_slugs_get_suffixes(ids: ModuleType) -> None:
    slugger = ids.Slugger()
    assert [slugger.slug("Purpose") for _ in range(3)] == [
        "purpose",
        "purpose-1",
        "purpose-2",
    ]


def test_canonical_and_render_round_trip(ids: ModuleType) -> None:
    assert ids.canonical("WID-002") == ids.canonical("WID-2") == "WID-2"
    assert ids.canonical("WID-002.01") == "WID-2.1"
    assert ids.canonical("not an id") is None
    assert ids.render("WID-2.1") == "WID-002.01"
    assert ids.render("WID-1234") == "WID-1234"


# --- CLI ------------------------------------------------------------------------


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)  # noqa: S603, S607


def _repo(tmp_path: Path) -> Path:
    """A git repository with one committed main spec and a matching ledger."""
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    spec = tmp_path / "openspec" / "specs" / "widget-parsing" / "spec.md"
    spec.parent.mkdir(parents=True)
    spec.write_text(_spec("widget-parsing", WID_BODY))
    (tmp_path / "openspec" / "spec-ids.yaml").write_text(
        "prefixes:\n  WID:\n    capability: widget-parsing\n    next: 5\nretired: []\n"
    )
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


def test_main_reports_ok(
    ids: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(_repo(tmp_path))
    monkeypatch.delenv("SPEC_IDS_BASE", raising=False)
    assert ids.main() == 0


def test_main_catches_vanished_scenario_against_head(
    ids: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = _repo(tmp_path)
    spec = root / "openspec" / "specs" / "widget-parsing" / "spec.md"
    spec.write_text(
        spec.read_text().replace("#### Scenario: WID-002.02 Bad key", "Bad key")
    )
    monkeypatch.chdir(root)
    monkeypatch.delenv("SPEC_IDS_BASE", raising=False)
    assert ids.main() == 1
    assert "[vanished-scenario] WID-002.02" in capsys.readouterr().err


def test_main_reports_unknown_base_ref(
    ids: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(_repo(tmp_path))
    monkeypatch.setenv("SPEC_IDS_BASE", "no-such-ref")
    assert ids.main() == 1
    assert "[vanished-scenario] cannot read" in capsys.readouterr().err
