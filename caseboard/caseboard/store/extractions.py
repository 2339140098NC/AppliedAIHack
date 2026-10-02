"""Create, read, replace, and delete one PDF's stored extract."""

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel

from caseboard.domain.enums import DocType
from caseboard.domain.models import (
    Evidence,
    Facet,
    PdfExtract,
    Segment,
    SourceFile,
    TimelineEvent,
)
from caseboard.extract.assemble import build_groups
from caseboard.extract.stamp import extract_stamp
from caseboard.extract.sensitivity import (
    coerce_event_kind,
    coerce_segment_kind,
    event_sensitivity,
    facet_sensitivity,
)
from caseboard.store.documents import DocumentStore
from caseboard.store.upstash import UpstashDocumentStore

Store = DocumentStore | UpstashDocumentStore


class PdfExtraction(BaseModel):
    """One saved PDF: the source row plus the records that cite it."""

    source: SourceFile
    segments: list[Segment]
    facets: list[Facet]
    events: list[TimelineEvent]


class ExtractionRecords:
    """Replace a file's extract in place so a later run does not duplicate it."""

    def __init__(self, store: Store) -> None:
        self._store = store

    def list(self) -> list[SourceFile]:
        return [SourceFile.model_validate(row) for row in self._store.list_type(DocType.source)]

    def get(self, filename: str) -> PdfExtraction | None:
        source = next((item for item in self.list() if item.filename == filename), None)
        if source is None:
            return None
        return PdfExtraction(
            source=source,
            segments=_models(self._store, DocType.segment, Segment, lambda row: row.get("source_file") == filename),
            facets=_models(self._store, DocType.facet, Facet, lambda row: _cites(row, filename)),
            events=_models(
                self._store,
                DocType.timeline_event,
                TimelineEvent,
                lambda row: row.get("origin") == "pdf" and _cites(row, filename),
            ),
        )

    def replace(
        self,
        filename: str,
        document_id: str,
        version_id: str,
        extracted: PdfExtract,
        *,
        page_count: int | None = None,
    ) -> SourceFile:
        """Delete the previous extract for this file, then write the new one."""
        self.delete(filename)
        source = SourceFile(
            filename=filename,
            page_count=page_count if page_count is not None else _page_span(extracted),
            clio_document_id=document_id,
            clio_version_id=version_id,
            extracted_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            schema_id=extract_stamp(),
        )
        self._store.put(DocType.source, filename, source)
        self._store.put_many(DocType.segment, _segments(filename, extracted))
        self._store.put_many(DocType.facet, _facets(filename, extracted))
        self._store.put_many(DocType.timeline_event, _events(filename, extracted))
        return source

    def delete(self, filename: str) -> None:
        """Remove one PDF's source row and the records that cite it. Other files stay."""
        if not filename:
            return
        self._store.delete_ids(DocType.segment, _ids(self._store, DocType.segment, lambda row: row.get("source_file") == filename))
        self._store.delete_ids(DocType.facet, _ids(self._store, DocType.facet, lambda row: _cites(row, filename)))
        self._store.delete_ids(
            DocType.timeline_event,
            _ids(
                self._store,
                DocType.timeline_event,
                lambda row: row.get("origin") == "pdf" and _cites(row, filename),
            ),
        )
        self._store.delete_ids(DocType.source, _ids(self._store, DocType.source, lambda row: row.get("filename") == filename))

    def rebuild(self) -> None:
        """Rebuild comparison groups from the facets that are still stored."""
        facets = [Facet.model_validate(row) for row in self._store.list_type(DocType.facet)]
        groups = build_groups(facets)
        self._store.delete_type(DocType.group)
        self._store.put_many(DocType.group, [(group.id, group) for group in groups])


def _models(store: Store, doc_type: DocType, model: type[BaseModel], predicate) -> list:
    return [model.model_validate(row) for row in store.list_type(doc_type) if predicate(row)]


def _ids(store: Store, doc_type: DocType, predicate) -> list[str]:
    return [str(row["id"]) for row in store.list_type(doc_type) if predicate(row)]


def _cites(row: dict, filename: str) -> bool:
    return any(cite.get("document") == filename for cite in row.get("evidence") or [])


def _segments(filename: str, extracted: PdfExtract) -> list[tuple[str, Segment]]:
    rows = []
    for item in extracted.segments:
        record = Segment(
            id=str(uuid.uuid4()),
            source_file=filename,
            page_start=item.page_start,
            page_end=item.page_end,
            kind=coerce_segment_kind(item.kind),
            authored_by=item.authored_by,
            facility=item.facility,
            document_date=item.document_date,
            nyscef_index=item.nyscef_index,
            nyscef_doc=item.nyscef_doc,
        )
        rows.append((record.id, record))
    return rows


def _facets(filename: str, extracted: PdfExtract) -> list[tuple[str, Facet]]:
    rows = []
    for item in extracted.facets:
        kind = coerce_segment_kind(item.segment_kind)
        sensitivity, reason = facet_sensitivity(kind, item.facet_key)
        evidence = [Evidence(document=filename, page=cite.page, quote=cite.quote) for cite in item.evidence]
        record = Facet(
            id=str(uuid.uuid4()),
            facet_key=item.facet_key.strip(),
            value=(item.value or "").strip() or None,
            redacted=item.redacted,
            sensitivity=sensitivity,
            sensitivity_reason=reason,
            authored_by=item.authored_by,
            segment_kind=kind,
            evidence=evidence,
        )
        if record.facet_key:
            rows.append((record.id, record))
    return rows


def _events(filename: str, extracted: PdfExtract) -> list[tuple[str, TimelineEvent]]:
    rows = []
    for item in extracted.events:
        kind = coerce_event_kind(item.kind)
        evidence = [Evidence(document=filename, page=cite.page, quote=cite.quote) for cite in item.evidence]
        sensitivity, reason = event_sensitivity(kind, evidence)
        record = TimelineEvent(
            id=str(uuid.uuid4()),
            date=_blank(item.date),
            time=_blank(item.time),
            label=item.label.strip(),
            kind=kind,
            sensitivity=sensitivity,
            sensitivity_reason=reason,
            evidence=evidence,
            origin="pdf",
        )
        if record.label:
            rows.append((record.id, record))
    return rows


def _blank(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    return value.strip()


def _page_span(extracted: PdfExtract) -> int:
    pages = 0
    for item in extracted.segments:
        pages = max(pages, item.page_start, item.page_end)
    for item in [*extracted.facets, *extracted.events]:
        for cite in item.evidence:
            pages = max(pages, cite.page)
    return pages
