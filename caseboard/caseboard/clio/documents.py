"""Save Clio matter PDFs on disk and record them in the document store."""

from pathlib import Path

from caseboard.clio.client import ClioClient
from caseboard.domain.enums import DocType
from caseboard.domain.models import SourceFile
from caseboard.extract.compress import page_count
from caseboard.store.documents import DocumentStore


class MatterPdfs:
    """Download a matter's PDFs once. The board reads the copies, not Clio."""

    def __init__(self, client: ClioClient, store: DocumentStore, directory: Path) -> None:
        self._client = client
        self._store = store
        self._directory = directory

    def pull(self, matter_id: str, on_progress) -> int:
        chosen = stored_pdfs(self._client.list_documents(matter_id))
        self._directory.mkdir(parents=True, exist_ok=True)
        saved: list[tuple[str, SourceFile]] = []
        for index, (document_id, filename) in enumerate(chosen, start=1):
            on_progress(f"Saving PDF {index}/{len(chosen)} {filename}")
            dest = self._directory / filename
            self._client.download_pdf(document_id, dest)
            saved.append((filename, SourceFile(filename=filename, page_count=page_count(dest))))
        kept = {filename for filename, _record in saved}
        for path in self._directory.glob("*.pdf"):
            if path.name not in kept:
                path.unlink()
        self._store.delete_type(DocType.source)
        self._store.put_many(DocType.source, saved)
        return len(saved)


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
