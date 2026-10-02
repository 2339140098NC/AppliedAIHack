"""Render one PDF page for the workspace viewer."""

from pathlib import Path

import pymupdf as fitz
from fastapi import HTTPException

from caseboard.config import Settings


def find_pdf(settings: Settings, filename: str) -> Path:
    """Resolve a stored Clio PDF by its file name."""
    if not filename or Path(filename).name != filename or not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=404)
    path = settings.docs_dir / filename
    if not path.is_file():
        raise HTTPException(status_code=404)
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
