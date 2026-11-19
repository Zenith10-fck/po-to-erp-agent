"""letter_style: a business letter. Centred letterhead, the PO number inside the first
sentence of the body, a small rule-less list of items inside the letter. Times."""
from __future__ import annotations

from ._common import (PAGE_H, PAGE_W, Col, Ctx, Flow, TableStyle, block_lines, draw_table, has,
                      po_label, total_label)

M = 64
W = PAGE_W - 2 * M
F, FB, FI = "Times-Roman", "Times-Bold", "Times-Italic"
SIZE, LEAD = 11, 14
RULE = (0.35, 0.10, 0.10)

COLS = [
    Col("line_no", "Item", 26),
    Col("qty", "Qty", 34, "r"),
    Col("uom", "Unit", 30, "c"),
    Col("item_no", "Your Item", 62),
    Col("customer_part_no", "Our Part", 58),
    Col("description", "Description", 118, flex=True),
    Col("requested_date", "Required", 56),
    Col("unit_price", "Price", 46, "r"),
    Col("line_total", "Total", 54, "r"),
]


def _letterhead(ctx: Ctx) -> float:
    b = ctx.spec.get("buyer") or {}
    y = PAGE_H - 58
    if ctx.page_no > 1:
        if has(b.get("name")):
            ctx.text(M, y, b["name"], FI, 9.5)
        ctx.text(PAGE_W - M, y, ctx.page_label(), FI, 9.5, "r")
        ctx.line(M, y - 5, PAGE_W - M, y - 5, 0.5, RULE)
        return y - 30
    if has(b.get("logo_text")):
        ctx.text(PAGE_W / 2, y, b["logo_text"], FB, 22, "c", RULE)
        y -= 16
    head = block_lines(b)
    if head:
        ctx.text(PAGE_W / 2, y, head[0], FB, 11, "c")
        y -= 12
        if head[1:]:
            ctx.text(PAGE_W / 2, y, ", ".join(head[1:]), F, 9.5, "c", width=W)
            y -= 8
    ctx.line(M, y, PAGE_W - M, y, 1.2, RULE)
    ctx.line(M, y - 2.5, PAGE_W - M, y - 2.5, 0.4, RULE)
    return y - 30


def draw(ctx: Ctx) -> None:
    sp = ctx.spec
    b = sp.get("buyer") or {}

    def footer():
        if ctx.total_pages > 1 and ctx.page_no == 1:
            ctx.text(PAGE_W - M, 40, ctx.page_label(), FI, 9.5, "r")

    def new_page():
        footer()
        ctx.new_page()
        return _letterhead(ctx)

    y = _letterhead(ctx)
    fl = Flow(ctx, M, y, W, 64, F, SIZE, LEAD, new_page)
    if has(sp.get("po_date")):
        fl.p(str(sp["po_date"]), align="r", after=LEAD * 0.6)
    for ln in block_lines(sp.get("supplier")):
        fl.p(ln, after=0)
    fl.p("Attention: Order Desk", after=LEAD)
    fl.p("Dear Sir or Madam,", after=LEAD * 0.6)

    intro = "Please accept this letter as our "
    if has(sp.get("po_number")):
        intro += po_label(sp, "Purchase Order No.") + " " + str(sp["po_number"])
    else:
        intro += "order"
    intro += " for the goods listed below. Kindly acknowledge receipt and confirm the delivery dates."
    fl.p(intro)

    lines = sp.get("lines") or []
    if lines:
        def table_page():
            return new_page(), 64

        st = TableStyle(font=F, bold=FB, size=10, head_size=10, leading=12, grid="head",
                        head_h=17, pad_x=3, pad_y=3, line_w=0.4, head_rule_w=0.5)
        fl.need(60)
        fl.y = draw_table(ctx, COLS, lines, M, fl.y + 6, 64, st, table_page)
        fl.space(16)
    if has(sp.get("order_total")):
        txt = total_label(sp, "Order total") + ": " + str(sp["order_total"])
        if has(sp.get("currency")):
            txt += " " + str(sp["currency"])
        fl.p(txt, FB, align="r")
    elif has(sp.get("currency")):
        fl.p("All prices are in " + str(sp["currency"]) + ".")

    ship, bill = block_lines(sp.get("ship_to")), block_lines(sp.get("bill_to"))
    if ship:
        fl.p("Please deliver the goods to " + ", ".join(ship) + ".")
    if bill:
        fl.p("Invoices should be addressed to " + ", ".join(bill) + ".")
    car = sp.get("carrier") or {}
    if has(car.get("name")):
        fl.p("Please ship via " + str(car["name"]) + ".", after=2)
    if has(car.get("account_no")):
        lab = str(car["label"]) if has(car.get("label")) else "Carrier account"
        fl.p(lab + ": " + str(car["account_no"]))
    elif has(car.get("name")):
        fl.space(LEAD * 0.5)
    if has(sp.get("shipping_notes")):
        fl.p("Delivery instructions: " + str(sp["shipping_notes"]))
    if has(sp.get("payment_terms")):
        fl.p("Our payment terms are " + str(sp["payment_terms"]) + ".")
    if ctx.visible_note:
        fl.p("Note: " + ctx.visible_note)

    fl.need(7 * LEAD)
    fl.space(LEAD * 0.5)
    fl.p("Yours sincerely,", after=LEAD * 2.6)
    if has(b.get("contact")):
        fl.p(b["contact"], after=0)
    if has(b.get("name")):
        fl.p(b["name"], after=0)
    footer()
