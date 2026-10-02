"""Replacing one PDF extract leaves the other files alone."""

from pathlib import Path

from caseboard.domain.models import ModelEvidence, ModelEvent, ModelFacet, ModelSegment, PdfExtract
from caseboard.store.documents import DocumentStore
from caseboard.store.extractions import ExtractionRecords
from caseboard.store.upstash import UpstashDocumentStore
from tests.test_upstash_store import MemoryRedis


def test_replace_and_delete_one_pdf_on_sqlite(tmp_path: Path) -> None:
    _assert_crud(DocumentStore(tmp_path / "case.sqlite"))


def test_replace_and_delete_one_pdf_on_upstash() -> None:
    _assert_crud(UpstashDocumentStore(MemoryRedis()))  # type: ignore[arg-type]


def _assert_crud(store: DocumentStore | UpstashDocumentStore) -> None:
    records = ExtractionRecords(store)
    records.replace("a.pdf", "1", "v1", _extract("Justin", "Visit"))
    records.replace("b.pdf", "2", "v1", _extract("Other", "Note"))
    first = records.get("a.pdf")
    assert first is not None
    assert first.source.clio_version_id == "v1"
    assert [facet.value for facet in first.facets] == ["Justin"]
    records.replace("a.pdf", "1", "v2", _extract("Justin W", "Visit"))
    updated = records.get("a.pdf")
    assert updated is not None
    assert updated.source.clio_version_id == "v2"
    assert [facet.value for facet in updated.facets] == ["Justin W"]
    assert len(updated.events) == 1
    other = records.get("b.pdf")
    assert other is not None and [facet.value for facet in other.facets] == ["Other"]
    records.delete("a.pdf")
    assert records.get("a.pdf") is None
    assert [item.filename for item in records.list()] == ["b.pdf"]


def _extract(value: str, label: str) -> PdfExtract:
    evidence = [ModelEvidence(page=1, quote=value)]
    return PdfExtract(
        segments=[ModelSegment(page_end=2)],
        facets=[ModelFacet(facet_key="patient.name", value=value, evidence=evidence)],
        events=[ModelEvent(label=label, evidence=[ModelEvidence(page=1, quote=label)])],
    )
