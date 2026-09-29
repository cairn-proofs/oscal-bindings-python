"""Config-level tests for the Ruff lint/format setup in ``pyproject.toml``.

Feature: lint-and-format-enforcement

Everything here is a pure function of the parsed ``pyproject.toml``: no
subprocess, no Ruff invocation, no filesystem walk. The module exposes three
helpers that the property tests (Properties 1-3) reuse:

- ``load_ruff_config()`` -- the ``[tool.ruff]`` table, parsed once.
- ``matches(pattern, path)`` -- Ruff's ``per-file-ignores`` pattern semantics.
- ``ignored_codes(path)`` -- the union of codes ``per-file-ignores`` names for
  a path.

``matches`` is the one piece of real logic in this module. If it were wrong,
the properties built on it would pass vacuously, so it is pinned by example
tests below.

Ruff 0.16.8 ``per-file-ignores`` semantics (confirmed empirically against the
pinned binary in a scratch project, then encoded here):

1. A pattern is anchored at the project root and matched against the
   root-relative POSIX path. ``exact/j.py`` does not match ``other/exact/j.py``.
2. Ruff also matches the pattern against the file's basename alone, so a bare
   ``zz.py`` matches ``zz.py`` at any depth. Patterns containing ``/`` never
   match through this branch in practice.
3. Globs are globset-style with ``literal_separator`` off: ``*`` and ``?`` DO
   cross ``/`` (``star/*`` matches ``star/sub/k.py``).
4. ``**`` as a whole segment matches zero or more segments: ``a/**/*``
   matches ``a/x.py`` and ``a/b/x.py``; ``a/**`` matches anything under
   ``a/`` but not ``a_old/...``; a leading ``**/`` matches any prefix.

Character classes, brace alternation, and ``!`` negation are not used by this
repo's config; ``matches`` rejects them rather than guessing.
"""

from __future__ import annotations

import functools
import re
import tomllib
from pathlib import Path
from typing import Any

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"

_UNSUPPORTED_GLOB_CHARS = frozenset("[]{}")


@functools.cache
def load_pyproject() -> dict[str, Any]:
    """Parse ``pyproject.toml`` once per test session."""
    with PYPROJECT.open("rb") as fh:
        return tomllib.load(fh)


def load_ruff_config() -> dict[str, Any]:
    """Return the ``[tool.ruff]`` table."""
    return load_pyproject()["tool"]["ruff"]


def per_file_ignores() -> dict[str, list[str]]:
    """Return ``[tool.ruff.lint.per-file-ignores]`` (pattern -> codes)."""
    return load_ruff_config()["lint"]["per-file-ignores"]


@functools.cache
def _compile(pattern: str) -> re.Pattern[str]:
    """Translate a Ruff/globset pattern to an anchored regex (see module doc)."""
    if pattern.startswith("!") or _UNSUPPORTED_GLOB_CHARS & set(pattern):
        msg = f"unsupported glob syntax in {pattern!r}"
        raise ValueError(msg)
    segments = pattern.split("/")
    out: list[str] = []
    for index, segment in enumerate(segments):
        last = index == len(segments) - 1
        if segment == "**":
            # Trailing `/**` (or a lone `**`): everything below. Leading `**/`
            # or inner `/**/`: zero or more whole segments.
            out.append(".*" if last else "(?:.*/)?")
            continue
        piece = "".join(
            ".*" if ch == "*" else "." if ch == "?" else re.escape(ch) for ch in segment
        )
        out.append(piece if last else piece + "/")
    # `**` segments already carry their trailing separator.
    return re.compile("".join(out), re.DOTALL)


def matches(pattern: str, path: str) -> bool:
    """Whether a ``per-file-ignores`` pattern applies to a root-relative path."""
    regex = _compile(pattern)
    basename = path.rsplit("/", 1)[-1]
    return regex.fullmatch(path) is not None or regex.fullmatch(basename) is not None


def ignored_codes(path: str) -> set[str]:
    """Union of the codes every matching ``per-file-ignores`` entry names."""
    return {
        code
        for pattern, codes in per_file_ignores().items()
        if matches(pattern, path)
        for code in codes
    }


# --- Glob helper: literal patterns ---------------------------------------


