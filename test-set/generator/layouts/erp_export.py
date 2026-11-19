"""erp_export: a monospace system printout from an old ERP, on green-bar paper with tractor
feed holes. Courier throughout, dashed rules, labels in capitals, the PO number on the
second header line of every page."""
from __future__ import annotations

from reportlab.pdfbase.pdfmetrics import stringWidth

from ._common import (PAGE_H, PAGE_W, Col, Ctx, TableStyle, block_lines, carrier_pairs,
                      draw_table, has, pairs, po_label, total_label)

M = 46
W = PAGE_W - 2 * M
F, FB = "Courier", "Courier-Bold"
SIZE, LEAD = 8.5, 10.5
BAND = (0.88, 0.95, 0.88)
HOLE = (0.80, 0.80, 0.80)

COLS = [
    Col("line_no", "LN", 22, "r"),
    Col("customer_part_no", "ITEM NUMBER", 66),
    Col("item_no", "VENDOR ITEM", 66),
    Col("description", "DESCRIPTION", 130, flex=True),
    Col("qty", "QUANTITY", 50, "r"),
    Col("uom", "UM", 22),
    Col("unit_price", "UNIT COST", 54, "r"),
    Col("line_total", "EXTENDED", 54, "r"),
    Col("requested_date", "DUE DATE", 56, "r"),
]


def _holes(ctx: Ctx):
    """Tractor feed holes and the perforation line on both edges."""
    c = ctx.c
    c.setStrokeColorRGB(*HOLE)
    c.setLineWidth(0.6)
    y = PAGE_H - 18
    while y > 10:
        c.circle(14, y, 4.2, stroke=1, fill=0)
        c.circle(PAGE_W - 14, y, 4.2, stroke=1, fill=0)
        y -= 36
    ctx.line(28, 0, 28, PAGE_H, 0.4, HOLE, dash=[2, 2])
    ctx.line(PAGE_W - 28, 0, PAGE_W - 28, PAGE_H, 0.4, HOLE, dash=[2, 2])


def _dashes(ctx: Ctx, y, ch="-"):
    n = int(W / stringWidth(ch, F, SIZE))
    ctx.text(M, y, ch * n, F, SIZE)


def _head(ctx: Ctx) -> float:
    sp = ctx.spec
    b = sp.get("buyer") or {}
    _holes(ctx)
    y = PAGE_H - 46
    if has(b.get("name")):
        ctx.text(M, y, b["name"], FB, SIZE, width=W - 90)
    ctx.text(M + W, y, ctx.page_label(), F, SIZE, "r")
    y -= LEAD
    ctx.text(M, y, "PGM POR310", F, SIZE)
    ctx.text(M + stringWidth("PGM POR310    ", F, SIZE), y, "PURCHASE ORDER", FB, 10)
    if has(sp.get("po_number")):
        ctx.text(M + W, y, po_label(sp, "P.O. NUMBER") + ": " + str(sp["po_number"]), FB, 10, "r",
                 width=W - 190)
    y -= LEAD * 0.6
    _dashes(ctx, y - 3, "=")
    return y - LEAD - 6


def _addr(ctx: Ctx, x, y, label, lines, width) -> float:
    if not lines:
        return y
    ctx.text(x, y, label, FB, SIZE)
    lx = x + stringWidth("SHIP TO:  ", F, SIZE)
    for ln in lines:
        ctx.text(lx, y, ln, F, SIZE, width=width - (lx - x))
        y -= LEAD
    return y - LEAD * 0.4


def draw(ctx: Ctx) -> None:
    sp = ctx.spec
    b = sp.get("buyer") or {}
    y = _head(ctx)

    # buyer address and contact
    addr = [str(a) for a in (b.get("address_lines") or []) if has(a)]
    if has(b.get("contact")):
        addr.append(str(b["contact"]))
    for ln in addr:
        ctx.text(M, y, ln, F, SIZE)
        y -= LEAD
    if addr:
        y -= LEAD * 0.4

    half = W / 2
    vendor, ship = block_lines(sp.get("supplier")), block_lines(sp.get("ship_to"))
    room = half - 8 - stringWidth("SHIP TO:  ", F, SIZE)
    if vendor and ship and all(stringWidth(ln, F, SIZE) <= room for ln in vendor + ship):
        ya = _addr(ctx, M, y, "VENDOR:", vendor, half - 8)
        yb = _addr(ctx, M + half, y, "SHIP TO:", ship, half)
        y = min(ya, yb)
    else:   # long lines: stack the blocks instead of shrinking them
        y = _addr(ctx, M, y, "VENDOR:", vendor, W)
        y = _addr(ctx, M, y, "SHIP TO:", ship, W)
    y = _addr(ctx, M, y, "BILL TO:", block_lines(sp.get("bill_to")), half - 8)

    facts = pairs(("ORDER DATE", sp.get("po_date")), ("TERMS", sp.get("payment_terms")),
                  ("CURRENCY", sp.get("currency")), *carrier_pairs(sp, "SHIP VIA", "FRT ACCT"))
    row = ""
    rows = []
    for lab, val in facts:
        part = f"{lab}: {val}"
        if row and stringWidth(row + "   " + part, F, SIZE) > W:
            rows.append(row)
            row = part
        else:
            row = row + "   " + part if row else part
    if row:
        rows.append(row)
    for r in rows:
        ctx.text(M, y, r, F, SIZE)
        y -= LEAD
    y -= 4

    def footer():
        ctx.text(PAGE_W / 2, 30, "CONTINUED ON NEXT PAGE", F, SIZE, "c")

    def new_page():
        footer()
        ctx.new_page()
        return _head(ctx), 56

    st = TableStyle(font=F, bold=FB, size=SIZE, head_size=SIZE, leading=LEAD, pad_x=3,
                    pad_y=2.5, grid="dashes", bands=True, zebra=BAND)
    y = draw_table(ctx, COLS, sp.get("lines") or [], M, y, 56, st, new_page)

    notes = pairs(("SHIPPING INSTR", sp.get("shipping_notes")), ("NOTE", ctx.visible_note))
    if y - (LEAD * (4 + 2 * len(notes))) < 50:
        y, _ = new_page()
    y -= LEAD * 0.5
    if has(sp.get("order_total")):
        lab = total_label(sp, "ORDER TOTAL")
        if has(sp.get("currency")):
            lab += " (" + str(sp["currency"]) + ")"
        ctx.text(M + W - 72, y, lab + " ....", FB, SIZE, "r")
        ctx.text(M + W - 2, y, sp["order_total"], FB, SIZE, "r")
        y -= LEAD * 1.6
    for lab, val in notes:
        ctx.text(M, y, lab + ":", FB, SIZE)
        lx = M + stringWidth("SHIPPING INSTR: ", F, SIZE)
        for part in ctx.wrap(val, F, SIZE, W - (lx - M)):
            ctx.text(lx, y, part, F, SIZE)
            y -= LEAD
    y -= LEAD
    ctx.text(PAGE_W / 2, y, "*** END OF PURCHASE ORDER ***", F, SIZE, "c")
