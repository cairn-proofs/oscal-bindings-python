"""Document-level facade for parsed OSCAL documents.

`OscalDoc` wraps any of the 8 per-type document wrappers (or the
`OscalDocument` union root) and exposes uniform accessors that don't
require callers to know which body type they hold.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from oscal_bindings.v1._datetime import OscalDateTime
from oscal_bindings.v1.models import (
    AssessmentPlan,
    AssessmentPlanDocument,
    AssessmentResults,
    AssessmentResultsDocument,
    Catalog,
    CatalogDocument,
    ComponentDefinition,
    ComponentDefinitionDocument,
    MappingCollection,
    MappingCollectionDocument,
    Metadata,
    OscalDocument,
    PlanOfActionAndMilestones,
    PlanOfActionAndMilestonesDocument,
    Profile,
    ProfileDocument,
    SystemSecurityPlan,
    SystemSecurityPlanDocument,
)
from oscal_bindings.v1.parser import parse_oscal, parse_oscal_file

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import datetime
    from pathlib import Path

OscalBody = (
    Catalog
    | Profile
    | SystemSecurityPlan
    | AssessmentPlan
    | AssessmentResults
    | PlanOfActionAndMilestones
    | ComponentDefinition
    | MappingCollection
)

OscalWrapper = (
    CatalogDocument
    | ProfileDocument
    | SystemSecurityPlanDocument
    | AssessmentPlanDocument
    | AssessmentResultsDocument
    | PlanOfActionAndMilestonesDocument
    | ComponentDefinitionDocument
    | MappingCollectionDocument
)


_WRAPPER_TO_BODY_ATTR: dict[type, str] = {
    CatalogDocument: "catalog",
    ProfileDocument: "profile",
    SystemSecurityPlanDocument: "system_security_plan",
    AssessmentPlanDocument: "assessment_plan",
    AssessmentResultsDocument: "assessment_results",
    PlanOfActionAndMilestonesDocument: "plan_of_action_and_milestones",
    ComponentDefinitionDocument: "component_definition",
    MappingCollectionDocument: "mapping_collection",
}


class OscalAccessError(Exception):
    """Raised when a typed accessor is called on the wrong document type."""


class OscalDoc:
    """Uniform document-level accessor over a parsed OSCAL document.

    Every OSCAL top-level document carries `metadata` and a body-level
    `uuid`, but the path from the JSON-wrapper class to that body varies
    by document type (`doc.catalog.metadata` vs
    `doc.system_security_plan.metadata`). `OscalDoc` collapses that
    dispatch into a single shape.

    Example:
        >>> doc = OscalDoc.from_file("catalog.json")
        >>> doc.oscal_version
        '1.2.0'
        >>> doc.metadata.title
        'NIST SP 800-53 Rev 5 Catalog'
    """

    __slots__ = ("_wrapper",)

    def __init__(self, wrapper: OscalWrapper | OscalDocument) -> None:
        if isinstance(wrapper, OscalDocument):
            wrapper = wrapper.root
        if not isinstance(wrapper, tuple(_WRAPPER_TO_BODY_ATTR)):
            raise TypeError(
                "Expected an OSCAL document wrapper or OscalDocument, "
                f"got {type(wrapper).__name__}"
            )
        self._wrapper = wrapper

    @classmethod
    def from_json(cls, data: str | bytes) -> OscalDoc:
        """Parse an OSCAL JSON document and wrap it.

        Accepts `str` or `bytes`. Passing `bytes` skips an intermediate
        UTF-8 decode and avoids one document-size string allocation,
        which matters when consuming OSCAL from byte-sources (HTTP
        response body, S3 GET, file read, container layer pull).
        """
        return cls(parse_oscal(data))

    @classmethod
    def from_file(cls, path: Path | str) -> OscalDoc:
        """Parse an OSCAL JSON file and wrap it."""
        return cls(parse_oscal_file(path))

    @property
    def wrapper(self) -> OscalWrapper:
        """The underlying per-type document wrapper."""
        return self._wrapper

    @property
    def body(self) -> OscalBody:
        """The document body (`Catalog`, `Profile`, `SystemSecurityPlan`, ...)."""
        attr = _WRAPPER_TO_BODY_ATTR[type(self._wrapper)]
        return getattr(self._wrapper, attr)

    @property
    def metadata(self) -> Metadata:
        """The document's metadata block."""
        return self.body.metadata

    @property
    def oscal_version(self) -> str:
        """The `metadata.oscal-version` string."""
        return self.metadata.oscal_version

    @property
    def uuid(self) -> str:
        """The body's top-level UUID.

        Every OSCAL 1.x body type carries one, so this never raises for
        a validly parsed document.
        """
        return self.body.uuid

    def assessment_period(self) -> tuple[OscalDateTime | None, OscalDateTime | None]:
        """Return `(start, end)` datetimes for an Assessment Plan or Assessment Results.

        Each bound is `None` or an `OscalDateTime` of the document, with its
        instant, its offset, and every fraction digit of its text (FAC-007).

        For an Assessment Plan, walks `tasks[].timing` (including nested
        `tasks[].tasks[]`) and aggregates:

        - `on-date` contributes one datetime, which is both a start and an end.
        - `within-date-range` contributes its `start` and its `end`.
        - `at-frequency` contributes nothing.

        For Assessment Results, aggregates `results[].start` and
        `results[].end`.

        The start is the earliest of the start values and the end is the latest
        of the end values. Values are ordered by instant, so
        `2026-03-01T23:00:00-05:00` is later than `2026-03-02T01:00:00Z`, and
        the comparison counts every fraction digit. When two or more values
        have the earliest (or the latest) instant, the bound is the first of
        them in document order, where a task comes before its nested tasks. The
        bound keeps its own offset: it is not converted to UTC.

        Returns `(None, None)` if no datetime is present.

        Note:
            **Compare the bounds, do not subtract them.** `end - start` is a
            `timedelta` of microseconds, so it drops the digits beyond the
            sixth; see `OscalDateTime`.

        Warning:
            Before this version `assessment_period()` returned `datetime.date`
            values. A caller that needs a date calls `.date()` on a bound.

        Raises:
            OscalAccessError: If called on a non-AP/AR document.
        """
        body = self.body
        if isinstance(body, AssessmentPlan):
            return _ap_assessment_period(body)
        if isinstance(body, AssessmentResults):
            return _ar_assessment_period(body)
        raise OscalAccessError(
            "assessment_period() is only defined for AssessmentPlan and "
            f"AssessmentResults; got {type(body).__name__}"
        )

    def __repr__(self) -> str:
        return f"OscalDoc({type(self.body).__name__} uuid={self.uuid})"