@pytest.mark.parametrize(
    ("pattern", "path", "expected"),
    [
        # scripts/**/*
        ("scripts/**/*", "scripts/postprocess_models.py", True),
        ("scripts/**/*", "scripts/sub/deep.py", True),
        ("scripts/**/*", "src/scripts/x.py", False),
        ("scripts/**/*", "scripts_old/x.py", False),
        # tests/**/*
        ("tests/**/*", "tests/test_parser.py", True),
        ("tests/**/*", "tests/support/corpus.py", True),
        ("tests/**/*", "tests_extra/y.py", False),
        ("tests/**/*", "test/y.py", False),
        # src/oscal_bindings/v1/**
        ("src/oscal_bindings/v1/**", "src/oscal_bindings/v1/parser.py", True),
        (
            "src/oscal_bindings/v1/**",
            "src/oscal_bindings/v1/extensions/document.py",
            True,
        ),
        ("src/oscal_bindings/v1/**", "src/oscal_bindings/parser.py", False),
        (
            "src/oscal_bindings/v1/**",
            "src/oscal_bindings/extensions/__init__.py",
            False,
        ),
        ("src/oscal_bindings/v1/**", "src/oscal_bindings/v1_2/x.py", False),
        # Exact paths
        ("scripts/postprocess_models.py", "scripts/postprocess_models.py", True),
        ("scripts/postprocess_models.py", "scripts/other.py", False),
        ("scripts/postprocess_models.py", "src/scripts/postprocess_models.py", False),
    ],
)
def test_matches_repo_patterns(pattern: str, path: str, *, expected: bool) -> None:
    assert matches(pattern, path) is expected


REPO_INIT_FILES = [
    "src/oscal_bindings/__init__.py",
    "src/oscal_bindings/extensions/__init__.py",
    "src/oscal_bindings/v1/__init__.py",
    "src/oscal_bindings/v1/extensions/__init__.py",
    "tests/support/__init__.py",
]


@pytest.mark.parametrize("path", REPO_INIT_FILES)
def test_exact_shim_path_matches_only_itself(path: str) -> None:
    pattern = "src/oscal_bindings/__init__.py"
    assert matches(pattern, path) is (path == pattern)


@pytest.mark.parametrize(
    ("pattern", "path", "expected"),
    [
        # Empirically confirmed Ruff 0.16.8 behavior (module docstring, rules 2-4).
        ("zz.py", "zz.py", True),
        ("zz.py", "base/deep/zz.py", True),  # basename branch
        ("exact/j.py", "other/exact/j.py", False),  # anchored at root
        ("star/*", "star/sub/k.py", True),  # `*` crosses `/`
        ("**/conftest.py", "conftest.py", True),
        ("**/conftest.py", "a/b/conftest.py", True),
        ("a/**", "a_old/x.py", False),
    ],
)
def test_matches_ruff_semantics(pattern: str, path: str, *, expected: bool) -> None:
    assert matches(pattern, path) is expected


@pytest.mark.parametrize("pattern", ["!scripts/*", "src/[ab].py", "{a,b}/*.py"])
def test_matches_rejects_unsupported_syntax(pattern: str) -> None:
    with pytest.raises(ValueError, match="unsupported glob syntax"):
        matches(pattern, "a.py")


# --- ignored_codes against the real config -------------------------------


def test_every_configured_pattern_is_supported() -> None:
    for pattern in per_file_ignores():
        _compile(pattern)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (
            "scripts/postprocess_models.py",
            {"T201", "INP001", "PLR0912", "PLR0915"},
        ),
        ("scripts/other.py", {"T201", "INP001"}),
        (
            "tests/test_parser.py",
            {"PLR2004", "S101", "TID252", "PLC0415", "INP001"},
        ),
        ("src/oscal_bindings/v1/parser.py", {"EM101", "EM102", "TRY003"}),
        ("src/oscal_bindings/__init__.py", {"PLC0414"}),
        ("src/oscal_bindings/parser.py", set()),
        ("src/oscal_bindings/extensions/__init__.py", set()),
        ("src/oscal_bindings/v1_2/x.py", set()),
    ],
)
def test_ignored_codes(path: str, expected: set[str]) -> None:
    assert ignored_codes(path) == expected


# --- Shared path strategy (Properties 1 and 2) ---------------------------

# Directory prefixes, including the near-miss trees an over-broad glob would
# silently capture and the excluded trees that must be caught.
_DIR_PREFIXES = [
    "",
    "scripts",
    "script",
    "scripts_old",
    "src/scripts",
    "tests",
    "tests_extra",
    "test",
    "src/oscal_bindings",
    "src/oscal_bindings/v1",
    "src/oscal_bindings/extensions",
    "src/oscal_bindings/v1/extensions",
    "src/oscal_bindings/v1_2",
    "build",
    ".hatch",
    "docs",
]
_MIDDLE_SEGMENTS = ["sub", "support", "deep", "v1", "build", "pkg"]
_LEAVES = [
    "__init__.py",
    "x.py",
    "parser.py",
    "models.py",
    "conftest.py",
    "README.md",
    "notes.md",
    "data.json",
    "setup.cfg",
]
SHADOW_PATHS = [
    "src/oscal_bindings/extensions/__init__.py",
    "src/oscal_bindings/parser.py",
    "src/oscal_bindings/v1_2/x.py",
    "src/oscal_bindings/v1/__init__.py",
]


