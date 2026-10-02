"""Render one PDF page from Clio bytes. The file is not written to disk."""

from pathlib import Path

import pymupdf as fitz
from fastapi import HTTPException

from caseboard.clio.client import ClioClient
from caseboard.config import Settings
from caseboard.domain.enums import DocType
from caseboard.errors import CaseboardError
from caseboard.store.documents import DocumentStore


def page_bytes(settings: Settings, client: ClioClient, store: DocumentStore, filename: str) -> bytes:
    """Return the PDF for a saved source. Clio is fetched into memory."""
    if not filename or Path(filename).name != filename or not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=404)
    document_id = ""
    for row in store.list_type(DocType.source):
        if row.get("filename") == filename:
            document_id = str(row.get("clio_document_id") or "")
            break
    if document_id:
        try:
            return client.pdf_bytes(document_id)
        except CaseboardError as exc:
            raise HTTPException(status_code=404) from exc
    cached = settings.docs_dir / filename
    if cached.is_file():
        return cached.read_bytes()
    raise HTTPException(status_code=404)


def render_page(source: bytes, page_number: int) -> tuple[bytes, bool, int]:
    """Return a PNG, whether the page has no text layer, and the page count."""
    document = fitz.open(stream=source, filetype="pdf")
    try:
        count = document.page_count
        index = min(max(page_number, 1), count) - 1
        page = document[index]
        scanned = not page.get_text().strip()
        pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
        return pixmap.tobytes("png"), scanned, count
    finally:
        document.close()
