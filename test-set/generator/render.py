"""Part B of the test-set generator: one render spec in, one PDF out.

    render_document(spec, out_pdf, fonts_dir)

See SPEC.md, section "Render spec". This module knows nothing about master data or the
answer key: it prints what the spec says, exactly as the spec says it.
"""
from __future__ import annotations

import importlib
import io
import sys
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from degrade import DEGRADATIONS, degrade_pdf  # noqa: E402
from layouts import extras, non_po  # noqa: E402
from layouts._common import GREY, PAGE_H, PAGE_W, WHITE, Ctx, has  # noqa: E402

LAYOUTS = ["classic_table", "modern_blocks", "free_text", "side_by_side", "compact_grid",
           "letter_style", "erp_export", "form_boxes"]
KINDS = ["po", "invoice", "quote_request", "newsletter"]
EXTRA_PAGES = ["cover", "terms"]
INJECTION_STYLES = ["visible_note", "small_footer", "white_text"]
HAND_FONT = "Kalam"
HAND_FILE = "Kalam-Regular.ttf"

__all__ = ["render_document", "LAYOUTS", "DEGRADATIONS"]


def _hand_font(fonts_dir: Path) -> str:
    if HAND_FONT not in pdfmetrics.getRegisteredFontNames():
        path = Path(fonts_dir) / HAND_FILE
        if not path.exists():
            raise FileNotFoundError(f"handwriting font not found: {path}")
        pdfmetrics.registerFont(TTFont(HAND_FONT, str(path)))
    return HAND_FONT


def _check(spec: dict) -> None:
    kind = spec.get("kind") or "po"
    if kind not in KINDS:
        raise ValueError(f"unknown kind: {kind}")
    if kind == "po" and not spec.get("handwritten") and spec.get("layout") not in LAYOUTS:
        raise ValueError(f"unknown layout: {spec.get('layout')}")
    for d in spec.get("degradations") or []:
        if d not in DEGRADATIONS:
            raise ValueError(f"unknown degradation: {d}")
    for e in spec.get("extra_pages") or []:
        if e not in EXTRA_PAGES:
            raise ValueError(f"unknown extra page: {e}")
    style = spec.get("injection_style")
    if has(spec.get("injection_text")) and style not in INJECTION_STYLES:
        raise ValueError(f"unknown injection style: {style}")


def _draw_fn(spec: dict):
    kind = spec.get("kind") or "po"
    if kind != "po":
        return non_po.DRAW[kind]
    layout = "form_boxes" if spec.get("handwritten") else spec["layout"]
    return importlib.import_module(f"layouts.{layout}").draw


def _white_text(ctx: Ctx, text: str) -> None:
    """Pure white text in an empty band low on page 1. Drawn BEFORE the page content, so
    anything printed later lies on top of it and nothing visible is covered."""
    lines = ctx.wrap(text, "Helvetica", 7, PAGE_W - 120)
    y = 140
    for ln in lines[:6]:
        ctx.text(60, y, ln, "Helvetica", 7, color=WHITE)
        y -= 8.5


def _small_footer(ctx: Ctx, text: str) -> None:
    """Tiny grey footer text under the normal footer of page 1."""
    lines = ctx.wrap(text, "Helvetica", 5, PAGE_W - 100)
    y = 22
    for ln in lines[:3]:
        ctx.text(50, y, ln, "Helvetica", 5, color=GREY)
        y -= 6


def _draw_main(c, spec: dict, total_pages: int, hand_font: str | None) -> int:
    """Draw the PO (or other document) pages. Returns how many pages it used."""
    ctx = Ctx(c, spec, total_pages, hand_font)
    inj = spec.get("injection_text") if has(spec.get("injection_text")) else None
    style = spec.get("injection_style")
    if inj and style == "white_text":
        _white_text(ctx, str(inj))
    if inj and style == "small_footer":
        def hook(cx: Ctx):
            if cx.page_no == 1:
                _small_footer(cx, str(inj))
        ctx.page_end_hook = hook
    _draw_fn(spec)(ctx)
    ctx.end_page()
    c.showPage()
    return ctx.page_no


def _canvas(buf) -> canvas.Canvas:
    c = canvas.Canvas(buf, pagesize=(PAGE_W, PAGE_H), invariant=1, pageCompression=1)
    c.setCreator("po-test-set generator")
    return c


def build_pdf_bytes(spec: dict, fonts_dir: Path) -> bytes:
    """The text PDF, before any degradation."""
    _check(spec)
    hand = _hand_font(fonts_dir) if spec.get("handwritten") else None
    extra = spec.get("extra_pages") or []

    # pass 1: count the pages of the main document, so "Page x of y" is right
    dry = _canvas(io.BytesIO())
    n_main = _draw_main(dry, spec, 1, hand)

    buf = io.BytesIO()
    c = _canvas(buf)
    total = n_main + ("cover" in extra) + ("terms" in extra)
    if "cover" in extra:
        extras.draw_cover(Ctx(c, spec, 1), total)
        c.showPage()
    _draw_main(c, spec, n_main, hand)
    if "terms" in extra:
        extras.draw_terms(Ctx(c, spec, 1))
        c.showPage()
    c.save()
    return buf.getvalue()


def render_document(spec: dict, out_pdf: Path, fonts_dir: Path) -> None:
    """Render one spec to `out_pdf`. Degradations (or handwriting) give an image-only PDF."""
    pdf = build_pdf_bytes(spec, fonts_dir)
    steps = list(spec.get("degradations") or [])
    if spec.get("handwritten") and "scan" not in steps:
        steps.insert(0, "scan")
    out_pdf = Path(out_pdf)
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    if steps:
        degrade_pdf(pdf, out_pdf, steps, int(spec.get("seed") or 0))
    else:
        out_pdf.write_bytes(pdf)
