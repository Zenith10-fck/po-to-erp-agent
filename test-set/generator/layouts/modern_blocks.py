"""modern_blocks: coloured header band with the PO number inside it, stacked
bill-to / ship-to blocks, a zebra table without vertical rules."""
from __future__ import annotations

from ._common import (PAGE_H, PAGE_W, WHITE, Col, Ctx, TableStyle, block_lines, carrier_pairs,
                      draw_table, has, pairs, po_label, total_label)

M = 48
W = PAGE_W - 2 * M
TEAL = (0.05, 0.36, 0.40)
SOFT = (0.91, 0.95, 0.95)
MUTED = (0.40, 0.45, 0.47)

COLS = [
    Col("line_no", "#", 22),
    Col("description", "Description", 140, flex=True),
    Col("item_no", "Supplier Item", 66),
    Col("customer_part_no", "Our Item", 58),
    Col("requested_date", "Due", 54),
    Col("qty", "Quantity", 44, "r"),
    Col("uom", "Unit", 30),
    Col("unit_price", "Price", 46, "r"),
    Col("line_total", "Amount", 56, "r"),
]


def _band(ctx: Ctx) -> float:
    sp = ctx.spec
    b = sp.get("buyer") or {}
    h = 64
    ctx.rect(0, PAGE_H - h, PAGE_W, h, stroke=None, fill=TEAL)
    name = b.get("logo_text") if has(b.get("logo_text")) else b.get("name")
    if has(name):
        ctx.text(M, PAGE_H - 40, name, "Helvetica-Bold", 20, color=WHITE, width=250)
    ctx.text(PAGE_W - M, PAGE_H - 28, "Purchase Order", "Helvetica", 12, "r", WHITE)
    if has(sp.get("po_number")):
        ctx.text(PAGE_W - M, PAGE_H - 48, po_label(sp, "PO #") + " " + str(sp["po_number"]),
                 "Helvetica-Bold", 14, "r", WHITE, width=250)
    return PAGE_H - h - 22


def _block(ctx: Ctx, x, y, title, lines, width) -> float:
    if not lines:
        return y
    ctx.text(x, y, title, "Helvetica-Bold", 7, color=TEAL)
    y -= 12
    for i, ln in enumerate(lines):
        ctx.text(x, y, ln, "Helvetica-Bold" if i == 0 else "Helvetica", 9, width=width)
        y -= 11.5
    return y - 8


def _footer(ctx: Ctx):
    b = ctx.spec.get("buyer") or {}
    ctx.line(M, 46, PAGE_W - M, 46, 0.4, MUTED)
    if has(b.get("name")):
        ctx.text(M, 35, b["name"], "Helvetica", 7.5, color=MUTED)
    ctx.text(PAGE_W - M, 35, ctx.page_label(), "Helvetica", 7.5, "r", MUTED)


def draw(ctx: Ctx) -> None:
    sp = ctx.spec
    b = sp.get("buyer") or {}
    y0 = _band(ctx)
    colw = W / 3 - 12

    # column 1: from / supplier   column 2: bill to above ship to   column 3: order facts
    frm = block_lines(b) + ([str(b["contact"])] if has(b.get("contact")) else [])
    y1 = _block(ctx, M, y0, "FROM", frm, colw)
    y1 = _block(ctx, M, y1, "SUPPLIER", block_lines(sp.get("supplier")), colw)
    x2 = M + W / 3
    y2 = _block(ctx, x2, y0, "BILL TO", block_lines(sp.get("bill_to")), colw)
    y2 = _block(ctx, x2, y2, "SHIP TO", block_lines(sp.get("ship_to")), colw)
    x3 = M + 2 * W / 3
    facts = pairs(("Order date", sp.get("po_date")), ("Payment terms", sp.get("payment_terms")),
                  ("Currency", sp.get("currency")), *carrier_pairs(sp, "Carrier", "Carrier account"))
    y3 = y0
    if facts:
        fh = 12 + 25 * len(facts)
        ctx.rect(x3, y0 + 12 - fh, W / 3, fh, stroke=None, fill=SOFT)
        y3 = y0 - 2
        for lab, val in facts:
            ctx.text(x3 + 10, y3, lab, "Helvetica", 7, color=MUTED, width=W / 3 - 20)
            ctx.text(x3 + 10, y3 - 11, val, "Helvetica-Bold", 9.5, width=W / 3 - 20)
            y3 -= 25
        y3 -= 8
    y = min(y1, y2, y3) - 6

    def new_page():
        _footer(ctx)
        ctx.new_page()
        return _band(ctx) + 4, 62

    st = TableStyle(grid="zebra", head_h=20, head_color=TEAL, line_color=TEAL, zebra=SOFT,
                    pad_y=5, size=8.5)
    y = draw_table(ctx, COLS, sp.get("lines") or [], M, y, 62, st, new_page)

    notes = pairs(("DELIVERY NOTES", sp.get("shipping_notes")), ("NOTE", ctx.visible_note))
    if y - (60 + 32 * len(notes)) < 56:
        y, _ = new_page()
    y -= 14
    if has(sp.get("order_total")):
        ctx.rect(M + W - 200, y - 26, 200, 26, stroke=None, fill=TEAL)
        ctx.text(M + W - 190, y - 17, total_label(sp), "Helvetica", 10, color=WHITE, width=95)
        ctx.text(M + W - 10, y - 18, sp["order_total"], "Helvetica-Bold", 13, "r", WHITE, width=90)
    ny = y - 6
    for lab, val in notes:
        ctx.text(M, ny, lab, "Helvetica-Bold", 7, color=TEAL)
        ny = ctx.para(M, ny - 12, val, "Helvetica", 9, W - 230, 11.5) - 6
    _footer(ctx)
