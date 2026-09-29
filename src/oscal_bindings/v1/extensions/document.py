"""Document-level facade for parsed OSCAL documents.

`OscalDoc` wraps any of the 8 per-type document wrappers (or the
`OscalDocument` union root) and exposes uniform accessors that don't
require callers to know which body type they hold.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

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
    from datetime import date
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

    def assessment_period(self) -> tuple[date | None, date | None]:
        """Return `(start, end)` dates for an Assessment Plan or Assessment Results.

        For an Assessment Plan, walks `tasks[].timing` (including nested
        `tasks[].tasks[]`) and aggregates:

        - `on-date` contributes a single point in time.
        - `within-date-range` contributes its `start` and `end`.
        - `at-frequency` contributes nothing (no calendar dates).

        For Assessment Results, aggregates `results[].start` and
        `results[].end`.

        Precedence rule: when multiple date sources are present, the
        earliest start and the latest end across all sources win.
        Returns `(None, None)` if no calendar dates are present.

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


def _ap_assessment_period(
    ap: AssessmentPlan,
) -> tuple[date | None, date | None]:
    starts: list[date] = []
    ends: list[date] = []
    for task in ap.tasks or []:
        _collect_task_dates(task, starts, ends)
    return (min(starts) if starts else None, max(ends) if ends else None)


def _collect_task_dates(task, starts: list[date], ends: list[date]) -> None:
    timing = task.timing
    if timing is not None:
        on_date = getattr(timing, "on_date", None)
        if on_date is not None:
            starts.append(on_date.date.date())
            ends.append(on_date.date.date())
        range_ = getattr(timing, "within_date_range", None)
        if range_ is not None:
            starts.append(range_.start.date())
            ends.append(range_.end.date())
    for child in task.tasks or []:
        _collect_task_dates(child, starts, ends)


def _ar_assessment_period(
    ar: AssessmentResults,
) -> tuple[date | None, date | None]:
    starts = [r.start.date() for r in ar.results]
    ends = [r.end.date() for r in ar.results if r.end is not None]
    return (min(starts) if starts else None, max(ends) if ends else None)
