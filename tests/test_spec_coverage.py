"""Which scenarios of the pinned spec artifact the tests cover (issue #49).

Three checks run against the pinned artifact. Each scenario is cited by a local
test (``@pytest.mark.spec("MDL-021.03")``), cited by a corpus case, or recorded
in ``tests/support/spec_not_applicable.py`` with a reason. No citation names a
scenario that the artifact lacks. No scenario is both recorded and cited. The
unit tests run the same logic on made-up data, so each failure mode is shown to
fail.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from support import spec_scenarios as sc
from support.spec_not_applicable import NOT_APPLICABLE

if TYPE_CHECKING:
    from pathlib import Path

SCENARIOS = {
    "AAA-001.01": sc.Scenario("AAA-001.01", "alpha", "one"),
    "AAA-001.02": sc.Scenario("AAA-001.02", "alpha", "two"),
    "BBB-002.01": sc.Scenario("BBB-002.01", "beta", "three"),
}


def _check(
    markers: dict[str, list[str]] | None = None,
    corpus: dict[str, list[str]] | None = None,
    record: dict[str, str] | None = None,
    text: dict[str, list[str]] | None = None,
) -> list[str]:
    return sc.problems(SCENARIOS, markers or {}, corpus or {}, record or {}, text)


class TestTheCheck:
    """The logic, on made-up scenarios."""

    def test_all_scenarios_cited_or_recorded_is_clean(self) -> None:
        assert (
            _check(
                markers={"AAA-001.01": ["tests/a.py:3"]},
                corpus={"AAA-001.02": ["case/x"]},
                record={"BBB-002.01": "the store runs this one"},
            )
            == []
        )

    def test_a_scenario_that_nobody_cites_fails(self) -> None:
        found = _check(
            markers={"AAA-001.01": ["tests/a.py:3"]},
            corpus={"AAA-001.02": ["case/x"]},
        )
        assert len(found) == 1
        assert found[0].startswith("BBB-002.01 (beta: three)")

    def test_removing_the_only_marker_of_a_scenario_fails(self) -> None:
        cited = {"AAA-001.01": ["tests/a.py:3"], "AAA-001.02": ["tests/a.py:9"]}
        kept = {"BBB-002.01": ["tests/b.py:1"], **cited}
        assert _check(markers=kept) == []
        del kept["AAA-001.02"]
        assert any(f.startswith("AAA-001.02") for f in _check(markers=kept))

    def test_a_corpus_case_covers_a_scenario(self) -> None:
        found = _check(
            markers={"AAA-001.01": ["a:1"], "AAA-001.02": ["a:2"]},
            corpus={"BBB-002.01": ["case/y"]},
        )
        assert found == []

    def test_a_retired_scenario_cited_by_a_test_fails(self) -> None:
        found = _check(
            markers={
                "AAA-001.01": ["tests/a.py:1"],
                "AAA-001.02": ["tests/a.py:2"],
                "BBB-002.01": ["tests/a.py:3"],
                "AAA-001.99": ["tests/a.py:4"],
            }
        )
        assert found == [
            "tests/a.py:4: a test cites AAA-001.99, which the artifact lacks"
        ]

    def test_a_retired_scenario_in_the_record_fails(self) -> None:
        found = _check(
            markers={s: ["a:1"] for s in SCENARIOS},
            record={"AAA-009.01": "gone"},
        )
        assert found == ["record: AAA-009.01 is not a scenario of the artifact"]

    def test_a_retired_scenario_named_in_text_fails(self) -> None:
        found = _check(
            markers={s: ["a:1"] for s in SCENARIOS},
            text={"AAA-001.99": ["src/x.py:7"]},
        )
        assert found == ["src/x.py:7: names AAA-001.99, which the artifact lacks"]

    def test_a_scenario_in_the_record_and_cited_by_a_test_fails(self) -> None:
        found = _check(
            markers={s: ["tests/a.py:1"] for s in SCENARIOS},
            record={"AAA-001.01": "not for this binding"},
        )
        assert len(found) == 1
        assert "AAA-001.01 is in the record" in found[0]
        assert "tests/a.py:1 cites it" in found[0]

    def test_a_scenario_in_the_record_and_cited_by_a_corpus_case_fails(self) -> None:
        found = _check(
            markers={"AAA-001.02": ["a:1"], "BBB-002.01": ["a:2"]},
            corpus={"AAA-001.01": ["case/z"]},
            record={"AAA-001.01": "not for this binding"},
        )
        assert len(found) == 1
        assert "case/z cites it" in found[0]

    def test_a_record_entry_needs_a_reason(self) -> None:
        found = _check(
            markers={"AAA-001.01": ["a:1"], "AAA-001.02": ["a:2"]},
            record={"BBB-002.01": "  "},
        )
        assert found == ["record: BBB-002.01 has no reason"]

    def test_a_marker_that_is_not_a_scenario_identifier_fails(self) -> None:
        found = _check(
            markers={
                "AAA-001": ["tests/a.py:1"],
                "AAA-001.01": ["a:1"],
                "AAA-001.02": ["a:2"],
                "BBB-002.01": ["a:3"],
            }
        )
        assert found == ["tests/a.py:1: 'AAA-001' is not a scenario identifier"]


class TestTheScanners:
    def test_markers_are_read_from_a_test_module(self, tmp_path: Path) -> None:
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "test_x.py").write_text(
            "import pytest\n"
            "\n"
            "pytestmark = pytest.mark.spec('AAA-001.01')\n"
            "\n"
            "@pytest.mark.spec('AAA-001.02', 'BBB-002.01')\n"
            "def test_a(): ...\n"
            "\n"
            "class TestB:\n"
            "    @pytest.mark.parametrize(\n"
            "        'v', [pytest.param(1, marks=pytest.mark.spec('AAA-001.02'))]\n"
            "    )\n"
            "    def test_c(self, v): ...\n"
            "\n"
            "@pytest.mark.slow\n"
            "def test_d(): ...\n",
            encoding="utf-8",
        )
        cited, errors = sc.marker_citations(tests)
        assert errors == []
        assert sorted(cited) == ["AAA-001.01", "AAA-001.02", "BBB-002.01"]
        assert len(cited["AAA-001.02"]) == 2
        assert cited["AAA-001.01"] == ["tests/test_x.py:3"]

    def test_a_marker_without_a_string_is_an_error(self, tmp_path: Path) -> None:
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "test_x.py").write_text(
            "import pytest\n"
            "ID = 'AAA-001.01'\n"
            "@pytest.mark.spec(ID)\n"
            "def test_a(): ...\n"
            "@pytest.mark.spec()\n"
            "def test_b(): ...\n",
            encoding="utf-8",
        )
        cited, errors = sc.marker_citations(tests)
        assert cited == {}
        assert len(errors) == 2
        assert "not a string" in errors[0]
        assert "cites no scenario" in errors[1]

    def test_text_citations_find_a_name_in_a_docstring(self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "m.py").write_text(
            '"""Implements AAA-001.01 and not AAA-001."""\n', encoding="utf-8"
        )
        for name in sc._TEXT_FILES:  # noqa: SLF001
            (tmp_path / name).write_text("", encoding="utf-8")
        for name in sc._TEXT_ROOTS:  # noqa: SLF001
            (tmp_path / name).mkdir(exist_ok=True)
        found = sc.text_citations(tmp_path)
        assert found == {"AAA-001.01": ["src/m.py:1"]}


@pytest.fixture(scope="module")
def scenarios() -> dict[str, sc.Scenario]:
    found = sc.artifact_scenarios()
    assert found, "the pinned artifact has no scenarios"
    return found


class TestThePinnedArtifact:
    """The checks of issue #49, on the real artifact and the real tests."""

    def test_the_artifact_scenarios_are_read(
        self, scenarios: dict[str, sc.Scenario]
    ) -> None:
        capabilities = {s.capability for s in scenarios.values()}
        assert {"model-derivation", "document-parsing", "serialization"} <= capabilities
        assert all(sc.SCENARIO_ID.fullmatch(ident) for ident in scenarios)

    def test_every_scenario_is_covered_and_no_citation_is_stale(
        self, scenarios: dict[str, sc.Scenario]
    ) -> None:
        markers, marker_errors = sc.marker_citations()
        found = sc.problems(
            scenarios,
            markers,
            sc.corpus_citations(),
            NOT_APPLICABLE,
            sc.text_citations(),
            marker_errors,
        )
        assert found == [], "\n" + "\n".join(found)

    def test_a_corpus_citation_names_a_scenario_of_the_artifact(
        self, scenarios: dict[str, sc.Scenario]
    ) -> None:
        stale = sorted(set(sc.corpus_citations()) - set(scenarios))
        assert stale == []