def _join(prefix: str, middle: list[str], leaf: str) -> str:
    return "/".join(part for part in [prefix, *middle, leaf] if part)


repo_paths: st.SearchStrategy[str] = st.one_of(
    st.builds(
        _join,
        st.sampled_from(_DIR_PREFIXES),
        st.lists(st.sampled_from(_MIDDLE_SEGMENTS), max_size=3),
        st.sampled_from(_LEAVES),
    ),
    st.sampled_from(SHADOW_PATHS),
)


# --- Property 1: exclusion is engine-symmetric ---------------------------

_ENGINE_SCOPED_EXCLUDE_KEYS = ("exclude", "extend-exclude")


def _normalize(pattern: str) -> str:
    """Ruff resolves patterns against the project root; drop a leading ``./``."""
    return pattern.removeprefix("./")


def exclusion_patterns(engine: str) -> list[str]:
    """Effective exclusion patterns for ``engine`` (``"lint"`` or ``"format"``).

    Top-level ``exclude``/``extend-exclude`` apply to both engines; the
    engine-scoped keys apply only to their own engine. Ruff's built-in default
    list is identical for both engines, so it cannot break symmetry and is
    not modelled here.
    """
    ruff = load_ruff_config()
    scoped = ruff.get(engine, {})
    return [
        _normalize(pattern)
        for table in (ruff, scoped)
        for key in _ENGINE_SCOPED_EXCLUDE_KEYS
        for pattern in table.get(key, [])
    ]


def is_excluded(engine: str, path: str) -> bool:
    """Whether ``engine`` skips a root-relative path.

    Ruff tests exclusion patterns against every directory it descends into as
    well as the file itself, so a directory pattern excludes everything below
    it. ``matches`` already covers the basename branch.
    """
    parts = path.split("/")
    candidates = ["/".join(parts[: i + 1]) for i in range(len(parts))]
    return any(
        matches(pattern, candidate)
        for pattern in exclusion_patterns(engine)
        for candidate in candidates
    )


def test_no_engine_scoped_exclusion_keys() -> None:
    ruff = load_ruff_config()
    for engine in ("lint", "format"):
        for key in _ENGINE_SCOPED_EXCLUDE_KEYS:
            assert key not in ruff.get(engine, {}), f"{engine}.{key} is set"


@pytest.mark.parametrize(
    "path",
    ["src/oscal_bindings/v1/models.py", "build/x.py", ".hatch/x.py", "README.md"],
)
@pytest.mark.parametrize("engine", ["lint", "format"])
def test_required_paths_excluded_by_both_engines(engine: str, path: str) -> None:
    assert is_excluded(engine, path)


@pytest.mark.parametrize(
    "path",
    [
        "src/oscal_bindings/v1/parser.py",
        "src/oscal_bindings/v1/__init__.py",
        "scripts/postprocess_models.py",
        "tests/test_parser.py",
    ],
)
@pytest.mark.parametrize("engine", ["lint", "format"])
def test_source_paths_walked_by_both_engines(engine: str, path: str) -> None:
    assert not is_excluded(engine, path)


@settings(max_examples=200)
@given(path=repo_paths)
@example(path="src/oscal_bindings/v1/models.py")
@example(path="build/x.py")
@example(path="build/sub/deep.py")
@example(path=".hatch/x.py")
@example(path="docs/notes.md")
def test_prop_exclusion_is_engine_symmetric(path: str) -> None:
    """Feature: lint-and-format-enforcement, Property 1: Exclusion is engine-symmetric.

    **Validates: Requirements 1.7, 3.1, 3.2, 3.3**
    """
    assert is_excluded("lint", path) == is_excluded("format", path)


# --- Property 2: per-file ignores are exactly scoped ---------------------

