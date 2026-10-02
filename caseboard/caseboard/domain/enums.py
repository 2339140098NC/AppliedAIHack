"""Closed sets for document kinds, audiences, and findings."""

from enum import Enum


class Sensitivity(str, Enum):
    firm_only = "firm_only"
    provider_visible = "provider_visible"


class Audience(str, Enum):
    firm = "firm"
    provider = "provider"


class SegmentKind(str, Enum):
    clinical_note = "clinical_note"
    imaging_report = "imaging_report"
    operative_report = "operative_report"
    bill = "bill"
    hipaa_authorization = "hipaa_authorization"
    photo_id = "photo_id"
    pleading = "pleading"
    discovery = "discovery"
    correspondence = "correspondence"
    expert_report = "expert_report"
    incident_report = "incident_report"
    other = "other"


class GroupStatus(str, Enum):
    conflict = "conflict"
    consistent = "consistent"
    incomplete = "incomplete"


class EventKind(str, Enum):
    accident = "accident"
    treatment = "treatment"
    imaging = "imaging"
    surgery = "surgery"
    filing = "filing"
    correspondence = "correspondence"
    exam = "exam"
    demand = "demand"
    call = "call"
    email = "email"
    note = "note"
    message = "message"


class DocType(str, Enum):
    source = "source"
    segment = "segment"
    facet = "facet"
    group = "group"
    timeline_event = "timeline_event"
    communication = "communication"
    validation = "validation"
    portrait = "portrait"
    share = "share"
    glance = "glance"
    charge = "charge"
    summary = "summary"


class Severity(str, Enum):
    conflict = "conflict"
    incomplete = "incomplete"
    sensitive = "sensitive"


class CommSource(str, Enum):
    phone = "phone"
    email = "email"
    note = "note"
    message = "message"
