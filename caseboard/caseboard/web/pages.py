"""Render one PDF page, fetching the file from Clio when it is not cached."""

from pathlib import Path

import pymupdf as fitz
from fastapi import HTTPException

from caseboard.clio.client import ClioClient
from caseboard.config import Settings
from caseboard.domain.enums import DocType
from caseboard.store.documents import DocumentStore


def open_pdf(settings: Settings, client: ClioClient, store: DocumentStore, filename: str) -> Path:
    """Return a local copy, downloading that one document from Clio if needed."""
    if not filename or Path(filename).name != filename or not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=404)
    path = settings.docs_dir / filename
    if path.is_file():
        return path
    document_id = ""
    for row in store.list_type(DocType.source):
        if row.get("filename") == filename:
            document_id = str(row.get("clio_document_id") or "")
            break
    if not document_id:
        raise HTTPException(status_code=404)
    client.download_pdf(document_id, path)
    return path


def render_page(path: Path, page_number: int) -> tuple[bytes, bool, int]:
    """Return a PNG, whether the page has no text layer, and the page count."""
    document = fitz.open(path)
    try:
        count = document.page_count
        index = min(max(page_number, 1), count) - 1
        page = document[index]
        scanned = not page.get_text().strip()
        pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
        return pixmap.tobytes("png"), scanned, count
    finally:
        document.close()
