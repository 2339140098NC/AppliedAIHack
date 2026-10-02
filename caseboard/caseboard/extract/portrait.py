"""Crop the client's headshot out of the photo-id scan."""

import base64

import pymupdf as fitz

from caseboard.domain.enums import DocType
from caseboard.domain.models import ClientPortrait
from caseboard.store.documents import DocumentStore
from caseboard.store.upstash import UpstashDocumentStore

Store = DocumentStore | UpstashDocumentStore

# Fractions of the photo-id scan. They frame the headshot and leave the card text out.
_HEADSHOT = (0.133, 0.319, 0.350, 0.717)
PORTRAIT_ID = "client"


def is_photo_id(filename: str) -> bool:
    return "photo-id" in filename.lower()


def portrait_png(pdf: bytes) -> bytes:
    """Return a PNG of the headshot on the first embedded image."""
    document = fitz.open(stream=pdf, filetype="pdf")
    try:
        images = document[0].get_images()
        if not images:
            raise ValueError("photo id has no image")
        source = fitz.Pixmap(document, images[0][0])
        if source.n >= 5:
            source = fitz.Pixmap(fitz.csRGB, source)
        width, height = source.width, source.height
        box = fitz.Rect(
            width * _HEADSHOT[0],
            height * _HEADSHOT[1],
            width * _HEADSHOT[2],
            height * _HEADSHOT[3],
        )
        page = fitz.open().new_page(width=width, height=height)
        page.insert_image(page.rect, pixmap=source)
        shot = page.get_pixmap(clip=box, alpha=False)
        return shot.tobytes("png")
    finally:
        document.close()


def save_portrait(store: Store, pdf: bytes, filename: str) -> None:
    """Replace the stored headshot for this case."""
    encoded = base64.b64encode(portrait_png(pdf)).decode("ascii")
    store.put(
        DocType.portrait,
        PORTRAIT_ID,
        ClientPortrait(id=PORTRAIT_ID, source_file=filename, png_base64=encoded),
    )
