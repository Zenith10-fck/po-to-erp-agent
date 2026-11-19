"""Turns a text PDF into an image-only PDF that looks scanned, faxed, rotated or skewed.

Degraded, not destroyed: a careful human can still read every value. All randomness comes
from one numpy generator seeded from the spec seed, so the output is repeatable.
"""
from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pymupdf
from PIL import Image, ImageFilter

DEGRADATIONS = ["scan", "rotate90", "rotate180", "skew", "noise", "fax"]

WORK_DPI = 200      # first rasterisation; every step works on this or lower
SCAN_DPI = 150
FAX_DPI = 100


class _Page:
    """One page image (8-bit grey) plus its resolution and how it should be stored."""

    def __init__(self, img: Image.Image, dpi: int):
        self.img = img
        self.dpi = dpi
        self.bilevel = False
        self.bed: int | None = None   # scanner bed grey, set by skew

    def resample(self, dpi: int):
        if dpi >= self.dpi:
            return
        w, h = self.img.size
        self.img = self.img.resize((round(w * dpi / self.dpi), round(h * dpi / self.dpi)),
                                   Image.LANCZOS)
        self.dpi = dpi


def _arr(img: Image.Image) -> np.ndarray:
    return np.asarray(img, dtype=np.float32)


def _img(a: np.ndarray) -> Image.Image:
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "L")


def _rotate(img: Image.Image, angle: float, fill: int) -> Image.Image:
    return img.rotate(angle, resample=Image.BICUBIC, expand=False, fillcolor=fill)


# ---- steps ----------------------------------------------------------------------------------

def _scan(p: _Page, rng: np.random.Generator):
    """~150 dpi grey, off-white paper with a soft gradient, light noise, tiny skew."""
    p.resample(SCAN_DPI)
    a = _arr(p.img)
    h, w = a.shape
    paper = rng.uniform(238, 247)
    grad = np.linspace(0, rng.uniform(-6, 6), w, dtype=np.float32)[None, :]
    grad = grad + np.linspace(0, rng.uniform(-4, 4), h, dtype=np.float32)[:, None]
    ink = rng.uniform(18, 35)
    # map white -> paper and black -> ink, keep the anti-aliasing in between
    a = ink + (a / 255.0) * (paper - ink) + grad
    a += rng.normal(0, 3.5, a.shape).astype(np.float32)
    img = _img(a).filter(ImageFilter.GaussianBlur(0.35))
    angle = float(rng.uniform(-0.45, 0.45))
    p.img = _rotate(img, angle, int(paper))


def _rotate90(p: _Page, rng: np.random.Generator):
    p.img = p.img.transpose(Image.ROTATE_90 if rng.random() < 0.5 else Image.ROTATE_270)


def _rotate180(p: _Page, rng: np.random.Generator):
    p.img = p.img.transpose(Image.ROTATE_180)


def _skew(p: _Page, rng: np.random.Generator):
    """1-3 degrees, the page a bit smaller than the scanner bed so its edge shows."""
    w, h = p.img.size
    bed = int(rng.uniform(150, 185))
    scale = 0.955
    small = p.img.resize((round(w * scale), round(h * scale)), Image.LANCZOS)
    angle = float(rng.uniform(1.0, 3.0) * (1 if rng.random() < 0.5 else -1))
    sw, sh = small.size
    # paper with a thin grey border, on a darker bed, then rotated as one piece
    canvas = Image.new("L", (w, h), bed)
    ox = (w - sw) // 2 + int(rng.integers(-w // 80, w // 80 + 1))
    oy = (h - sh) // 2 + int(rng.integers(-h // 80, h // 80 + 1))
    shadow = Image.new("L", (sw + 6, sh + 6), max(bed - 45, 0))
    canvas.paste(shadow, (ox - 1, oy + 2))
    canvas.paste(small, (ox, oy))
    p.img = _rotate(canvas, angle, bed)
    p.bed = bed


