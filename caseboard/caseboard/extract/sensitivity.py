"""Initial provider-visibility guess, tightened by source and fact key."""

from caseboard.domain.enums import EventKind, SegmentKind, Sensitivity
from caseboard.domain.models import Evidence

LEGAL_KINDS = {
    SegmentKind.pleading,
    SegmentKind.discovery,
    SegmentKind.correspondence,
    SegmentKind.expert_report,
    SegmentKind.photo_id,
    SegmentKind.hipaa_authorization,
    SegmentKind.incident_report,
}

CLINICAL_KINDS = {
    SegmentKind.clinical_note,
    SegmentKind.imaging_report,
    SegmentKind.operative_report,
    SegmentKind.bill,
}

FIRM_EVENT_KINDS = {
    EventKind.filing,
    EventKind.correspondence,
    EventKind.exam,
    EventKind.demand,
    EventKind.call,
    EventKind.email,
    EventKind.note,
    EventKind.message,
}

_SENSITIVE_BITS = (
    "ssn",
    "social_security",
    "license_number",
    "hiv",
    "substance",
    "mental_health",
    "medicaid",
    "medicare",
    "ssd",
    "nofault",
    "no_fault",
    "damages",
    "policy",
    "employee_number",
    "settlement",
    "hipaa",
    "special_categor",
    "redisclosure",
    "expert",
    "draft",
    "missing_document",
    "injury_at_scene",
    "prior_index",
    "index_number",
)

_LEGAL_NAME_BITS = (
    "pleading",
    "discovery",
    "correspondence",
    "expert",
    "subpoena",
)


def coerce_segment_kind(value: str) -> SegmentKind:
    try:
        return SegmentKind(value)
    except ValueError:
        return SegmentKind.other


def coerce_event_kind(value: str) -> EventKind:
    try:
        return EventKind(value)
    except ValueError:
        return EventKind.treatment


def facet_sensitivity(
    kind: SegmentKind,
    facet_key: str,
) -> tuple[Sensitivity, str]:
    """Return the visibility label and why it was chosen."""
    key = facet_key.lower()
    if any(bit in key for bit in _SENSITIVE_BITS):
        return Sensitivity.firm_only, "Sensitive fact key"
    if kind in LEGAL_KINDS:
        return Sensitivity.firm_only, "Legal, defense, or identity source"
    if kind in CLINICAL_KINDS:
        return Sensitivity.provider_visible, "Treating clinical fact"
    return Sensitivity.firm_only, "Unclassified source stays with the firm"


def event_sensitivity(
    kind: EventKind,
    evidence: list[Evidence],
) -> tuple[Sensitivity, str]:
    if kind in FIRM_EVENT_KINDS:
        return Sensitivity.firm_only, "Firm event"
    for item in evidence:
        name = item.document.lower()
        if any(bit in name for bit in _LEGAL_NAME_BITS):
            return Sensitivity.firm_only, "Cited from a legal document"
    if kind in {EventKind.treatment, EventKind.imaging, EventKind.surgery, EventKind.accident}:
        return Sensitivity.provider_visible, "Clinical or accident event"
    return Sensitivity.firm_only, "Unclassified event stays with the firm"
