"""Tests for the OscalDoc facade."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from oscal_bindings import (
    OscalAccessError,
    OscalDateTime,
    OscalDoc,
    parse_oscal,
)
from oscal_bindings.models import (
    AssessmentResults,
    AssessmentResultsDocument,
    Catalog,
    CatalogDocument,
    MappingCollection,
    MappingCollectionDocument,
    Metadata,
    Result,
    SystemSecurityPlan,
    SystemSecurityPlanDocument,
)

OSCAL_VERSION = "1.2.1"
TEST_UUID = "f47ac10b-58cc-4372-a567-0e02b2c3d479"


def _metadata_block(title: str) -> dict:
    return {
        "title": title,
        "last-modified": "2026-01-01T00:00:00Z",
        "version": "1.0",
        "oscal-version": OSCAL_VERSION,
    }


MINIMAL_CATALOG = json.dumps(
    {"catalog": {"uuid": TEST_UUID, "metadata": _metadata_block("C")}}
)
MINIMAL_PROFILE = json.dumps(
    {
        "profile": {
            "uuid": TEST_UUID,
            "metadata": _metadata_block("P"),
            "imports": [{"href": "https://example.com/cat.json", "include-all": {}}],
        }
    }
)
MINIMAL_COMPONENT_DEFINITION = json.dumps(
    {
        "component-definition": {
            "uuid": TEST_UUID,
            "metadata": _metadata_block("CD"),
        }
    }
)
MINIMAL_POAM = json.dumps(
    {
        "plan-of-action-and-milestones": {
            "uuid": TEST_UUID,
            "metadata": _metadata_block("POAM"),
            "poam-items": [{"title": "Item 1", "description": "first"}],
        }
    }
)
MINIMAL_ASSESSMENT_PLAN = json.dumps(
    {
        "assessment-plan": {
            "uuid": TEST_UUID,
            "metadata": _metadata_block("AP"),
            "import-ssp": {"href": "https://example.com/ssp.json"},
            "reviewed-controls": {"control-selections": [{"include-all": {}}]},
        }
    }
)


def _ap_with_tasks(tasks: list[dict]) -> str:
    return json.dumps(
        {
            "assessment-plan": {
                "uuid": TEST_UUID,
                "metadata": _metadata_block("AP"),
                "import-ssp": {"href": "https://example.com/ssp.json"},
                "reviewed-controls": {"control-selections": [{"include-all": {}}]},
                "tasks": tasks,
            }
        }
    )


def _ar_with_results(results: list[dict]) -> str:
    return json.dumps(
        {
            "assessment-results": {
                "uuid": TEST_UUID,
                "metadata": _metadata_block("AR"),
                "import-ap": {"href": "https://example.com/ap.json"},
                "results": results,
            }
        }
    )


def _task(uuid: str, type_: str, title: str, **rest) -> dict:
    return {"uuid": uuid, "type": type_, "title": title, **rest}


def _result(uuid: str, title: str, start: str, end: str | None = None) -> dict:
    r = {
        "uuid": uuid,
        "title": title,
        "description": "r",
        "start": start,
        "reviewed-controls": {"control-selections": [{"include-all": {}}]},
    }
    if end is not None:
        r["end"] = end
    return r


class TestFacadeBasics:
    def test_from_json_returns_oscaldoc(self):
        doc = OscalDoc.from_json(MINIMAL_CATALOG)
        assert isinstance(doc, OscalDoc)

    def test_from_json_accepts_bytes(self):
        doc = OscalDoc.from_json(MINIMAL_CATALOG.encode("utf-8"))
        assert doc.oscal_version == OSCAL_VERSION
        assert doc.uuid == TEST_UUID

    def test_from_json_invalid_utf8_raises(self):
        from oscal_bindings import OscalParseError

        with pytest.raises(OscalParseError):
            OscalDoc.from_json(b"\xff\xfe not utf-8")

    def test_wraps_oscaldocument(self):
        parsed = parse_oscal(MINIMAL_CATALOG)
        doc = OscalDoc(parsed)
        assert doc.oscal_version == OSCAL_VERSION

    def test_wraps_per_type_wrapper(self):
        parsed = parse_oscal(MINIMAL_CATALOG)
        doc = OscalDoc(parsed.root)
        assert doc.oscal_version == OSCAL_VERSION

    def test_rejects_unrelated_object(self):
        with pytest.raises(TypeError, match="OSCAL document wrapper"):
            OscalDoc("not a wrapper")

    def test_repr_includes_body_type_and_uuid(self):
        doc = OscalDoc.from_json(MINIMAL_CATALOG)
        r = repr(doc)
        assert "Catalog" in r
        assert TEST_UUID in r


@pytest.mark.parametrize(
    "fixture",
    [
        MINIMAL_CATALOG,
        MINIMAL_PROFILE,
        MINIMAL_COMPONENT_DEFINITION,
        MINIMAL_POAM,
        MINIMAL_ASSESSMENT_PLAN,
        _ar_with_results([_result(TEST_UUID, "R", "2025-01-05T00:00:00Z")]),
    ],
)
class TestUniformAccessors:
    def test_oscal_version(self, fixture):
        doc = OscalDoc.from_json(fixture)
        assert doc.oscal_version == OSCAL_VERSION

    def test_uuid(self, fixture):
        doc = OscalDoc.from_json(fixture)
        assert doc.uuid == TEST_UUID

    def test_metadata(self, fixture):
        doc = OscalDoc.from_json(fixture)
        assert doc.metadata.last_modified is not None


class TestDispatchForHardToBuildTypes:
    """SSP and MappingCollection have deeply nested required fields; use
    model_construct() to verify the facade dispatch table covers them
    without standing up a full valid document."""

    def _metadata(self) -> Metadata:
        return Metadata.model_construct(
            title="t",
            last_modified="2026-01-01T00:00:00Z",
            version="1.0",
            oscal_version=OSCAL_VERSION,
        )

    def test_dispatches_to_ssp_body(self):
        body = SystemSecurityPlan.model_construct(
            uuid=TEST_UUID, metadata=self._metadata()
        )
        wrapper = SystemSecurityPlanDocument.model_construct(system_security_plan=body)
        doc = OscalDoc(wrapper)
        assert doc.uuid == TEST_UUID
        assert doc.oscal_version == OSCAL_VERSION
        assert doc.body is body

    def test_dispatches_to_mapping_collection_body(self):
        body = MappingCollection.model_construct(
            uuid=TEST_UUID, metadata=self._metadata()
        )
        wrapper = MappingCollectionDocument.model_construct(mapping_collection=body)
        doc = OscalDoc(wrapper)
        assert doc.uuid == TEST_UUID
        assert doc.body is body


class TestAssessmentPeriod:
    def test_raises_for_catalog(self):
        doc = OscalDoc.from_json(MINIMAL_CATALOG)
        with pytest.raises(OscalAccessError, match="AssessmentPlan"):
            doc.assessment_period()

    def test_raises_for_profile(self):
        doc = OscalDoc.from_json(MINIMAL_PROFILE)
        with pytest.raises(OscalAccessError):
            doc.assessment_period()

    def test_ap_without_tasks_returns_none_none(self):
        doc = OscalDoc.from_json(MINIMAL_ASSESSMENT_PLAN)
        assert doc.assessment_period() == (None, None)

    def test_ap_with_on_date_task(self):
        fixture = _ap_with_tasks(
            [
                _task(
                    TEST_UUID,
                    "milestone",
                    "T",
                    timing={"on-date": {"date": "2025-03-15T00:00:00Z"}},
                )
            ]
        )
        doc = OscalDoc.from_json(fixture)
        start, end = doc.assessment_period()
        assert start == datetime(2025, 3, 15, tzinfo=UTC)
        assert end == datetime(2025, 3, 15, tzinfo=UTC)

    def test_ap_with_date_range_task(self):
        fixture = _ap_with_tasks(
            [
                _task(
                    TEST_UUID,
                    "action",
                    "T",
                    timing={
                        "within-date-range": {
                            "start": "2025-01-05T00:00:00Z",
                            "end": "2025-01-30T00:00:00Z",
                        }
                    },
                )
            ]
        )
        doc = OscalDoc.from_json(fixture)
        assert doc.assessment_period() == (
            datetime(2025, 1, 5, tzinfo=UTC),
            datetime(2025, 1, 30, tzinfo=UTC),
        )

    def test_ap_aggregates_across_multiple_tasks(self):
        u2 = "00000000-0000-4000-8000-000000000002"
        fixture = _ap_with_tasks(
            [
                _task(
                    TEST_UUID,
                    "milestone",
                    "T1",
                    timing={"on-date": {"date": "2025-03-15T00:00:00Z"}},
                ),
                _task(
                    u2,
                    "action",
                    "T2",
                    timing={
                        "within-date-range": {
                            "start": "2025-01-05T00:00:00Z",
                            "end": "2025-04-30T00:00:00Z",
                        }
                    },
                ),
            ]
        )
        doc = OscalDoc.from_json(fixture)
        assert doc.assessment_period() == (
            datetime(2025, 1, 5, tzinfo=UTC),
            datetime(2025, 4, 30, tzinfo=UTC),
        )

    def test_ap_at_frequency_contributes_nothing(self):
        fixture = _ap_with_tasks(
            [
                _task(
                    TEST_UUID,
                    "action",
                    "T",
                    timing={"at-frequency": {"period": 7, "unit": "days"}},
                )
            ]
        )
        doc = OscalDoc.from_json(fixture)
        assert doc.assessment_period() == (None, None)

    def test_ap_walks_nested_tasks(self):
        u2 = "00000000-0000-4000-8000-000000000002"
        fixture = _ap_with_tasks(
            [
                _task(
                    TEST_UUID,
                    "milestone",
                    "Parent",
                    tasks=[
                        _task(
                            u2,
                            "milestone",
                            "Child",
                            timing={"on-date": {"date": "2025-06-01T00:00:00Z"}},
                        )
                    ],
                )
            ]
        )
        doc = OscalDoc.from_json(fixture)
        assert doc.assessment_period() == (
            datetime(2025, 6, 1, tzinfo=UTC),
            datetime(2025, 6, 1, tzinfo=UTC),
        )

    def test_ar_single_result_with_end(self):
        fixture = _ar_with_results(
            [
                _result(
                    TEST_UUID,
                    "R1",
                    "2025-02-01T00:00:00Z",
                    "2025-02-15T00:00:00Z",
                )
            ]
        )
        doc = OscalDoc.from_json(fixture)
        assert doc.assessment_period() == (
            datetime(2025, 2, 1, tzinfo=UTC),
            datetime(2025, 2, 15, tzinfo=UTC),
        )

    def test_ar_aggregates_across_results(self):
        u2 = "00000000-0000-4000-8000-000000000002"
        fixture = _ar_with_results(
            [
                _result(
                    TEST_UUID,
                    "R1",
                    "2025-02-01T00:00:00Z",
                    "2025-02-15T00:00:00Z",
                ),
                _result(
                    u2,
                    "R2",
                    "2025-01-20T00:00:00Z",
                    "2025-03-01T00:00:00Z",
                ),
            ]
        )
        doc = OscalDoc.from_json(fixture)
        assert doc.assessment_period() == (
            datetime(2025, 1, 20, tzinfo=UTC),
            datetime(2025, 3, 1, tzinfo=UTC),
        )

    def test_ar_result_without_end(self):
        fixture = _ar_with_results([_result(TEST_UUID, "R1", "2025-02-01T00:00:00Z")])
        doc = OscalDoc.from_json(fixture)
        start, end = doc.assessment_period()
        assert start == datetime(2025, 2, 1, tzinfo=UTC)
        assert end is None


def _on_date(uuid: str, date_text: str, **rest) -> dict:
    return _task(
        uuid, "milestone", "T", timing={"on-date": {"date": date_text}}, **rest
    )


U2 = "00000000-0000-4000-8000-000000000002"
U3 = "00000000-0000-4000-8000-000000000003"


class TestAssessmentPeriodDatetimes:
    """FAC-007: the bounds are datetimes ordered by instant, first in document order."""

    def test_the_bounds_are_oscal_datetimes(self):
        fixture = _ap_with_tasks([_on_date(TEST_UUID, "2025-03-15T00:00:00Z")])
        start, end = OscalDoc.from_json(fixture).assessment_period()
        assert isinstance(start, OscalDateTime)
        assert isinstance(end, OscalDateTime)
        assert start.to_string() == "2025-03-15T00:00:00Z"

    def test_bounds_are_ordered_by_instant_across_offsets(self):
        fixture = _ap_with_tasks(
            [
                _on_date(TEST_UUID, "2026-03-01T23:00:00-05:00"),
                _on_date(U2, "2026-03-02T01:00:00Z"),
            ]
        )
        start, end = OscalDoc.from_json(fixture).assessment_period()
        assert start.to_string() == "2026-03-02T01:00:00Z"
        assert end.to_string() == "2026-03-01T23:00:00-05:00"

    def test_a_bound_keeps_its_own_offset(self):
        fixture = _ap_with_tasks([_on_date(TEST_UUID, "2026-03-01T07:00:00-05:00")])
        start, _ = OscalDoc.from_json(fixture).assessment_period()
        assert start.utcoffset() == timedelta(hours=-5)

    def test_an_equal_instant_gives_the_first_value_in_document_order(self):
        fixture = _ap_with_tasks(
            [
                _on_date(
                    TEST_UUID,
                    "2026-03-01T12:00:00Z",
                    tasks=[_on_date(U2, "2026-03-01T07:00:00-05:00")],
                )
            ]
        )
        start, end = OscalDoc.from_json(fixture).assessment_period()
        assert start.to_string() == "2026-03-01T12:00:00Z"
        assert end.to_string() == "2026-03-01T12:00:00Z"

    def test_the_first_value_wins_whatever_the_offset_of_the_second(self):
        fixture = _ap_with_tasks(
            [
                _on_date(U2, "2026-03-01T07:00:00-05:00"),
                _on_date(TEST_UUID, "2026-03-01T12:00:00Z"),
            ]
        )
        start, end = OscalDoc.from_json(fixture).assessment_period()
        assert start.to_string() == "2026-03-01T07:00:00-05:00"
        assert end.to_string() == "2026-03-01T07:00:00-05:00"

    def test_a_task_comes_before_its_nested_tasks(self):
        fixture = _ap_with_tasks(
            [
                _on_date(
                    TEST_UUID,
                    "2026-03-01T12:00:00Z",
                    tasks=[_on_date(U2, "2026-03-01T12:00:00+00:00")],
                ),
                _on_date(U3, "2026-03-01T07:00:00-05:00"),
            ]
        )
        start, _ = OscalDoc.from_json(fixture).assessment_period()
        assert start.to_string() == "2026-03-01T12:00:00Z"

    def test_the_seventh_fraction_digit_orders_the_bounds(self):
        fixture = _ar_with_results(
            [
                _result(
                    TEST_UUID,
                    "R1",
                    "2026-03-01T10:00:00.1234568Z",
                    "2026-03-01T11:00:00Z",
                ),
                _result(
                    U2,
                    "R2",
                    "2026-03-01T05:00:00.1234567-05:00",
                    "2026-03-01T06:00:00.0000001-05:00",
                ),
            ]
        )
        start, end = OscalDoc.from_json(fixture).assessment_period()
        assert start.to_string() == "2026-03-01T05:00:00.1234567-05:00"
        assert end.to_string() == "2026-03-01T06:00:00.0000001-05:00"

    def test_digits_beyond_the_sixth_decide_an_otherwise_equal_instant(self):
        fixture = _ap_with_tasks(
            [
                _on_date(TEST_UUID, "2026-03-01T12:00:00.1234568Z"),
                _on_date(U2, "2026-03-01T12:00:00.1234567Z"),
            ]
        )
        start, end = OscalDoc.from_json(fixture).assessment_period()
        assert start.fraction == "1234567"
        assert end.fraction == "1234568"

    def test_a_within_date_range_gives_a_start_and_an_end(self):
        fixture = _ap_with_tasks(
            [
                _task(
                    TEST_UUID,
                    "action",
                    "T",
                    timing={
                        "within-date-range": {
                            "start": "2026-03-01T00:00:00Z",
                            "end": "2026-03-09T00:00:00Z",
                        }
                    },
                ),
                _on_date(U2, "2026-03-05T00:00:00Z"),
            ]
        )
        start, end = OscalDoc.from_json(fixture).assessment_period()
        assert start == datetime(2026, 3, 1, tzinfo=UTC)
        assert end == datetime(2026, 3, 9, tzinfo=UTC)

    def test_a_model_built_without_validation_still_gives_oscal_datetimes(self):
        body = AssessmentResults.model_construct(
            results=[
                Result.model_construct(
                    start=datetime(2026, 3, 1, tzinfo=UTC),
                    end=datetime(2026, 3, 2, tzinfo=UTC),
                )
            ]
        )
        doc = OscalDoc(
            AssessmentResultsDocument.model_construct(assessment_results=body)
        )
        start, end = doc.assessment_period()
        assert isinstance(start, OscalDateTime)
        assert isinstance(end, OscalDateTime)

    def test_the_docstring_says_to_compare_and_not_to_subtract(self):
        doc = OscalDoc.assessment_period.__doc__ or ""
        assert "do not subtract" in doc
        assert "microseconds" in doc
        assert "datetime.date" in doc
        assert "first of" in doc


class TestBodyAccess:
    def test_body_returns_correct_type(self):
        doc = OscalDoc.from_json(MINIMAL_CATALOG)
        assert isinstance(doc.body, Catalog)

    def test_wrapper_returns_underlying_wrapper(self):
        doc = OscalDoc.from_json(MINIMAL_CATALOG)
        assert isinstance(doc.wrapper, CatalogDocument)
