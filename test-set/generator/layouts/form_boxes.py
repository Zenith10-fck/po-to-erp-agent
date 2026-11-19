"""form_boxes: a pre-printed order form (form lines and labels in dark red) that was filled
in. Every value sits in its own labelled box; the item table has blank ruled rows down to
the totals. Values go through ctx.value(), so with handwritten=True they are drawn in the
handwriting font."""
from __future__ import annotations

from ._common import (PAGE_H, PAGE_W, Col, Ctx, TableStyle, block_lines, carrier_pairs,
                      draw_table, has, pairs, po_label, total_label)

M = 40
W = PAGE_W - 2 * M
RED = (0.55, 0.10, 0.12)
PINK = (0.98, 0.92, 0.92)
LF, LB = "Helvetica", "Helvetica-Bold"
VF = "Helvetica"

COLS = [
    Col("line_no", "LN", 22, "c"),
    Col("qty", "QTY", 38, "r"),
    Col("uom", "UNIT", 32, "c"),
    Col("item_no", "PART NO.", 66),
    Col("customer_part_no", "OUR NO.", 58),
    Col("description", "DESCRIPTION", 146, flex=True),
    Col("requested_date", "DATE REQ'D", 58, "c"),
    Col("unit_price", "UNIT PRICE", 50, "r"),
    Col("line_total", "AMOUNT", 62, "r"),
]


def _lead(ctx: Ctx) -> float:
    return 15.0 if ctx.hand_font else 11.5


def _box(ctx: Ctx, x, top, w, h, label, lines, size=9.5):
    """Labelled box; the label is pre-printed, the lines are filled-in values."""
    ctx.rect(x, top - h, w, h, stroke=RED, lw=0.7)
    ctx.text(x + 3, top - 7.5, label, LB, 6.2, color=RED)
    lead = _lead(ctx)
    yy = top - 9 - lead + (2 if ctx.hand_font else 1)
    for ln in lines:
        ctx.value(x + 8, yy, ln, VF, size, width=w - 14)
        yy -= lead


def _box_h(ctx: Ctx, n) -> float:
    return 14 + _lead(ctx) * max(n, 1)


def _top(ctx: Ctx) -> float:
    """Pre-printed form head: company, title, form number, PO number and date boxes."""
    sp = ctx.spec
    b = sp.get("buyer") or {}
    y = PAGE_H - 50
    x = M
    if has(b.get("logo_text")):
        ctx.text(x, y, b["logo_text"], "Times-Bold", 20, color=RED, width=250)
        y -= 14
    for i, ln in enumerate(block_lines(b)):
        ctx.text(x, y, ln, LB if i == 0 else LF, 8, color=RED, width=260)
        y -= 9.5
    ctx.text(PAGE_W - M, PAGE_H - 50, "PURCHASE ORDER", LB, 17, "r", RED)
    ctx.text(PAGE_W - M, PAGE_H - 62, "Form 2207-B   " + ctx.page_label(), LF, 7, "r", RED)
    # PO number and date boxes, top right
    bw = 118
    top = PAGE_H - 70
    h = _box_h(ctx, 1)
    bx = PAGE_W - M - 2 * bw
    if has(sp.get("po_number")):
        _box(ctx, bx, top, bw, h, po_label(sp, "P.O. NO."), [sp["po_number"]], 10.5)
    if has(sp.get("po_date")):
        _box(ctx, bx + bw, top, bw, h, "DATE", [sp["po_date"]], 10)
    return min(y, top - h) - 10


def draw(ctx: Ctx) -> None:
    sp = ctx.spec
    b = sp.get("buyer") or {}
    y = _top(ctx)
    half = W / 2

    # vendor + ship to, then bill to + shipping facts
    sup, ship = block_lines(sp.get("supplier")), block_lines(sp.get("ship_to"))
    if sup or ship:
        h = _box_h(ctx, max(len(sup), len(ship)))
        if sup:
            _box(ctx, M, y, half, h, "TO (VENDOR)", sup)
        if ship:
            _box(ctx, M + half, y, half, h, "SHIP TO", ship)
        y -= h
    bill = block_lines(sp.get("bill_to"))
    facts = pairs(*carrier_pairs(sp, "SHIP VIA", "ACCOUNT NO."), ("TERMS", sp.get("payment_terms")),
                  ("CURRENCY", sp.get("currency")))
    if bill or facts:
        h = max(_box_h(ctx, len(bill)) if bill else 0, _box_h(ctx, 1) * ((len(facts) + 1) // 2))
        if bill:
            _box(ctx, M, y, half, h, "BILL TO", bill)
        if facts:
            rows = (len(facts) + 1) // 2
            fh = h / rows
            for i, (lab, val) in enumerate(facts):
                fx = M + half + (i % 2) * half / 2
                fw = half / 2 if not (i == len(facts) - 1 and i % 2 == 0) else half
                _box(ctx, fx, y - (i // 2) * fh, fw, fh, lab, [val], 9.5)
        y -= h
    y -= 10

    # the instructions box grows with its text; the table stops above it
    tw = 180
    nw = W - tw - 8
    notes = [v for v in (sp.get("shipping_notes"), ctx.visible_note) if has(v)]
    note_lines = [part for v in notes for part in ctx.wrap(v, ctx.vfont(VF), ctx.vsize(9), nw - 16)]
    step = _lead(ctx) - 1
    nh = max(62.0, 14 + step * len(note_lines) + 6)
    bottom = nh + 88

    def footer():
        ctx.text(M, 30, "Original - Vendor", LF, 6.5, color=RED)
        ctx.text(PAGE_W - M, 30, "Please show our P.O. number on all invoices, packages and "
                 "correspondence.", LF, 6.5, "r", RED)

    def new_page():
        footer()
        ctx.new_page()
        return _top(ctx), bottom

    hand = bool(ctx.hand_font)
    st = TableStyle(font=VF, bold=LB, size=9 if not hand else 8.5, head_size=6.5, leading=11,
                    head_h=15, head_fill=PINK, head_color=RED, grid="full", line_color=RED,
                    line_w=0.5, min_row_h=24 if hand else 18, extend="rows", pad_y=4)
    y = draw_table(ctx, COLS, sp.get("lines") or [], M, y, bottom, st, new_page)

    # bottom block: instructions box on the left, total box on the right
    y -= 8
    if notes:
        _box(ctx, M, y, nw, nh, "SPECIAL INSTRUCTIONS", [])
    yy = y - 9 - _lead(ctx) + 2
    for part in note_lines:
        ctx.value(M + 8, yy, part, VF, 9, width=nw - 16)
        yy -= step
    th = _box_h(ctx, 1) + 2
    if has(sp.get("order_total")):
        ctx.rect(M + W - tw, y - th, tw, th, stroke=RED, fill=PINK, lw=0.9)
        ctx.text(M + W - tw + 4, y - 8, total_label(sp, "TOTAL"), LB, 6.8, color=RED, width=tw - 8)
        ctx.value(M + W - 8, y - th + 6, sp["order_total"], LB, 11, "r", width=tw - 50)
    # ordered by / signature
    sy = y - nh - 26
    if has(b.get("contact")):
        ctx.line(M, sy, M + half - 20, sy, 0.6, RED)
        ctx.text(M, sy - 8, "ORDERED BY", LB, 6.2, color=RED)
        ctx.value(M + 4, sy + 4, b["contact"], VF, 9, width=half - 30)
    ctx.line(M + half + 20, sy, M + W, sy, 0.6, RED)
    ctx.text(M + half + 20, sy - 8, "AUTHORIZED SIGNATURE", LB, 6.2, color=RED)
    footer()
