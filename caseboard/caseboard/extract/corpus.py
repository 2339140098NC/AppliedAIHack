"""Turn a Gemini extract into stored facets, segments, and events."""

import uuid
from pathlib import Path

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
from caseboard.extract.compress import page_count, prepare_pdf
from caseboard.extract.gemini import GeminiExtractor
from caseboard.extract.sensitivity import (
    coerce_event_kind,
    coerce_segment_kind,
    event_sensitivity,
    facet_sensitivity,
)
from caseboard.store.documents import DocumentStore

_HIGH_RES_BITS = ("photo-id", "hipaa", "medical-records", "medical-bills")


class CorpusExtractor:
    """Extract every PDF in the corpus and replace the PDF-derived documents."""

    def __init__(
        self,
        store: DocumentStore,
        extractor: GeminiExtractor,
        corpus_dir: Path,
        compress_dir: Path,
    ) -> None:
        self._store = store
        self._extractor = extractor
        self._corpus_dir = corpus_dir
        self._compress_dir = compress_dir

    def pdfs(self) -> list[Path]:
        if not self._corpus_dir.is_dir():
            return []
        return sorted(self._corpus_dir.rglob("*.pdf"))

    def run(self, on_progress) -> list[str]:
        files = self.pdfs()
        self.begin()
        problems: list[str] = []
        for index, path in enumerate(files, start=1):
            on_progress(f"Extracting {index}/{len(files)} {path.name}")
            try:
                self.ingest(path, "")
            except Exception as exc:
                problems.append(f"{path.name}: {exc}")
        self.finish()
        return problems

    def begin(self) -> None:
        self._store.delete_type(DocType.source)
        self._store.delete_type(DocType.segment)
        self._store.delete_type(DocType.facet)
        self._store.delete_type(DocType.group)
        self._store.delete_type(DocType.timeline_event, origin="pdf")

    def ingest(self, path: Path, clio_document_id: str) -> None:
        self._one(path, clio_document_id)

    def finish(self) -> None:
        self._rebuild_groups()

    def _one(self, path: Path, clio_document_id: str) -> None:
        prepared = prepare_pdf(path, self._compress_dir)
        high = any(bit in path.name.lower() for bit in _HIGH_RES_BITS)
        extracted = self._extractor.extract_pdf(prepared, high_resolution=high)
        count = page_count(path)
        source = SourceFile(
            filename=path.name,
            page_count=count,
            clio_document_id=clio_document_id,
        )
        self._store.put(DocType.source, path.name, source)
        self._store_extract(path.name, extracted)

    def _store_extract(self, filename: str, extracted: PdfExtract) -> None:
        segments = []
        for item in extracted.segments:
            kind = coerce_segment_kind(item.kind)
            record = Segment(
                id=str(uuid.uuid4()),
                source_file=filename,
                page_start=item.page_start,
                page_end=item.page_end,
                kind=kind,
                authored_by=item.authored_by,
                facility=item.facility,
                document_date=item.document_date,
                nyscef_index=item.nyscef_index,
                nyscef_doc=item.nyscef_doc,
            )
            segments.append((record.id, record))
        facets = []
        for item in extracted.facets:
            kind = coerce_segment_kind(item.segment_kind)
            sensitivity, reason = facet_sensitivity(kind, item.facet_key)
            evidence = [
                Evidence(document=filename, page=cite.page, quote=cite.quote)
                for cite in item.evidence
            ]
            text = (item.value or "").strip() or None
            record = Facet(
                id=str(uuid.uuid4()),
                facet_key=item.facet_key.strip(),
                value=text,
                redacted=item.redacted,
                sensitivity=sensitivity,
                sensitivity_reason=reason,
                authored_by=item.authored_by,
                segment_kind=kind,
                evidence=evidence,
            )
            if record.facet_key:
                facets.append((record.id, record))
        events = []
        for item in extracted.events:
            kind = coerce_event_kind(item.kind)
            evidence = [
                Evidence(document=filename, page=cite.page, quote=cite.quote)
                for cite in item.evidence
            ]
            sensitivity, reason = event_sensitivity(kind, evidence)
            record = TimelineEvent(
                id=str(uuid.uuid4()),
                date=_blank_to_none(item.date),
                time=_blank_to_none(item.time),
                label=item.label.strip(),
                kind=kind,
                sensitivity=sensitivity,
                sensitivity_reason=reason,
                evidence=evidence,
                origin="pdf",
            )
            if record.label:
                events.append((record.id, record))
        self._store.put_many(DocType.segment, segments)
        self._store.put_many(DocType.facet, facets)
        self._store.put_many(DocType.timeline_event, events)

    def _rebuild_groups(self) -> None:
        facets = [Facet.model_validate(row) for row in self._store.list_type(DocType.facet)]
        groups = build_groups(facets)
        self._store.delete_type(DocType.group)
        self._store.put_many(DocType.group, [(group.id, group) for group in groups])


def _blank_to_none(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    return value.strip()
