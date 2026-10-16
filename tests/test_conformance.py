"""Conformance runner: the pinned OSCAL bindings corpus, run against this binding.

One test per case in ``corpus/<release>/cases.json`` of the pinned spec
artifact (``tests/support/spec_artifact.py``). The operations and case fields
are defined in the artifact's ``corpus/<release>/README.md``. A case whose
``known-defects`` names this binding is a strict expected failure: when the
defect is fixed, the case passes unexpectedly and the run fails until the mark
is removed.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
from support.canonical_json import canonicalize
from support.spec_artifact import corpus_root

import oscal_bindings as ob
from oscal_bindings import OscalAccessError, OscalDoc, OscalParseError

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

BINDING = "oscal-bindings-python"

TYPED_PARSERS: dict[str, Callable[[str | bytes], Any]] = {
    "catalog": ob.parse_catalog,
    "profile": ob.parse_profile,
    "component-definition": ob.parse_component_definition,
    "system-security-plan": ob.parse_system_security_plan,
    "assessment-plan": ob.parse_assessment_plan,
    "assessment-results": ob.parse_assessment_results,
    "plan-of-action-and-milestones": ob.parse_plan_of_action_and_milestones,
    "mapping-collection": ob.parse_mapping_collection,
}


def category(error: BaseException) -> str | None:
    """Map an exception to a corpus error category, or None for any other error.

    The library has no typed error for a document-type mismatch or an unknown
    element type, so those two categories come from the message prefix.
    """
    if isinstance(error, FileNotFoundError):
        return "not-found"
    if isinstance(error, OscalAccessError):
        return "access-error"
    if isinstance(error, OscalParseError):
        message = str(error)
        if message.startswith("Document is not"):
            return "document-type-mismatch"
        if message.startswith("Unknown element type"):
            return "unknown-element-type"
        return "parse-error"
    return None


def _load_cases() -> list[Any]:
    cases = json.loads((corpus_root() / "cases.json").read_text("utf-8"))["cases"]
    params = []
    for case in cases:
        defects = [d for d in case.get("known-defects", []) if d["binding"] == BINDING]
        marks = [
            pytest.mark.xfail(strict=True, reason=f"known defect: {d['issue']}")
            for d in defects
        ]
        params.append(pytest.param(case, id=case["id"], marks=marks))
    return params


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Parametrize ``case`` with every corpus case. A fetch failure fails the run."""
    if "case" in metafunc.fixturenames:
        metafunc.parametrize("case", _load_cases())


def _expect_error(case: dict[str, Any], run: Callable[[], object]) -> BaseException:
    """Run ``run`` and assert it raises the case's expected category."""
    with pytest.raises(Exception) as info:  # noqa: PT011 -- the category is checked below
        run()
    error = info.value
    got = category(error)
    assert got is not None, f"unmapped error {type(error).__name__}: {error}"
    assert got == case["expected-category"], f"category {got}: {error}"
    return error


def _round_trip(case: dict[str, Any], src: Path) -> None:
    data = src.read_bytes()
    doc = ob.parse_oscal(data.decode("utf-8"))
    TYPED_PARSERS[case["document-type"]](data)
    assert ob.validate_oscal(data) is True
    expected = (corpus_root() / case["expected"]).read_bytes()
    assert canonicalize(ob.serialize_oscal(doc)) == expected


def _parse(case: dict[str, Any], src: Path) -> None:
    data: str | bytes = src.read_bytes()
    if case.get("input-form") != "bytes":
        data = data.decode("utf-8")
    error = _expect_error(case, lambda: ob.parse_oscal(data))
    minimum = case.get("expected-min-failures")
    if minimum is not None:
        assert isinstance(error, OscalParseError)
        assert len(error.errors) >= minimum, error.errors
    assert ob.validate_oscal(data) is False


def _parse_typed(case: dict[str, Any], src: Path) -> None:
    parser = TYPED_PARSERS[case["document-type"]]
    _expect_error(case, lambda: parser(src.read_bytes()))


def _parse_file(case: dict[str, Any], src: Path) -> None:
    error = _expect_error(case, lambda: ob.parse_oscal_file(src))
    assert str(src) in str(error)


def _assessment_period(case: dict[str, Any], src: Path) -> None:
    doc = OscalDoc(ob.parse_oscal(src.read_bytes()))
    _expect_error(case, doc.assessment_period)


def _validate_element(case: dict[str, Any], src: Path) -> None:
    element = json.loads(src.read_text("utf-8"))
    if "expected-category" in case:
        _expect_error(case, lambda: ob.validate_element(element, case["element-type"]))
        return
    result = ob.validate_element(element, case["element-type"])
    assert result.valid is case["expected-valid"], result.errors


OPERATIONS: dict[str, Callable[[dict[str, Any], Path], None]] = {
    "round-trip": _round_trip,
    "parse": _parse,
    "parse-typed": _parse_typed,
    "parse-file": _parse_file,
    "assessment-period": _assessment_period,
    "validate-element": _validate_element,
}


def test_case(case: dict[str, Any]) -> None:
    """Run one corpus case and compare its result with the expected result."""
    assert case["operation"] in OPERATIONS, f"unknown operation {case['operation']}"
    OPERATIONS[case["operation"]](case, corpus_root() / case["input"])


def test_every_category_is_mapped() -> None:
    """Each category in the corpus has a branch in ``category``."""
    index = json.loads((corpus_root() / "cases.json").read_text("utf-8"))
    mapped = {
        category(FileNotFoundError()),
        category(OscalAccessError()),
        category(OscalParseError("Document is not a Catalog")),
        category(OscalParseError("Unknown element type: x")),
        category(OscalParseError("Failed to parse")),
    }
    assert set(index["categories"]) == mapped
