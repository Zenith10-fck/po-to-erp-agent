"""classic_table: the textbook PO. Logo top-left, PO number in a box top-right,
three address boxes, an info strip and a fully ruled table. Helvetica."""
from __future__ import annotations

from reportlab.pdfbase.pdfmetrics import stringWidth

from ._common import (PAGE_H, PAGE_W, Col, Ctx, TableStyle, block_lines, carrier_pairs,
                      draw_table, has, labelled_box, pairs, po_label, total_label)

M = 42
W = PAGE_W - 2 * M
NAVY = (0.10, 0.18, 0.38)
HEAD = (0.86, 0.88, 0.92)

COLS = [
    Col("line_no", "Line", 28, "c"),
    Col("item_no", "Vendor Item", 66),
    Col("customer_part_no", "Our Part #", 62),
    Col("description", "Description", 144, flex=True),
    Col("qty", "Qty", 36, "r"),
    Col("uom", "U/M", 30, "c"),
    Col("unit_price", "Unit Price", 52, "r"),
    Col("line_total", "Extended", 56, "r"),
    Col("requested_date", "Req. Date", 54, "c"),
]


def _top(ctx: Ctx) -> float:
    """Logo, buyer block, title and the PO number box. Returns y under the header."""
    sp = ctx.spec
    b = sp.get("buyer") or {}
    y = PAGE_H - 62
    if has(b.get("logo_text")):
        ctx.text(M, y, b["logo_text"], "Helvetica-Bold", 24, color=NAVY, width=270)
        y -= 16
    if ctx.page_no == 1:
        for i, ln in enumerate(block_lines(b)):
            ctx.text(M, y, ln, "Helvetica-Bold" if i == 0 else "Helvetica", 9, width=280)
            y -= 11
        if has(b.get("contact")):
            ctx.text(M, y, b["contact"], "Helvetica", 8.5, width=280)
            y -= 11
    ctx.text(PAGE_W - M, PAGE_H - 60, "PURCHASE ORDER", "Helvetica-Bold", 18, "r", NAVY)
    rows = pairs((po_label(sp, "Purchase Order No."), sp.get("po_number")),
                 ("Date", sp.get("po_date")), ("Page", f"{ctx.page_no} of {ctx.total_pages}"))
    bw, lw, rh = 214, 108, 16
    bx, by = PAGE_W - M - bw, PAGE_H - 70
    for lab, val in rows:
        ctx.rect(bx, by - rh, lw, rh, fill=HEAD)
        ctx.rect(bx + lw, by - rh, bw - lw, rh)
        ctx.text(bx + 5, by - rh + 5, lab, "Helvetica-Bold", 8, width=lw - 10)
        ctx.text(bx + lw + 6, by - rh + 4.5, val, "Helvetica", 9.5, width=bw - lw - 12)
        by -= rh
    return min(y, by) - 10


def _footer(ctx: Ctx):
    ctx.text(PAGE_W / 2, 34, ctx.page_label(), "Helvetica", 8, "c")


def draw(ctx: Ctx) -> None:
    sp = ctx.spec
    y = _top(ctx)

    # three address boxes
    boxes = [(t, block_lines(p)) for t, p in (("VENDOR", sp.get("supplier")),
                                             ("BILL TO", sp.get("bill_to")),
                                             ("SHIP TO", sp.get("ship_to")))]
    boxes = [b for b in boxes if b[1]]
    if boxes:
        gap = 8
        bw = (W - gap * (len(boxes) - 1)) / len(boxes)
        h = 14 + 8 + 11.5 * max(len(b[1]) for b in boxes)
        for i, (title, lines) in enumerate(boxes):
            labelled_box(ctx, M + i * (bw + gap), y, bw, h, title, lines, title_fill=HEAD,
                         bold_first="Helvetica-Bold")
        y -= h + 10

    # info strip
    info = pairs(("Payment Terms", sp.get("payment_terms")),
                 *carrier_pairs(sp, "Ship Via", "Carrier Account"),
                 ("Currency", sp.get("currency")))
    if info:
        need = [max(stringWidth(lab, "Helvetica-Bold", 7.5), stringWidth(val, "Helvetica", 9)) + 16
                for lab, val in info]
        need = [max(n, 80.0) for n in need]
        widths = [n * W / sum(need) for n in need]
        x = M
        for (lab, val), cw in zip(info, widths):
            ctx.rect(x, y - 14, cw, 14, fill=HEAD)
            ctx.rect(x, y - 32, cw, 18)
            ctx.text(x + cw / 2, y - 10, lab, "Helvetica-Bold", 7.5, "c", width=cw - 8)
            ctx.text(x + cw / 2, y - 26, val, "Helvetica", 9, "c", width=cw - 8)
            x += cw
        y -= 32 + 12

    def new_page():
        _footer(ctx)
        ctx.new_page()
        return _top(ctx), 60

    st = TableStyle(head_fill=HEAD, grid="full", head_h=18)
    y = draw_table(ctx, COLS, sp.get("lines") or [], M, y, 60, st, new_page)

    notes = pairs(("Shipping Instructions:", sp.get("shipping_notes")), ("Note:", ctx.visible_note))
    need = 30 + 28 * len(notes) + 50
    if y - need < 50:
        y, _ = new_page()
    y -= 8
    if has(sp.get("order_total")):
        ctx.rect(M + W - 190, y - 20, 100, 20, fill=HEAD)
        ctx.rect(M + W - 90, y - 20, 90, 20)
        ctx.text(M + W - 185, y - 14, total_label(sp), "Helvetica-Bold", 9.5, width=90)
        ctx.text(M + W - 6, y - 14, sp["order_total"], "Helvetica-Bold", 10.5, "r", width=80)
    ny = y - 10
    for lab, val in notes:
        ctx.text(M, ny, lab, "Helvetica-Bold", 8.5)
        ny = ctx.para(M, ny - 11, val, "Helvetica", 9, W - 210, 11) - 4
    y = min(ny, y - 30) - 26
    ctx.line(M + W - 190, y, M + W, y)
    ctx.text(M + W - 190, y - 10, "Authorized Signature", "Helvetica", 7.5)
    _footer(ctx)
