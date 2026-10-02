"""Render one PDF page from Clio bytes. The file is not written to disk."""

import threading
from pathlib import Path

import pymupdf as fitz
from fastapi import HTTPException

from caseboard.clio.client import ClioClient
from caseboard.config import Settings
from caseboard.domain.enums import DocType
from caseboard.errors import CaseboardError
from caseboard.store.documents import DocumentStore

_LOCK = threading.Lock()
_PDFS: dict[str, bytes] = {}
_PNGS: dict[tuple[str, int], bytes] = {}
_MAX_PDFS = 4
_MAX_PNGS = 24


def page_bytes(settings: Settings, client: ClioClient, store: DocumentStore, filename: str) -> bytes:
    """Return the PDF for a saved source. Clio is fetched into memory."""
    if not filename or Path(filename).name != filename or not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=404)
    with _LOCK:
        remembered = _PDFS.get(filename)
    if remembered is not None:
        return remembered
    row = store.get(DocType.source, filename)
    document_id = str((row or {}).get("clio_document_id") or "")
    if document_id:
        try:
            payload = client.pdf_bytes(document_id)
        except CaseboardError as exc:
            raise HTTPException(status_code=404) from exc
        _remember_pdf(filename, payload)
        return payload
    cached = settings.docs_dir / filename
    if cached.is_file():
        payload = cached.read_bytes()
        _remember_pdf(filename, payload)
        return payload
    raise HTTPException(status_code=404)


def cached_page(filename: str, page_number: int) -> bytes | None:
    with _LOCK:
        return _PNGS.get((filename, page_number))


def remember_page(filename: str, page_number: int, png: bytes) -> None:
    with _LOCK:
        if len(_PNGS) >= _MAX_PNGS:
            _PNGS.clear()
        _PNGS[(filename, page_number)] = png


def _remember_pdf(filename: str, payload: bytes) -> None:
    with _LOCK:
        if len(_PDFS) >= _MAX_PDFS:
            _PDFS.clear()
        _PDFS[filename] = payload


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
