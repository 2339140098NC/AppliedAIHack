"""One PDF's stored segments, facts, and timeline events."""

from caseboard.domain.enums import Sensitivity
from caseboard.domain.models import Facet, Segment, TimelineEvent
from caseboard.web.workspace.query import WorkspaceQuery


def build_extract_detail(
    segments: list[Segment],
    facets: list[Facet],
    events: list[TimelineEvent],
    query: WorkspaceQuery,
) -> dict | None:
    """Firm-only reading of what Gemini stored for the open PDF."""
    filename = query.document
    if not query.firm or query.panel != "extract" or not filename or filename.startswith("clio:"):
        return None
    file_segments = [item for item in segments if item.source_file == filename]
    file_facets = [item for item in facets if any(cite.document == filename for cite in item.evidence)]
    file_events = [
        item
        for item in events
        if item.origin == "pdf" and any(cite.document == filename for cite in item.evidence)
    ]
    return {
        "filename": filename,
        "title": _title(filename),
        "empty": not file_segments and not file_facets and not file_events,
        "page_href": query.url(document=filename, page=1, quote="", drawer="1", panel=""),
        "segments": [_segment_row(item) for item in file_segments],
        "facts": [_fact_row(item, filename, query) for item in file_facets],
        "events": [_event_row(item, filename, query) for item in file_events],
    }


def _segment_row(segment: Segment) -> dict:
    who = ", ".join(part for part in (segment.authored_by, segment.facility, segment.document_date) if part)
    return {
        "kind": segment.kind.value.replace("_", " ").title(),
        "pages": _span(segment.page_start, segment.page_end),
        "who": who,
    }


def _fact_row(facet: Facet, filename: str, query: WorkspaceQuery) -> dict:
    cite = next((item for item in facet.evidence if item.document == filename), None)
    page = cite.page if cite else 1
    quote = cite.quote if cite else ""
    return {
        "title": _title(facet.facet_key),
        "value": facet.value.strip() if facet.value and facet.value.strip() else "Left blank",
        "blank": not (facet.value and facet.value.strip()),
        "redacted": facet.redacted,
        "firm_only": facet.sensitivity == Sensitivity.firm_only,
        "href": query.url(document=filename, page=page, quote=quote, drawer="1", panel=""),
        "label": f"p. {page}",
    }


def _event_row(event: TimelineEvent, filename: str, query: WorkspaceQuery) -> dict:
    cite = next((item for item in event.evidence if item.document == filename), None)
    page = cite.page if cite else 1
    return {
        "when": event.date or "Undated",
        "kind": event.kind.value.replace("_", " ").title(),
        "label": event.label,
        "href": query.url(document=filename, page=page, quote=cite.quote if cite else "", drawer="1", panel=""),
        "page": f"p. {page}",
    }


def _title(key: str) -> str:
    text = key.replace(".pdf", "").replace(".", " ").replace("_", " ").replace("-", " ").strip()
    stem = text.split("__")[-1]
    return stem[:1].upper() + stem[1:] if stem else "Fact"


def _span(start: int, end: int) -> str:
    if start == end:
        return f"p. {start}"
    return f"pp. {start}–{end}"
