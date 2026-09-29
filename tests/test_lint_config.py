"""Example tests for the lint-and-format-enforcement configuration.

Feature: lint-and-format-enforcement

These pin the concrete values in ``pyproject.toml`` (and a handful of tree
facts) that the requirements name. Parsed assertions go through ``tomllib``.
"""

import re
import tomllib
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
GENERATED_MODELS = ROOT / "src" / "oscal_bindings" / "v1" / "models.py"

V1_GLOB = "src/oscal_bindings/v1/**"
SHIM_INIT = "src/oscal_bindings/__init__.py"
POSTPROCESS = "scripts/postprocess_models.py"

# Req 2.6: the four files whose re-export lines carried an unused F401 noqa.
NOQA_F401_SITES = [
    "src/oscal_bindings/__init__.py",
    "src/oscal_bindings/extensions/__init__.py",
    "src/oscal_bindings/parser.py",
    "src/oscal_bindings/v1/__init__.py",
]

_NOQA_CODES = re.compile(r"#\s*noqa:\s*([^#\n]*)", re.IGNORECASE)


@pytest.fixture(scope="module")
def pyproject() -> dict[str, Any]:
    with PYPROJECT.open("rb") as fh:
        return tomllib.load(fh)


@pytest.fixture(scope="module")
def ruff(pyproject: dict[str, Any]) -> dict[str, Any]:
    return pyproject["tool"]["ruff"]


@pytest.fixture(scope="module")
def per_file_ignores(ruff: dict[str, Any]) -> dict[str, list[str]]:
    return ruff["lint"]["per-file-ignores"]


@pytest.fixture(scope="module")
def default_env(pyproject: dict[str, Any]) -> dict[str, Any]:
    return pyproject["tool"]["hatch"]["envs"]["default"]


def _entries_naming(ignores: dict[str, list[str]], code: str) -> set[str]:
    return {pattern for pattern, codes in ignores.items() if code in codes}


# --- Req 1.1, 4.10: pinned Ruff ---------------------------------------------


def test_ruff_pinned_exactly_once_with_exact_specifier(
    default_env: dict[str, Any],
) -> None:
    ruff_deps = [
        dep
        for dep in default_env["dependencies"]
        if re.match(r"ruff\b", dep, re.IGNORECASE)
    ]
    assert len(ruff_deps) == 1, ruff_deps
    assert re.fullmatch(r"ruff==\d+\.\d+\.\d+", ruff_deps[0]), ruff_deps[0]


# --- Req 1.5: retained settings ---------------------------------------------


def test_retained_ruff_settings(ruff: dict[str, Any]) -> None:
    assert ruff["line-length"] == 88
    assert ruff["target-version"] == "py311"
    assert ruff["format"]["quote-style"] == "double"
    assert ruff["format"]["indent-style"] == "space"
    assert ruff["lint"]["isort"]["known-first-party"] == ["oscal_bindings"]


# --- Req 1.6, 2.1, 2.2, 2.3, 2.5, 2.9: per-file ignores ---------------------


def test_tests_entry_retains_req_1_6_codes_and_inp001(
    per_file_ignores: dict[str, list[str]],
) -> None:
    codes = set(per_file_ignores["tests/**/*"])
    assert {"PLR2004", "S101", "TID252", "PLC0415"} <= codes
    assert "INP001" in codes


def test_scripts_entry_is_exactly_t201_inp001(
    per_file_ignores: dict[str, list[str]],
) -> None:
    assert set(per_file_ignores["scripts/**/*"]) == {"T201", "INP001"}


def test_postprocess_entry_is_exactly_plr0912_plr0915(
    per_file_ignores: dict[str, list[str]],
) -> None:
    assert set(per_file_ignores[POSTPROCESS]) == {"PLR0912", "PLR0915"}
    for code in ("PLR0912", "PLR0915"):
        assert _entries_naming(per_file_ignores, code) == {POSTPROCESS}


def test_v1_entry_is_exactly_em101_em102_try003(
    per_file_ignores: dict[str, list[str]],
) -> None:
    assert set(per_file_ignores[V1_GLOB]) == {"EM101", "EM102", "TRY003"}


def test_plc0414_scoped_to_shim_init_only(
    per_file_ignores: dict[str, list[str]],
) -> None:
    assert _entries_naming(per_file_ignores, "PLC0414") == {SHIM_INIT}


# --- Req 2.6: dead F401 noqa directives removed -----------------------------


@pytest.mark.parametrize("rel_path", NOQA_F401_SITES)
def test_no_noqa_f401_at_shim_sites(rel_path: str) -> None:
    text = (ROOT / rel_path).read_text(encoding="utf-8")
    for match in _NOQA_CODES.finditer(text):
        codes = {c.strip().upper() for c in re.split(r"[,\s]+", match.group(1))}
        assert "F401" not in codes, f"{rel_path}: {match.group(0)!r}"


# --- Req 1.8, 3.3: top-level exclusions -------------------------------------


@pytest.mark.parametrize(
    "pattern",
    ["src/oscal_bindings/v1/models.py", "*.md", "./build", ".hatch"],
)
def test_top_level_exclusion_patterns(ruff: dict[str, Any], pattern: str) -> None:
    assert pattern in ruff["extend-exclude"]


# --- Req 3.4: no in-file suppression in the generated module ----------------


# Built by concatenation so Ruff does not parse these literals as directives
# on this line.
_SUPPRESSION_MARKERS = ["#" + " noqa", "#" + " fmt: off", "#" + " fmt: on"]


@pytest.mark.parametrize("marker", _SUPPRESSION_MARKERS)
def test_generated_models_has_no_suppression_markers(marker: str) -> None:
    assert marker not in GENERATED_MODELS.read_text(encoding="utf-8")


# --- Req 4.1, 4.2, 4.5, 4.6, 4.10: Hatch scripts ----------------------------


def test_lint_script_runs_check_and_format_check(
    default_env: dict[str, Any],
) -> None:
    lint = default_env["scripts"]["lint"]
    assert isinstance(lint, list)
    assert any(cmd.startswith("ruff check") for cmd in lint)
    assert any(cmd.startswith("ruff format --check") for cmd in lint)


def test_release_includes_lint_and_keeps_every_stage(
    default_env: dict[str, Any],
) -> None:
    release = default_env["scripts"]["release"]
    for stage in ("generate", "lint", "typing", "hatch test --all --cover", "docs"):
        assert stage in release, stage
    assert release.index("generate") < release.index("lint")


# --- Req 1.3: no Hatch-supplied ruleset -------------------------------------


def test_no_hatch_static_analysis_ruleset(pyproject: dict[str, Any]) -> None:
    assert "hatch-static-analysis" not in pyproject["tool"]["hatch"]["envs"]
    assert "extend" not in pyproject["tool"]["ruff"]
    assert "ruff_defaults.toml" not in PYPROJECT.read_text(encoding="utf-8")


# --- Req 4.8, 4.9: no CI workflow, no pre-commit hook -----------------------


def test_no_ci_workflows_directory() -> None:
    assert not (ROOT / ".github" / "workflows").exists()


def test_no_pre_commit_config() -> None:
    assert not (ROOT / ".pre-commit-config.yaml").exists()


# --- Req 2.8: accepted findings left in the source --------------------------


def test_tests_is_not_a_package() -> None:
    assert not (ROOT / "tests" / "__init__.py").exists()


def test_postprocess_script_still_prints() -> None:
    assert "print(" in (ROOT / POSTPROCESS).read_text(encoding="utf-8")
