"""Downsample scanned PDFs so a whole file fits Gemini's upload cap."""

from pathlib import Path

import pymupdf as fitz

from caseboard.errors import CaseboardError

TARGET_BYTES = 18 * 1024 * 1024
HARD_CAP = 45 * 1024 * 1024


def prepare_pdf(source: Path, cache_dir: Path) -> Path:
    """Return the original when it is already small, otherwise a compressed copy."""
    if source.stat().st_size <= TARGET_BYTES:
        return source
    cache_dir.mkdir(parents=True, exist_ok=True)
    dest = cache_dir / f"{source.stem}.pdf"
    stamp = cache_dir / f"{source.stem}.stamp"
    signature = f"{source.stat().st_mtime_ns}:{source.stat().st_size}"
    if dest.exists() and stamp.exists() and stamp.read_text() == signature:
        if dest.stat().st_size <= HARD_CAP:
            return dest
    for scale in (0.8, 0.62, 0.48):
        _downsample(source, dest, scale)
        if dest.stat().st_size <= TARGET_BYTES:
            break
    if dest.stat().st_size > HARD_CAP:
        raise CaseboardError(f"{source.name} is still over the upload cap after compression")
    stamp.write_text(signature)
    return dest


def page_count(path: Path) -> int:
    document = fitz.open(path)
    try:
        return document.page_count
    finally:
        document.close()


def _downsample(source: Path, dest: Path, scale: float) -> None:
    src = fitz.open(source)
    out = fitz.open()
    try:
        matrix = fitz.Matrix(scale, scale)
        for page in src:
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            new_page = out.new_page(width=page.rect.width, height=page.rect.height)
            new_page.insert_image(page.rect, pixmap=pixmap)
        out.save(dest, garbage=4, deflate=True)
    finally:
        src.close()
        out.close()
