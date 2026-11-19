"""Documents that are NOT purchase orders: invoice, quote request, newsletter. Simple but
realistic, so the "is it a PO?" step has real look-alikes to reject. They ignore `layout`."""
from __future__ import annotations

from ._common import (GREY, LIGHT, PAGE_H, PAGE_W, Col, Ctx, Flow, TableStyle, block_lines,
                      draw_table, has, pairs, po_label, total_label)

M = 50
W = PAGE_W - 2 * M
SLATE = (0.20, 0.24, 0.30)


def _head(ctx: Ctx, title: str, color) -> float:
    """Issuer on the left, document title on the right. Returns y under the head."""
    b = ctx.spec.get("buyer") or {}
    y = PAGE_H - 60
    if has(b.get("logo_text")):
        ctx.text(M, y, b["logo_text"], "Helvetica-Bold", 20, color=color, width=280)
        y -= 16
    for i, ln in enumerate(block_lines(b)):
        ctx.text(M, y, ln, "Helvetica-Bold" if i == 0 else "Helvetica", 9, width=280)
        y -= 11
    if has(b.get("contact")):
        ctx.text(M, y, b["contact"], "Helvetica", 8.5, width=280)
        y -= 11
    ctx.text(PAGE_W - M, PAGE_H - 62, title, "Helvetica-Bold", 20, "r", color)
    return y


def _facts(ctx: Ctx, rows, top) -> float:
    """Right-hand label/value list under the title."""
    y = top
    for lab, val in rows:
        ctx.text(PAGE_W - M - 120, y, lab, "Helvetica-Bold", 8.5, "r")
        ctx.text(PAGE_W - M, y, val, "Helvetica", 9.5, "r", width=110)
        y -= 13
    return y


def _footer(ctx: Ctx, text: str):
    ctx.line(M, 48, PAGE_W - M, 48, 0.4, GREY)
    ctx.text(M, 36, text, "Helvetica", 7.5, color=GREY)
    ctx.text(PAGE_W - M, 36, ctx.page_label(), "Helvetica", 7.5, "r", GREY)


def draw_invoice(ctx: Ctx) -> None:
    sp = ctx.spec
    color = (0.45, 0.12, 0.10)
    y = _head(ctx, "INVOICE", color)
    fy = _facts(ctx, pairs((po_label(sp, "Invoice No."), sp.get("po_number")),
                           ("Invoice Date", sp.get("po_date")), ("Terms", sp.get("payment_terms")),
                           ("Currency", sp.get("currency"))), PAGE_H - 84)
    y = min(y, fy) - 14
    bill = block_lines(sp.get("bill_to")) or block_lines(sp.get("supplier"))
    ship = block_lines(sp.get("ship_to"))
    yy = y
    for x, title, lines in ((M, "BILL TO", bill), (M + W / 2, "SHIPPED TO", ship)):
        if not lines:
            continue
        ctx.text(x, y, title, "Helvetica-Bold", 8, color=color)
        yy2 = y - 13
        for ln in lines:
            ctx.text(x, yy2, ln, "Helvetica", 9.5, width=W / 2 - 10)
            yy2 -= 12
        yy = min(yy, yy2)
    y = yy - 12

    cols = [Col("line_no", "#", 22), Col("item_no", "Item", 70),
            Col("description", "Description", 210, flex=True), Col("qty", "Qty", 40, "r"),
            Col("uom", "Unit", 34, "c"), Col("unit_price", "Unit Price", 64, "r"),
            Col("line_total", "Amount", 72, "r")]

    def new_page():
        _footer(ctx, "Thank you for your business.")
        ctx.new_page()
        return PAGE_H - 70, 70

    st = TableStyle(grid="rows", head_fill=LIGHT, head_h=18, line_color=GREY)
    y = draw_table(ctx, cols, sp.get("lines") or [], M, y, 70, st, new_page)
    if y < 150:
        y, _ = new_page()
    y -= 20
    if has(sp.get("order_total")):
        ctx.text(PAGE_W - M - 100, y, total_label(sp, "Amount Due"), "Helvetica-Bold", 11, "r")
        ctx.text(PAGE_W - M, y, sp["order_total"], "Helvetica-Bold", 11, "r", width=95)
        y -= 26
    ctx.para(M, y, "Please remit payment by the due date shown. Make checks payable to the company "
             "named above and write the invoice number on your remittance. Questions about this "
             "invoice: call the number above.", "Helvetica", 8.5, W - 40, 11)
    _footer(ctx, "Thank you for your business.")