# The EXPECTED scoping, written down independently of pyproject.toml so a
# widened config glob (e.g. `src/oscal_bindings/**`) disagrees with it rather
# than silently redefining "correct". Code -> the only patterns allowed to
# exempt it. Sources: Req 1.6 (tests list), 2.1 (T201/INP001 under scripts),
# 2.2 (INP001 under tests), 2.3 (EM101/EM102/TRY003 under v1), 2.5 (PLC0414 at
# the shim), 2.9 (PLR0912/PLR0915 at the post-processor only).
EXPECTED_SCOPES: dict[str, frozenset[str]] = {
    "T201": frozenset({"scripts/**/*"}),
    "INP001": frozenset({"tests/**/*", "scripts/**/*"}),
    "PLR2004": frozenset({"tests/**/*"}),
    "S101": frozenset({"tests/**/*"}),
    "TID252": frozenset({"tests/**/*"}),
    "PLC0415": frozenset({"tests/**/*"}),
    "PLR0912": frozenset({"scripts/postprocess_models.py"}),
    "PLR0915": frozenset({"scripts/postprocess_models.py"}),
    "EM101": frozenset({"src/oscal_bindings/v1/**"}),
    "EM102": frozenset({"src/oscal_bindings/v1/**"}),
    "TRY003": frozenset({"src/oscal_bindings/v1/**"}),
    "PLC0414": frozenset({"src/oscal_bindings/__init__.py"}),
}
GOVERNED_CODES = sorted(EXPECTED_SCOPES)

# Real Ruff codes from selected families that no ignore entry names: they must
# never be exempt anywhere. Several are siblings of governed codes (EM103 next
# to EM101/EM102, PLR0913 next to PLR0912/PLR0915, T203 next to T201, S102 next
# to S101, TRY300 next to TRY003), which is where a sloppy prefix would leak.
UNGOVERNED_CODES = [
    "E501",
    "F401",
    "B007",
    "TRY300",
    "EM103",
    "PLR0911",
    "PLR0913",
    "PLC0206",
    "S102",
    "T203",
    "TID251",
    "RUF100",
]


def expected_ignored(code: str, path: str) -> bool:
    """Whether the spec table says ``code`` is exempt at ``path``."""
    return any(matches(pattern, path) for pattern in EXPECTED_SCOPES.get(code, ()))


py_repo_paths: st.SearchStrategy[str] = st.one_of(
    st.builds(
        _join,
        st.sampled_from(_DIR_PREFIXES),
        st.lists(st.sampled_from(_MIDDLE_SEGMENTS), max_size=3),
        st.sampled_from([leaf for leaf in _LEAVES if leaf.endswith(".py")]),
    ),
    st.sampled_from(SHADOW_PATHS),
    st.sampled_from(
        [
            "scripts/postprocess_models.py",
            "scripts/other.py",
            "src/oscal_bindings/__init__.py",
            "src/oscal_bindings/v1/parser.py",
        ]
    ),
)


def test_config_per_file_ignores_equal_expected_table() -> None:
    """The config's (pattern, code) pairs are exactly the spec table's."""
    configured = {
        (pattern, code)
        for pattern, codes in per_file_ignores().items()
        for code in codes
    }
    expected = {
        (pattern, code)
        for code, patterns in EXPECTED_SCOPES.items()
        for pattern in patterns
    }
    assert configured == expected


def test_ungoverned_codes_are_disjoint_from_governed() -> None:
    assert not set(UNGOVERNED_CODES) & set(GOVERNED_CODES)


@settings(max_examples=300)
@given(
    path=py_repo_paths,
    code=st.sampled_from(GOVERNED_CODES + UNGOVERNED_CODES),
)
@example(path="scripts/postprocess_models.py", code="PLR0912")
@example(path="scripts/postprocess_models.py", code="PLR0915")
@example(path="scripts/postprocess_models.py", code="T201")
@example(path="scripts/other.py", code="PLR0912")
@example(path="scripts/other.py", code="PLR0915")
@example(path="scripts/other.py", code="INP001")
@example(path="src/oscal_bindings/v1/parser.py", code="EM102")
@example(path="src/oscal_bindings/v1/parser.py", code="PLC0414")
@example(path="src/oscal_bindings/__init__.py", code="PLC0414")
@example(path="src/oscal_bindings/__init__.py", code="EM101")
@example(path="src/oscal_bindings/v1/__init__.py", code="PLC0414")
@example(path="src/oscal_bindings/extensions/__init__.py", code="EM101")
@example(path="src/oscal_bindings/extensions/__init__.py", code="PLC0414")
@example(path="src/oscal_bindings/parser.py", code="EM102")
@example(path="src/oscal_bindings/parser.py", code="TRY003")
@example(path="src/oscal_bindings/v1_2/x.py", code="EM101")
@example(path="src/scripts/x.py", code="T201")
@example(path="scripts_old/x.py", code="T201")
@example(path="tests_extra/y.py", code="S101")
@example(path="tests/support/corpus.py", code="INP001")
def test_prop_per_file_ignores_exactly_scoped(path: str, code: str) -> None:
    """Property 2: Per-file ignores are exactly scoped.

    Feature: lint-and-format-enforcement, Property 2: Per-file ignores are
    exactly scoped.

    For any repo-relative Python path and any governed code, the code is
    ignored at that path iff the path matches a pattern the spec table allows
    for it; ungoverned codes from selected families are never ignored.

    **Validates: Requirements 1.6, 2.1, 2.2, 2.3, 2.5, 2.7, 2.9**
    """
    assert (code in ignored_codes(path)) is expected_ignored(code, path)


