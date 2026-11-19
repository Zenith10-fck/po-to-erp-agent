"""Opens a PDF and gives the gates what they need: page text, word positions, hidden text
and page images. Uses PyMuPDF. No model calls here."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pymupdf as fitz

from .normalize import squash

MIN_WORDS_FOR_TEXT_LAYER = 15
TINY_FONT_PT = 3.5


@dataclass
class Word:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def yc(self) -> float:
        return (self.y0 + self.y1) / 2


@dataclass
class Page:
    number: int                 # 1-based
    text: str                   # whitespace-squashed text layer ("" for a scan)
    words: list[Word] = field(default_factory=list)
    hidden_text: list[str] = field(default_factory=list)  # white or tiny text found in the layer
    has_text_layer: bool = False


@dataclass
class Document:
    path: Path
    pages: list[Page]

    @property
    def is_text_pdf(self) -> bool:
        """True only if every page has a usable text layer. One scanned page makes it a scan."""
        return bool(self.pages) and all(p.has_text_layer for p in self.pages)

    def page(self, number: int | None) -> Page | None:
        if number is None or number < 1 or number > len(self.pages):
            return None
        return self.pages[number - 1]


VISIBLE_DPI = 100
MIN_INK_CONTRAST = 60     # darkest vs lightest pixel inside a word's box, 0-255 grey


def _hidden_spans(page: "fitz.Page") -> list[str]:
    """Text that is in the text layer but a person cannot see on the page.

    Judged by the rendered page, not by the text colour: inside the box of each span there
    must be real ink contrast. This catches white on white, very light grey, text covered by a
    white box and invisible text (render mode 3), and still allows white text on a dark band.
    Tiny text (under 3.5 pt) is always reported."""
    pix = page.get_pixmap(dpi=VISIBLE_DPI, colorspace=fitz.csGRAY, annots=False)
    buf, width, height = pix.samples, pix.width, pix.height
    sx, sy = width / page.rect.width, height / page.rect.height
    out = []
    for block in page.get_text("dict").get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = squash(span.get("text", ""))
                if not any(ch.isalnum() for ch in text):
                    continue
                if span.get("size", 10) < TINY_FONT_PT:
                    out.append(text)
                    continue
                x0, y0, x1, y1 = span["bbox"]
                c0, c1 = max(0, int(x0 * sx)), min(width, int(x1 * sx) + 1)
                r0, r1 = max(0, int(y0 * sy)), min(height, int(y1 * sy) + 1)
                if c1 <= c0 or r1 <= r0:
                    out.append(text)          # off the page
                    continue
                lo, hi = 255, 0
                for row in range(r0, r1):
                    seg = buf[row * width + c0: row * width + c1]
                    lo, hi = min(lo, min(seg)), max(hi, max(seg))
                if hi - lo < MIN_INK_CONTRAST:
                    out.append(text)
    return out


def _is_scan_page(page: "fitz.Page", word_count: int) -> bool:
    """A page is a scan when it carries a large image and almost no text. A nearly empty page
    with no image ("This page intentionally left blank") is still a text page."""
    if word_count >= MIN_WORDS_FOR_TEXT_LAYER:
        return False
    area = page.rect.width * page.rect.height
    for img in page.get_images(full=True):
        for rect in page.get_image_rects(img[0]):
            if rect.width * rect.height >= 0.3 * area:
                return True
    return False


def load_document(path: Path) -> Document:
    pages = []
    with fitz.open(path) as pdf:
        for i, p in enumerate(pdf, start=1):
            words = [Word(w[4], w[0], w[1], w[2], w[3]) for w in p.get_text("words")]
            pages.append(Page(
                number=i,
                text=squash(p.get_text()),
                words=words,
                hidden_text=_hidden_spans(p),
                has_text_layer=not _is_scan_page(p, len(words)),
            ))
    return Document(path=path, pages=pages)


def render_pages(path: Path, out_dir: Path, dpi: int = 150, enhance: bool = False) -> list[Path]:
    """Writes page-<n>.png files. `enhance` gives the second read a different picture
    (grey, higher contrast) so the two reads of a scan are less alike."""
    out_dir.mkdir(parents=True, exist_ok=True)
    files = []
    with fitz.open(path) as pdf:
        for i, p in enumerate(pdf, start=1):
            pix = p.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY if enhance else fitz.csRGB)
            if enhance:
                pix.gamma_with(1.4)
            target = out_dir / f"page-{i}.png"
            pix.save(target)
            files.append(target)
    return files
