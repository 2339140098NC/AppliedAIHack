"""Validations that read stored documents and do not change them."""

import uuid

from caseboard.domain.enums import SegmentKind, Sensitivity, Severity
from caseboard.domain.models import (
    Communication,
    ComparisonGroup,
    Facet,
    Finding,
    Segment,
    SourceFile,
    TimelineEvent,
)
from caseboard.extract.compare import calendar_day
from caseboard.extract.sensitivity import LEGAL_KINDS
from caseboard.validate.critical import critical_findings

_DATED_KINDS = {"accident", "surgery", "filing"}
_ONCE = {"accident", "surgery", "filing", "demand"}
_SECRET_KEYS = ("ssn", "license_number")
_SECRET_WORDS = ("medicaid", "social security", " hiv", "policy number", "settlement")


def run_checks(
    sources: list[SourceFile],
    facets: list[Facet],
    _groups: list[ComparisonGroup],
    events: list[TimelineEvent],
    communications: list[Communication],
    segments: list[Segment] | None = None,
) -> list[Finding]:
    pages = {source.filename: source.page_count for source in sources}
    findings: list[Finding] = []
    findings.extend(_facet_evidence(facets, pages))
    findings.extend(critical_findings(facets, events, segments or []))
    findings.extend(_legal_labeled_clinical(facets))
    findings.extend(_redaction(facets))
    findings.extend(_sensitive_text(facets))
    findings.extend(_timeline(events))
    findings.extend(_clio(communications))
    return findings


def _facet_evidence(facets: list[Facet], pages: dict[str, int]) -> list[Finding]:
    findings = []
    for facet in facets:
        if not facet.evidence:
            findings.append(
                _finding(
                    "missing_evidence",
                    Severity.incomplete,
                    f"{facet.facet_key} has no document and page",
                    [facet.id],
                    [],
                )
            )
            continue
        for item in facet.evidence:
            count = pages.get(item.document)
            if item.page < 1 or (count is not None and item.page > count):
                findings.append(
                    _finding(
                        "page_out_of_range",
                        Severity.incomplete,
                        f"{facet.facet_key} cites {item.document} p.{item.page}",
                        [facet.id],
                        [item],
                    )
                )
    return findings


def _legal_labeled_clinical(facets: list[Facet]) -> list[Finding]:
    findings = []
    for facet in facets:
        kind = facet.segment_kind
        if not isinstance(kind, SegmentKind):
            kind = SegmentKind(kind)
        if facet.sensitivity == Sensitivity.provider_visible and kind in LEGAL_KINDS:
            findings.append(
                _finding(
                    "clinical_label_on_legal_source",
                    Severity.sensitive,
                    f"{facet.facet_key} is marked visible but came from {kind.value}",
                    [facet.id],
                    facet.evidence,
                )
            )
    return findings


def _redaction(facets: list[Facet]) -> list[Finding]:
    findings = []
    for facet in facets:
        key = facet.facet_key.lower()
        digits = "".join(ch for ch in (facet.value or "") if ch.isdigit())
        if any(bit in key for bit in _SECRET_KEYS) and facet.value and not facet.redacted:
            if len(digits) >= 7:
                findings.append(
                    _finding(
                        "redaction_ignored",
                        Severity.sensitive,
                        f"{facet.facet_key} has a filled value on a redacted identifier",
                        [facet.id],
                        facet.evidence,
                    )
                )
    return findings


def _sensitive_text(facets: list[Facet]) -> list[Finding]:
    findings = []
    for facet in facets:
        if facet.sensitivity != Sensitivity.provider_visible:
            continue
        text = (facet.value or "").lower()
        if any(word in text for word in _SECRET_WORDS):
            findings.append(
                _finding(
                    "sensitive_text_visible",
                    Severity.sensitive,
                    f"{facet.facet_key} is provider-visible and mentions a restricted topic",
                    [facet.id],
                    facet.evidence,
                )
            )
    return findings


def _timeline(events: list[TimelineEvent]) -> list[Finding]:
    findings = []
    for event in events:
        if event.origin != "pdf":
            continue
        if event.date is None and event.kind.value in _DATED_KINDS:
            findings.append(
                _finding(
                    "timeline_missing_date",
                    Severity.incomplete,
                    f"{event.label} has no date",
                    [event.id],
                    event.evidence,
                )
            )
    by_label: dict[str, list[TimelineEvent]] = {}
    for event in events:
        if event.origin == "pdf" and event.date and event.kind.value in _ONCE:
            by_label.setdefault(event.label.strip().lower(), []).append(event)
    for label, group in by_label.items():
        dates = {calendar_day(event.date) or event.date for event in group}
        if len(dates) > 1:
            findings.append(
                _finding(
                    "timeline_date_conflict",
                    Severity.conflict,
                    f"{label} is dated {', '.join(sorted(str(item) for item in dates))}",
                    [event.id for event in group],
                    [cite for event in group for cite in event.evidence],
                )
            )
    return findings


def _clio(communications: list[Communication]) -> list[Finding]:
    findings = []
    for item in communications:
        if item.sensitivity != Sensitivity.firm_only:
            findings.append(
                _finding(
                    "clio_not_firm_only",
                    Severity.sensitive,
                    f"Clio {item.source.value} {item.clio_id} is not firm-only",
                    [item.id],
                    [],
                )
            )
    return findings


def _finding(code, severity, message, record_ids, evidence) -> Finding:
    return Finding(
        id=str(uuid.uuid4()),
        code=code,
        severity=severity,
        message=message,
        record_ids=record_ids,
        evidence=list(evidence),
    )
