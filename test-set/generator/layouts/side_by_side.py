"""side_by_side: buyer and supplier side by side, then "Invoice to" and "Deliver to" side by
side. Quantity comes first in the table. The order number is NOT at the top: it sits in a
reference box at the bottom of every page. Times with horizontal rules only."""
from __future__ import annotations

from ._common import (PAGE_H, PAGE_W, Col, Ctx, TableStyle, block_lines, carrier_pairs,
                      draw_table, has, pairs, po_label, total_label)

M = 50
W = PAGE_W - 2 * M
F, FB, FI = "Times-Roman", "Times-Bold", "Times-Italic"
GREEN = (0.12, 0.33, 0.20)
BOTTOM = 104   # the table stops here, above the reference box

COLS = [
    Col("qty", "Ordered", 44, "r"),
    Col("uom", "Unit", 32, "c"),
    Col("customer_part_no", "Our Ref", 62),
    Col("item_no", "Supplier Code", 68),
    Col("description", "Description", 122, flex=True),
    Col("requested_date", "Wanted", 56, "c"),
    Col("unit_price", "Each", 48, "r"),
    Col("line_total", "Value", 56, "r"),
    Col("line_no", "Ln", 24, "r"),
]


def _title(ctx: Ctx) -> float:
    b = ctx.spec.get("buyer") or {}
    y = PAGE_H - 56
    ctx.line(M, y + 16, PAGE_W - M, y + 16, 1.5, GREEN)
    if has(b.get("logo_text")):
        ctx.text(M, y - 4, b["logo_text"], FB, 20, color=GREEN, width=260)
    ctx.text(PAGE_W - M, y - 4, "PURCHASE ORDER", FB, 17, "r")
    ctx.line(M, y - 14, PAGE_W - M, y - 14, 0.5, GREEN)
    return y - 34


def _block(ctx: Ctx, x, y, title, lines, width) -> float:
    ctx.text(x, y, title, FB, 8.5, color=GREEN)
    y -= 13
    for i, ln in enumerate(lines):
        ctx.text(x, y, ln, FB if i == 0 else F, 10.5, width=width)
        y -= 13
    return y


def _reference(ctx: Ctx):
    """Bottom box with the order number, on every page."""
    sp = ctx.spec
    ctx.rect(M, 46, W, 40, stroke=GREEN, lw=0.8)
    if has(sp.get("po_number")):
        ctx.text(M + 10, 68, po_label(sp, "Our Order Number") + ": " + str(sp["po_number"]),
                 FB, 12.5, width=W - 120)
        ctx.text(M + 10, 54, "Please quote this number on all delivery notes, invoices and "
                 "correspondence.", FI, 8.5)
    else:
        ctx.text(M + 10, 62, "Please quote our order details on all delivery notes and invoices.",
                 FI, 9)
    ctx.text(M + W - 10, 68, ctx.page_label(), F, 9.5, "r")


def draw(ctx: Ctx) -> None:
    sp = ctx.spec
    b = sp.get("buyer") or {}
    y = _title(ctx)
    half = W / 2

    frm = block_lines(b) + ([str(b["contact"])] if has(b.get("contact")) else [])
    ya = _block(ctx, M, y, "ORDERED BY", frm, half - 16) if frm else y
    sup = block_lines(sp.get("supplier"))
    yb = _block(ctx, M + half + 12, y, "SUPPLIER", sup, half - 16) if sup else y
    ybot = min(ya, yb)
    if frm and sup:
        ctx.line(M + half, y + 8, M + half, ybot + 8, 0.4, GREEN)
    y = ybot - 8

    bill, ship = block_lines(sp.get("bill_to")), block_lines(sp.get("ship_to"))
    if bill or ship:
        h = 20 + 13 * max(len(bill), len(ship)) + 6
        boxes = [(t, ln) for t, ln in (("INVOICE TO", bill), ("DELIVER TO", ship)) if ln]
        for i, (title, lines) in enumerate(boxes):
            x = M + i * (half + 6)
            ctx.rect(x, y - h, half - 6, h, stroke=GREEN, lw=0.6)
            _block(ctx, x + 8, y - 13, title, lines, half - 24)
        y -= h + 14

    facts = pairs(("Order date", sp.get("po_date")), ("Terms", sp.get("payment_terms")),
                  ("Currency", sp.get("currency")), *carrier_pairs(sp, "Carrier", "Carrier account"))
    for i, (lab, val) in enumerate(facts):
        x = M + (i % 2) * (half + 6)
        ctx.text(x, y - 13 * (i // 2), lab + ": " + val, F, 10.5, width=half - 10)
    if facts:
        y -= 13 * ((len(facts) + 1) // 2) + 8

    def new_page():
        _reference(ctx)
        ctx.new_page()
        return _title(ctx) + 6, BOTTOM

    st = TableStyle(font=F, bold=FB, size=10, head_size=9.5, leading=12, grid="rows",
                    head_h=18, line_color=GREEN, pad_y=4)
    y = draw_table(ctx, COLS, sp.get("lines") or [], M, y, BOTTOM, st, new_page)

    notes = pairs(("Delivery instructions", sp.get("shipping_notes")), ("Note", ctx.visible_note))
    if y - (34 + 28 * len(notes)) < BOTTOM - 8:
        y, _ = new_page()
    y -= 18
    if has(sp.get("order_total")):
        ctx.text(M + W - 70, y, total_label(sp, "Order Value"), FB, 11, "r", width=160)
        ctx.text(M + W - 4, y, sp["order_total"], FB, 11, "r", width=60)
        ctx.line(M + W - 62, y - 4, M + W, y - 4, 0.5)
        ctx.line(M + W - 62, y - 6, M + W, y - 6, 0.5)
    for lab, val in notes:
        y = ctx.para(M, y, lab + ": " + val, F, 10, W - 250, 12.5) - 4
    _reference(ctx)
