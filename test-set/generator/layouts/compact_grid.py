"""compact_grid: a dense system form, like a big ERP's PO print. Narrow margins, small
Helvetica, a black title bar, the PO number in the first cell of a grid of order facts,
ship-to and bill-to side by side, a fully ruled table with a black header."""
from __future__ import annotations

from reportlab.pdfbase.pdfmetrics import stringWidth

from ._common import (BLACK, PAGE_H, PAGE_W, WHITE, Col, Ctx, TableStyle, block_lines,
                      carrier_pairs, draw_table, has, pairs, po_label, total_label)

M = 30
W = PAGE_W - 2 * M
INK = (0.12, 0.12, 0.12)
LAB = (0.38, 0.38, 0.38)
TINT = (0.95, 0.95, 0.95)

COLS = [
    Col("line_no", "Ln", 20, "c"),
    Col("customer_part_no", "Part #", 60),
    Col("item_no", "Vendor Part", 62),
    Col("description", "Description", 170, flex=True),
    Col("qty", "Ord Qty", 38, "r"),
    Col("uom", "UOM", 26, "c"),
    Col("unit_price", "Unit Cost", 50, "r"),
    Col("line_total", "Ext Cost", 58, "r"),
    Col("requested_date", "Need Date", 68, "c"),
]


def _cell(ctx: Ctx, x, top, w, h, label, value_lines, size=8.5, fill=None):
    """One grid cell: tiny label top-left, value lines under it."""
    ctx.rect(x, top - h, w, h, stroke=INK, fill=fill, lw=0.5)
    ctx.text(x + 3, top - 7, label, "Helvetica", 5.8, color=LAB, width=w - 6)
    yy = top - 7 - size - 2
    for i, ln in enumerate(value_lines):
        ctx.text(x + 3, yy, ln, "Helvetica-Bold" if i == 0 and len(value_lines) > 1 else "Helvetica",
                 size, width=w - 6)
        yy -= size + 2


def _bar(ctx: Ctx) -> float:
    """Black title bar with the page counter. Returns y under it."""
    top = PAGE_H - 28
    ctx.rect(M, top - 20, W, 20, stroke=None, fill=BLACK)
    ctx.text(M + 8, top - 14, "PURCHASE ORDER", "Helvetica-Bold", 11.5, color=WHITE)
    ctx.text(M + W - 8, top - 13.5, ctx.page_label(), "Helvetica", 7.5, "r", WHITE)
    return top - 20


def _head(ctx: Ctx) -> float:
    sp = ctx.spec
    b = sp.get("buyer") or {}
    y = _bar(ctx) - 6
    # buyer on the left, supplier cell on the right
    yl = y - 14
    if has(b.get("logo_text")):
        ctx.text(M, yl, b["logo_text"], "Helvetica-Bold", 14, width=W / 2 - 10)
        yl -= 12
    for i, ln in enumerate(block_lines(b)):
        ctx.text(M, yl, ln, "Helvetica-Bold" if i == 0 else "Helvetica", 7.5, width=W / 2 - 10)
        yl -= 9
    if has(b.get("contact")):
        ctx.text(M, yl, b["contact"], "Helvetica", 7.5, width=W / 2 - 10)
        yl -= 9
    sup = block_lines(sp.get("supplier"))
    yr = y
    if sup:
        h = 12 + 10 * len(sup)
        _cell(ctx, M + W / 2, y, W / 2, h, "SUPPLIER", sup, size=8)
        yr = y - h
    y = min(yl + 3, yr) - 6

    # grid of order facts, PO number first
    facts = pairs((po_label(sp, "PO Number"), sp.get("po_number")), ("Order Date", sp.get("po_date")),
                  ("Currency", sp.get("currency")), ("Payment Terms", sp.get("payment_terms")),
                  *carrier_pairs(sp, "Ship Via", "Freight Account"))
    # cells sized by their content; a second row when they do not fit in one
    rows, row, used = [], [], 0.0
    for i, (lab, val) in enumerate(facts):
        need = max(stringWidth(val, "Helvetica", 9 if i == 0 else 8.5),
                   stringWidth(lab, "Helvetica", 5.8)) + 14
        need = max(need, 70.0)
        if row and used + need > W:
            rows.append(row)
            row, used = [], 0.0
        row.append((i, lab, val, need))
        used += need
    if row:
        rows.append(row)
    for row in rows:
        scale = W / sum(r[3] for r in row)
        x = M
        for i, lab, val, need in row:
            cw = need * scale
            _cell(ctx, x, y, cw, 22, lab, [val], size=9 if i == 0 else 8.5,
                  fill=TINT if i == 0 else None)
            x += cw
        y -= 22
    return y - 6 if rows else y


def draw(ctx: Ctx) -> None:
    sp = ctx.spec
    y = _head(ctx)

    ship, bill = block_lines(sp.get("ship_to")), block_lines(sp.get("bill_to"))
    cells = [(t, ln) for t, ln in (("SHIP TO", ship), ("BILL TO", bill)) if ln]
    if cells:
        h = 12 + 10 * max(len(c[1]) for c in cells)
        cw = W / 2
        for i, (title, lines) in enumerate(cells):
            _cell(ctx, M + i * cw, y, cw, h, title, lines, size=8)
        y -= h + 8

    def footer():
        ctx.line(M, 40, M + W, 40, 0.4, LAB)
        ctx.text(M, 32, "This order is subject to the purchase terms on file. Quote the PO number "
                 "on every packing list and invoice.", "Helvetica", 6.5, color=LAB)
        ctx.text(M + W, 32, ctx.page_label(), "Helvetica", 6.5, "r", LAB)

    def new_page():
        footer()
        ctx.new_page()
        return _head(ctx), 52

    st = TableStyle(size=7.6, head_size=6.8, leading=9.2, pad_x=3, pad_y=3, head_h=14,
                    head_fill=BLACK, head_color=WHITE, grid="full", line_color=INK, line_w=0.4)
    y = draw_table(ctx, COLS, sp.get("lines") or [], M, y, 52, st, new_page)

    notes = [v for v in (sp.get("shipping_notes"), ctx.visible_note) if has(v)]
    need = 34 + 10 * len(notes)
    if y - need < 50:
        y, _ = new_page()
    y -= 6
    total_w = 170
    if has(sp.get("order_total")):
        ctx.rect(M + W - total_w, y - 20, total_w, 20, stroke=INK, fill=TINT)
        ctx.text(M + W - total_w + 6, y - 13, total_label(sp, "Order Total"), "Helvetica-Bold", 8.5,
                 width=80)
        ctx.text(M + W - 6, y - 13.5, sp["order_total"], "Helvetica-Bold", 10, "r", width=80)
    if notes:
        nw = W - total_w - 8
        lines = []
        for v in notes:
            lines += ctx.wrap(v, "Helvetica", 7.8, nw - 8)
        h = 12 + 9.5 * len(lines)
        ctx.rect(M, y - h, nw, h, stroke=INK)
        ctx.text(M + 3, y - 7, "SPECIAL INSTRUCTIONS", "Helvetica", 5.8, color=LAB)
        yy = y - 16
        for ln in lines:
            ctx.text(M + 4, yy, ln, "Helvetica", 7.8)
            yy -= 9.5
    footer()