# --- Property 3: the selection covers every governed code ----------------

# Pylint is the one linter whose selector ("PL") is shorter than its codes'
# letter prefix: Ruff splits it into PLC/PLE/PLR/PLW sub-linters.
_PYLINT_SUBLINTERS = frozenset({"PLC", "PLE", "PLR", "PLW"})


def _letters(code: str) -> str:
    """Leading alphabetic part of a rule code or selector (``T20`` -> ``T``)."""
    return re.match(r"[A-Z]*", code).group()  # type: ignore[union-attr]


def selector_covers(selector: str, code: str) -> bool:
    """Whether a Ruff ``select``/``ignore`` entry selects ``code``.

    Ruff selectors are prefixes, but over *linter-scoped* codes, not raw
    strings: ``E`` selects pycodestyle's ``E501`` and not flake8-errmsg's
    ``EM101``, and ``S`` selects bandit's ``S101`` and not ``SIM102``. A naive
    ``str.startswith`` would let ``E`` silently keep ``EM101`` "covered" after
    ``EM`` was trimmed from ``select``, so the linter letters must agree too.
    """
    if selector == "ALL":
        return True
    if not code.startswith(selector):
        return False
    if selector == "PL":
        return _letters(code) in _PYLINT_SUBLINTERS
    return _letters(selector) == _letters(code)


def is_reachable(code: str, select: list[str], ignore: list[str]) -> bool:
    """Some ``select`` entry covers ``code`` and no ``ignore`` entry does."""
    return any(selector_covers(s, code) for s in select) and not any(
        selector_covers(i, code) for i in ignore
    )


def _lint_select() -> list[str]:
    return load_ruff_config()["lint"]["select"]


def _lint_ignore() -> list[str]:
    lint = load_ruff_config()["lint"]
    return [*lint.get("ignore", []), *lint.get("extend-ignore", [])]


@pytest.mark.parametrize(
    ("selector", "code", "expected"),
    [
        ("T20", "T201", True),
        ("EM", "EM101", True),
        ("PL", "PLR2004", True),
        ("PL", "PLC0414", True),
        ("PLR", "PLR0912", True),
        ("TRY", "TRY003", True),
        ("S", "S101", True),
        ("E", "EM101", False),  # pycodestyle does not cover flake8-errmsg
        ("S", "SIM102", False),  # bandit does not cover flake8-simplify
        ("T", "TRY003", False),
        ("T20", "TID252", False),
        ("PLR", "PLC0415", False),
        ("ISC001", "ISC002", False),
    ],
)
def test_selector_covers(selector: str, code: str, *, expected: bool) -> None:
    assert selector_covers(selector, code) is expected


def test_select_is_explicit_family_list() -> None:
    """``ALL`` would make Property 3 hold trivially; the design lists families."""
    assert "ALL" not in _lint_select()


@pytest.mark.parametrize(
    ("dropped", "code"),
    [("TRY", "TRY003"), ("EM", "EM102"), ("PL", "PLC0414"), ("T20", "T201")],
)
def test_trimmed_select_loses_coverage(dropped: str, code: str) -> None:
    """Non-vacuity: removing a family from the real select breaks reachability."""
    select = _lint_select()
    assert is_reachable(code, select, _lint_ignore())
    trimmed = [s for s in select if s != dropped]
    assert not is_reachable(code, trimmed, _lint_ignore())


def test_ignore_entry_blocks_reachability() -> None:
    assert not is_reachable("TRY003", ["TRY"], ["TRY"])
    assert is_reachable("ISC002", ["ISC"], ["ISC001"])


@settings(max_examples=100)
@given(code=st.sampled_from(GOVERNED_CODES))
@example(code="EM102")
@example(code="PLC0414")
@example(code="TRY003")
def test_prop_selection_covers_governed_codes(code: str) -> None:
    """Property 3: The selection covers every governed code.

    Feature: lint-and-format-enforcement, Property 3: The selection covers
    every governed code.

    Every code with a ``per-file-ignores`` entry is selected and not globally
    ignored, so its exemption is meaningful rather than vacuous.

    **Validates: Requirements 1.2, 2.7**
    """
    assert is_reachable(code, _lint_select(), _lint_ignore())