def draw_quote_request(ctx: Ctx) -> None:
    sp = ctx.spec
    color = SLATE
    y = _head(ctx, "REQUEST FOR QUOTATION", color)
    fy = _facts(ctx, pairs((po_label(sp, "RFQ No."), sp.get("po_number")), ("Date", sp.get("po_date")),
                           ("Currency", sp.get("currency"))), PAGE_H - 84)
    y = min(y, fy) - 14
    sup = block_lines(sp.get("supplier"))
    if sup:
        ctx.text(M, y, "TO", "Helvetica-Bold", 8, color=color)
        y -= 13
        for ln in sup:
            ctx.text(M, y, ln, "Helvetica", 9.5)
            y -= 12
        y -= 8
    y = ctx.para(M, y, "This is not an order. Please quote your best price, lead time and minimum "
                 "order quantity for the items below. Do not ship against this request.",
                 "Helvetica-Bold", 9.5, W, 12.5) - 8

    cols = [Col("line_no", "Line", 30), Col("qty", "Est. Qty", 50, "r"), Col("uom", "Unit", 34, "c"),
            Col("item_no", "Your Item", 70), Col("customer_part_no", "Our Part", 66),
            Col("description", "Description", 142, flex=True),
            Col("requested_date", "Needed By", 60, "c"),
            Col("unit_price", "Target Price", 60, "r")]

    def new_page():
        _footer(ctx, "Request for quotation - not a purchase order.")
        ctx.new_page()
        return PAGE_H - 70, 80

    st = TableStyle(grid="full", head_fill=(0.90, 0.92, 0.95), head_h=18, line_color=SLATE,
                    min_row_h=0)
    y = draw_table(ctx, cols, sp.get("lines") or [], M, y, 80, st, new_page)
    if y < 170:
        y, _ = new_page()
    y -= 22
    ctx.text(M, y, "Your quotation", "Helvetica-Bold", 9.5)
    y -= 16
    for lab in ("Unit price and currency:", "Lead time (working days):", "Quote valid until:",
                "Quoted by (name and phone):"):
        ctx.text(M, y, lab, "Helvetica", 9)
        ctx.line(M + 150, y - 2, M + W, y - 2, 0.4, GREY)
        y -= 20
    notes = pairs(("Shipping", sp.get("shipping_notes")), ("Terms", sp.get("payment_terms")))
    for lab, val in notes:
        y = ctx.para(M, y - 4, lab + ": " + val, "Helvetica", 9, W, 11.5)
    _footer(ctx, "Request for quotation - not a purchase order.")


def draw_newsletter(ctx: Ctx) -> None:
    sp = ctx.spec
    b = sp.get("buyer") or {}
    ink = (0.05, 0.25, 0.45)
    ctx.rect(0, PAGE_H - 96, PAGE_W, 96, stroke=None, fill=ink)
    name = b.get("logo_text") if has(b.get("logo_text")) else b.get("name")
    if has(name):
        ctx.text(M, PAGE_H - 50, name, "Helvetica-Bold", 26, color=(1, 1, 1), width=W)
    if has(b.get("name")) and has(b.get("logo_text")):
        ctx.text(M, PAGE_H - 72, b["name"], "Helvetica", 10, color=(0.85, 0.90, 0.96))
    if has(sp.get("po_date")):
        ctx.text(PAGE_W - M, PAGE_H - 72, sp["po_date"], "Helvetica", 10, "r", (0.85, 0.90, 0.96))
    y = PAGE_H - 132
    if has(sp.get("title")):
        for ln in ctx.wrap(sp["title"], "Times-Bold", 22, W):
            ctx.text(M, y, ln, "Times-Bold", 22)
            y -= 26
        y -= 6
    ctx.line(M, y + 8, PAGE_W - M, y + 8, 0.6, GREY)
    y -= 14

    def new_page():
        _footer(ctx, "You receive this newsletter as a registered customer. Reply STOP to opt out.")
        ctx.new_page()
        return PAGE_H - 60

    fl = Flow(ctx, M, y, W, 70, "Times-Roman", 11, 14.5, new_page)
    for para in sp.get("body_paragraphs") or []:
        if has(para):
            fl.p(str(para), after=8)
    contact = b.get("contact")
    if has(contact):
        fl.space(6)
        fl.p("Questions? " + str(contact), "Times-Italic")
    _footer(ctx, "You receive this newsletter as a registered customer. Reply STOP to opt out.")


DRAW = {"invoice": draw_invoice, "quote_request": draw_quote_request, "newsletter": draw_newsletter}
