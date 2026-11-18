"""Tests for the ``binding-surface`` and ``schema-versioning`` scenarios (issue #49).

Each test cites the scenarios it verifies with ``@pytest.mark.spec``. The
tests that were already in the suite carry their markers where they stand;
this module holds the tests that were missing.
"""

from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import pytest
from support import spec_artifact
from support.expected_failures import EXPECTED_FAILURES
from support.scripts import load_script

from oscal_bindings import v1
from oscal_bindings.v1 import models

pin = load_script("spec_artifact")

_RECORD = Path(__file__).resolve().parent.parent / "openspec" / "traceability.json"

_CATALOG = {
    "catalog": {
        "uuid": "11111111-1111-4111-8111-111111111111",
        "metadata": {
            "title": "t",
            "last-modified": "2024-01-01T00:00:00Z",
            "version": "1",
            "oscal-version": "1.2.3",
        },
    }
}

_PARSE_OPERATIONS = sorted(
    name
    for name in v1.__all__
    if name.startswith("parse_")
    and not name.endswith("_file")
    and not hasattr(models, name)
)


def _record() -> dict:
    return json.loads(_RECORD.read_text("utf-8"))


def _entry(name: str) -> dict:
    return {op["name"]: op for op in _record()["operations"]}[name]


def _index() -> dict[str, dict]:
    path = spec_artifact.ensure_spec_artifact() / "openspec" / "requirements.json"
    return {e["id"]: e for e in json.loads(path.read_text("utf-8"))["requirements"]}


# -- binding-surface -----------------------------------------------------------


@pytest.mark.spec("SRF-001.01", "SRF-003.01")
def test_the_bytes_parse_operation_is_recorded_under_document_parsing() -> None:
    document = v1.parse_oscal(json.dumps(_CATALOG).encode())
    assert isinstance(document.root, models.CatalogDocument)
    assert "PRS-001" in _entry("parse_oscal")["requirements"]
    assert _index()["PRS-001"]["capability"] == "document-parsing"


@pytest.mark.spec("SRF-001.02", "SRF-002.02")
@pytest.mark.parametrize("name", _PARSE_OPERATIONS)
def test_no_public_operation_accepts_xml(name: str) -> None:
    assert not [n for n in v1.__all__ if "xml" in n.lower()]
    with pytest.raises(v1.OscalParseError):
        getattr(v1, name)("<catalog xmlns='http://csrc.nist.gov/ns/oscal/1.0'/>")


@pytest.mark.spec("SRF-001.03")
def test_generated_types_are_public_and_need_no_record_entry() -> None:
    recorded = {op["name"] for op in _record()["operations"]}
    generated = {
        name for name in v1.__all__ if getattr(models, name, None) is getattr(v1, name)
    }
    assert {"CatalogDocument", "DocumentId"} <= generated
    assert not generated & recorded


@pytest.mark.spec("SRF-002.03")
@pytest.mark.parametrize(
    "name", ["parse_oscal", "parse_catalog", "parse_oscal_yaml", "parse_catalog_yaml"]
)
def test_no_public_parse_operation_accepts_unknown_fields(name: str) -> None:
    bad = json.loads(json.dumps(_CATALOG))
    bad["catalog"]["unknown-field"] = 1
    with pytest.raises(v1.OscalParseError) as info:
        getattr(v1, name)(json.dumps(bad))
    assert not isinstance(info.value, v1.OscalDocumentTypeMismatchError)
    assert [(e["type"], e["loc"][-1]) for e in info.value.errors] == [
        ("extra_forbidden", "unknown-field")
    ]


@pytest.mark.spec("SRF-003.03")
def test_the_facade_entry_covers_the_assessment_period_accessor() -> None:
    assert "FAC-004" in _entry("OscalDoc")["requirements"]
    assert inspect.getattr_static(v1.OscalDoc, "assessment_period")
    recorded = {op["name"] for op in _record()["operations"]}
    assert "assessment_period" not in recorded
    assert not any(name.startswith("OscalDoc.") for name in recorded)


@pytest.mark.spec("SRF-006.01")
def test_the_pinned_index_has_the_entry_of_a_requirement() -> None:
    assert _index()["PRS-001"] == {
        "id": "PRS-001",
        "capability": "document-parsing",
        "title": "Parse an OSCAL document from text or bytes",
    }


@pytest.mark.spec("SRF-006.03")
def test_the_pinned_index_has_no_entry_for_a_retired_requirement() -> None:
    ledger = (
        spec_artifact.ensure_spec_artifact() / "openspec" / "spec-ids.yaml"
    ).read_text("utf-8")
    retired = ledger.split("retired:", 1)[1]
    retired_ids = set(
        re.findall(r"^  - id: ([A-Z]{2,5}-\d{3})$", retired, re.MULTILINE)
    )
    assert "MDL-004" in retired_ids
    assert not retired_ids & set(_index())


@pytest.mark.spec("SRF-006.04", "SRF-007.03")
def test_the_pinned_artifact_holds_the_index_and_the_record_schema() -> None:
    openspec = spec_artifact.ensure_spec_artifact() / "openspec"
    assert (openspec / "requirements.json").is_file()
    assert (openspec / "traceability.schema.json").is_file()


# -- schema-versioning ---------------------------------------------------------


@pytest.mark.spec("VER-002.01")
def test_the_active_release_is_the_pinned_identifier_not_the_newest_directory(
    tmp_path: Path,
) -> None:
    for release in ("0.0.1", pin.OSCAL_RELEASE, "99.0.0"):
        (tmp_path / "schemas" / release).mkdir(parents=True)
        (tmp_path / "corpus" / release).mkdir(parents=True)
    paths = pin.artifact_paths(tmp_path)
    assert paths.schema.parent.name == pin.OSCAL_RELEASE
    assert paths.corpus.name == pin.OSCAL_RELEASE
    assert paths.names.parent.name == pin.OSCAL_RELEASE
    assert pin.SPEC_ARTIFACT_VERSION.split("+oscal.")[1] == pin.OSCAL_RELEASE


@pytest.mark.spec("VER-004.01")
def test_the_artifact_version_carries_the_oscal_release_as_build_metadata() -> None:
    version = (spec_artifact.ensure_spec_artifact() / "VERSION").read_text().strip()
    assert version == pin.SPEC_ARTIFACT_VERSION
    assert version.endswith(f"+oscal.{pin.OSCAL_RELEASE}")
    assert re.fullmatch(r"\d+\.\d+\.\d+\+oscal\.\d+\.\d+\.\d+", version)


@pytest.mark.spec("VER-005.01")
def test_the_pin_records_a_content_hash() -> None:
    assert re.fullmatch(r"[0-9a-f]{64}", pin.SPEC_ARTIFACT_SHA256)
    assert pin.SPEC_ARTIFACT.sha256 == pin.SPEC_ARTIFACT_SHA256


@pytest.mark.spec("VER-007.01")
def test_expected_failures_are_local_and_the_pinned_corpus_holds_none() -> None:
    corpus = spec_artifact.corpus_root()
    cases = json.loads((corpus / "cases.json").read_text("utf-8"))
    assert "known-defects" not in cases
    assert "defect-twins" not in cases
    assert not [c["id"] for c in cases["cases"] if "known-defects" in c]
    assert set(EXPECTED_FAILURES) <= {c["id"] for c in cases["cases"]}
