"""The photo ID contributes a headshot, not the rest of the card."""

import pymupdf as fitz

from caseboard.extract.portrait import _HEADSHOT, portrait_png


def test_portrait_is_the_headshot_crop() -> None:
    width, height = 600, 502
    samples = bytearray((0, 80, 160)) * (width * height)
    x0, y0 = int(width * _HEADSHOT[0]), int(height * _HEADSHOT[1])
    x1, y1 = int(width * _HEADSHOT[2]), int(height * _HEADSHOT[3])
    for y in range(y0, y1):
        for x in range(x0, x1):
            index = (y * width + x) * 3
            samples[index:index + 3] = bytes((220, 40, 40))
    sheet = fitz.Pixmap(fitz.csRGB, width, height, bytes(samples), 0)
    page = fitz.open().new_page(width=width, height=height)
    page.insert_image(page.rect, pixmap=sheet)
    png = portrait_png(page.parent.tobytes())
    shot = fitz.Pixmap(png)
    assert shot.width < width // 2
    assert shot.height < height
    red, _green, blue = shot.pixel(shot.width // 2, shot.height // 2)
    assert red > 180
    assert blue < 80