def _noise(p: _Page, rng: np.random.Generator):
    """Heavier speckle, a slight blur and a few faint streaks (dirty scanner glass)."""
    a = _arr(p.img.filter(ImageFilter.GaussianBlur(0.7)))
    h, w = a.shape
    n = int(h * w * 0.0012)
    ys, xs = rng.integers(0, h, n), rng.integers(0, w, n)
    a[ys, xs] = rng.uniform(40, 140, n)
    # a few bigger dust specks (2x2)
    m = int(h * w * 0.00008)
    ys, xs = rng.integers(0, h - 2, m), rng.integers(0, w - 2, m)
    for dy in (0, 1):
        for dx in (0, 1):
            a[ys + dy, xs + dx] = np.minimum(a[ys + dy, xs + dx], 90)
    for _ in range(int(rng.integers(2, 5))):
        x = int(rng.integers(0, w - 3))
        a[:, x:x + int(rng.integers(1, 3))] -= rng.uniform(10, 24)
    if rng.random() < 0.6:
        y = int(rng.integers(0, h - 2))
        a[y:y + 2, :] -= rng.uniform(8, 16)
    a += rng.normal(0, 6, a.shape).astype(np.float32)
    p.img = _img(a)


def _fax(p: _Page, rng: np.random.Generator):
    """~100 dpi, 1-bit, a little dropout (light rows and missing specks)."""
    p.resample(FAX_DPI)
    a = _arr(p.img)
    h, w = a.shape
    a += rng.normal(0, 10, a.shape).astype(np.float32)
    # threshold is fairly high so thin strokes survive the 1-bit step
    limit = 175 if p.bed is None else min(175, p.bed - 30)
    bw = a < limit
    # dropout: a few rows lose part of their ink, a few white specks
    for _ in range(int(rng.integers(2, 5))):
        y = int(rng.integers(0, h))
        mask = rng.random(w) < 0.45
        bw[y, mask] = False
    n = int(h * w * 0.0006)
    bw[rng.integers(0, h, n), rng.integers(0, w, n)] = False
    n = int(h * w * 0.0002)
    bw[rng.integers(0, h, n), rng.integers(0, w, n)] = True
    p.img = Image.fromarray(np.where(bw, 0, 255).astype(np.uint8), "L")
    p.bilevel = True


STEPS = {"scan": _scan, "rotate90": _rotate90, "rotate180": _rotate180, "skew": _skew,
         "noise": _noise, "fax": _fax}


def degrade_pdf(pdf_bytes: bytes, out_pdf: Path, degradations: list[str], seed: int) -> None:
    """Rasterise every page, apply the steps in order, write an image-only PDF."""
    for d in degradations:
        if d not in STEPS:
            raise ValueError(f"unknown degradation: {d}")
    rng = np.random.default_rng(int(seed))
    src = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    out = pymupdf.open()
    for page in src:
        pix = page.get_pixmap(dpi=WORK_DPI, colorspace=pymupdf.csGRAY, alpha=False)
        img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
        p = _Page(img, WORK_DPI)
        for d in degradations:
            if p.bilevel and d in ("scan", "noise"):
                p.img = p.img.convert("L")
                p.bilevel = False
            STEPS[d](p, rng)
        if p.dpi > SCAN_DPI:
            p.resample(SCAN_DPI)   # rotate/skew only: still store a scan-like resolution
        buf = io.BytesIO()
        if p.bilevel:
            p.img.convert("1", dither=Image.NONE).save(buf, format="PNG", optimize=True)
        else:
            p.img.save(buf, format="JPEG", quality=82, optimize=True)
        w_pt = p.img.width * 72.0 / p.dpi
        h_pt = p.img.height * 72.0 / p.dpi
        new = out.new_page(width=w_pt, height=h_pt)
        new.insert_image(new.rect, stream=buf.getvalue())
    src.close()
    out_pdf = Path(out_pdf)
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    out.save(str(out_pdf), garbage=3, deflate=True, no_new_id=True)
    out.close()
