"""Pydantic contracts for Gemini output and stored JSON documents."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from caseboard.domain.enums import (
    CommSource,
    EventKind,
    GroupStatus,
    SegmentKind,
    Sensitivity,
    Severity,
)


class ModelEvidence(BaseModel):
    """Page citation returned by the model. The file name is stamped later."""

    model_config = ConfigDict(extra="ignore")

    page: int = 1
    quote: str = ""

    @field_validator("quote")
    @classmethod
    def clip_quote(cls, value: str) -> str:
        return value.strip()[:400]


class ModelFacet(BaseModel):
    model_config = ConfigDict(extra="ignore")

    facet_key: str
    value: str | None = None
    redacted: bool = False
    sensitivity: Sensitivity = Sensitivity.firm_only
    sensitivity_reason: str = ""
    authored_by: str = ""
    segment_kind: str = SegmentKind.other.value
    evidence: list[ModelEvidence] = Field(default_factory=list)


class ModelSegment(BaseModel):
    model_config = ConfigDict(extra="ignore")

    page_start: int = 1
    page_end: int = 1
    kind: str = SegmentKind.other.value
    authored_by: str = ""
    facility: str = ""
    document_date: str = ""
    nyscef_index: str = ""
    nyscef_doc: str = ""


class ModelEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    date: str | None = None
    time: str | None = None
    label: str
    kind: str = EventKind.treatment.value
    sensitivity: Sensitivity = Sensitivity.firm_only
    evidence: list[ModelEvidence] = Field(default_factory=list)


class PdfExtract(BaseModel):
    """One structured response for a whole PDF."""

    model_config = ConfigDict(extra="ignore")

    segments: list[ModelSegment] = Field(default_factory=list)
    facets: list[ModelFacet] = Field(default_factory=list)
    events: list[ModelEvent] = Field(default_factory=list)


class Evidence(BaseModel):
    document: str
    page: int
    quote: str = ""


class SourceFile(BaseModel):
    filename: str
    page_count: int = 0
    clio_document_id: str = ""
    clio_version_id: str = ""
    extracted_at: str = ""
    schema_id: str = ""


class Segment(BaseModel):
    id: str
    source_file: str
    page_start: int
    page_end: int
    kind: SegmentKind
    authored_by: str = ""
    facility: str = ""
    document_date: str = ""
    nyscef_index: str = ""
    nyscef_doc: str = ""


class Facet(BaseModel):
    id: str
    facet_key: str
    value: str | None = None
    redacted: bool = False
    sensitivity: Sensitivity
    sensitivity_reason: str
    authored_by: str = ""
    segment_kind: SegmentKind
    evidence: list[Evidence] = Field(default_factory=list)


class GroupEntry(BaseModel):
    facet_id: str
    value: str | None
    authored_by: str = ""
    sensitivity: Sensitivity
    evidence: list[Evidence] = Field(default_factory=list)


class ComparisonGroup(BaseModel):
    id: str
    facet_key: str
    status: GroupStatus
    entries: list[GroupEntry]


class TimelineEvent(BaseModel):
    id: str
    date: str | None = None
    time: str | None = None
    label: str
    kind: EventKind
    sensitivity: Sensitivity
    sensitivity_reason: str
    facet_ids: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    origin: str = "pdf"


class Communication(BaseModel):
    id: str
    clio_id: str
    source: CommSource
    subject: str = ""
    body: str = ""
    occurred_on: str | None = None
    occurred_time: str = ""
    author: str = ""
    sender: str = ""
    recipients: list[str] = Field(default_factory=list)
    sensitivity: Sensitivity = Sensitivity.firm_only
    matter_id: str = ""


class ProviderShare(BaseModel):
    """What a firm user has chosen to send to one provider."""

    id: str
    provider: str
    excluded: list[str] = Field(default_factory=list)
    sent_at: str = ""
    sent_ids: list[str] = Field(default_factory=list)


class ItemGlance(BaseModel):
    """A lawyer's one-line reading of one timeline item."""

    id: str
    category: str
    line: str
    urgent: bool = False


class CaseSummary(BaseModel):
    """A case overview, the action in front of the lawyer, and the buttons under it."""

    id: str
    line: str
    overview: str = ""
    actions: list[str] = Field(default_factory=list)


class Charge(BaseModel):
    """One dollar amount printed on a bill. The figure is copied, not computed."""

    id: str
    provider: str
    description: str
    amount: str
    service_date: str = ""
    document: str
    page: int = 1
    quote: str = ""


class ClientPortrait(BaseModel):
    """The client's headshot. The rest of the photo ID stays out of this record."""

    id: str
    source_file: str
    png_base64: str


class Finding(BaseModel):
    id: str
    code: str
    severity: Severity
    message: str
    record_ids: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    resolved: bool = False