def _as_oscal_datetime(value: datetime) -> OscalDateTime:
    """Return ``value`` as an `OscalDateTime` (a model built without validation)."""
    return (
        value
        if isinstance(value, OscalDateTime)
        else OscalDateTime.from_datetime(value)
    )


def _bounds(
    starts: Iterable[datetime], ends: Iterable[datetime]
) -> tuple[OscalDateTime | None, OscalDateTime | None]:
    """Return the earliest start and the latest end, the first value on a tie.

    Both iterables are in document order. A value replaces the bound only when
    it is strictly earlier (start) or strictly later (end), so an equal instant
    keeps the first value (FAC-007).
    """
    start: OscalDateTime | None = None
    for value in starts:
        candidate = _as_oscal_datetime(value)
        if start is None or candidate < start:
            start = candidate
    end: OscalDateTime | None = None
    for value in ends:
        candidate = _as_oscal_datetime(value)
        if end is None or candidate > end:
            end = candidate
    return start, end


def _ap_assessment_period(
    ap: AssessmentPlan,
) -> tuple[OscalDateTime | None, OscalDateTime | None]:
    starts: list[datetime] = []
    ends: list[datetime] = []
    for task in ap.tasks or []:
        _collect_task_dates(task, starts, ends)
    return _bounds(starts, ends)


def _collect_task_dates(task, starts: list[datetime], ends: list[datetime]) -> None:
    # A task comes before the tasks that it holds (FAC-007, document order).
    timing = task.timing
    if timing is not None:
        on_date = getattr(timing, "on_date", None)
        if on_date is not None:
            starts.append(on_date.date)
            ends.append(on_date.date)
        range_ = getattr(timing, "within_date_range", None)
        if range_ is not None:
            starts.append(range_.start)
            ends.append(range_.end)
    for child in task.tasks or []:
        _collect_task_dates(child, starts, ends)


def _ar_assessment_period(
    ar: AssessmentResults,
) -> tuple[OscalDateTime | None, OscalDateTime | None]:
    return _bounds(
        [r.start for r in ar.results],
        [r.end for r in ar.results if r.end is not None],
    )
