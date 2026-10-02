"""Record Clio PDF names. The bytes are fetched when a page or extract needs them."""

from pathlib import Path

from caseboard.clio.client import ClioClient
from caseboard.domain.enums import DocType
from caseboard.domain.models import SourceFile
from caseboard.store.documents import DocumentStore


class MatterPdfs:
    """Remember which Clio PDFs belong to the matter. Bytes are fetched later."""

    def __init__(self, client: ClioClient, store: DocumentStore) -> None:
        self._client = client
        self._store = store

    def catalog(self, matter_id: str) -> int:
        chosen = stored_pdfs(self._client.list_documents(matter_id))
        rows = [
            (filename, SourceFile(filename=filename, clio_document_id=document_id))
            for document_id, filename in chosen
        ]
        self._store.delete_type(DocType.source)
        self._store.put_many(DocType.source, rows)
        return len(rows)


def stored_pdfs(documents: list[dict]) -> list[tuple[str, str]]:
    """Return (clio id, filename) for uploaded PDFs, skipping duplicate names."""
    taken: set[str] = set()
    chosen: list[tuple[str, str]] = []
    for item in documents:
        filename = _pdf_name(item, taken)
        if filename is None:
            continue
        taken.add(filename)
        chosen.append((str(item.get("id")), filename))
    return chosen


def _pdf_name(item: dict, taken: set[str]) -> str | None:
    version = item.get("latest_document_version") or {}
    if version.get("fully_uploaded") is False:
        return None
    filename = Path(str(version.get("filename") or item.get("name") or "")).name
    kind = str(version.get("content_type") or "").lower()
    if kind != "application/pdf" and not filename.lower().endswith(".pdf"):
        return None
    if not filename.lower().endswith(".pdf"):
        filename = f"{filename}.pdf" if filename else f"{item.get('id')}.pdf"
    if filename in taken:
        filename = f"{item.get('id')}__{filename}"
    return filename
