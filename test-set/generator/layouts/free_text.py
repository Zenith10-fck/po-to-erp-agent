"""free_text: a typed order memo. No table at all: every line item is a sentence or a
loose list entry. The PO number sits in a "RE:" line. Courier, like a plain-text printout."""
from __future__ import annotations

from ._common import PAGE_H, PAGE_W, Ctx, Flow, block_lines, has, po_label, total_label

M = 54
W = PAGE_W - 2 * M
F, FB = "Courier", "Courier-Bold"
SIZE, LEAD = 10, 13


def _sentence(ln: dict, style: int) -> str:
    """One order line as text. The short values (item, qty, unit, price, total) come first,
    so they always sit on the first printed line; the description may wrap below.
    style 0: '5 CS of IT-10442 @ 86.40 = 432.00 - Hex bolt M8 x 40 zinc (our part HF-2291),
    need by 10/20/2026'
    style 1: 'IT-10442 / HF-2291, qty 5 CS, 86.40 each, total 432.00 - Hex bolt ..., deliver ...'"""
    g = lambda k: str(ln[k]) if has(ln.get(k)) else None
    qty = " ".join(v for v in (g("qty"), g("uom")) if v)
    if style == 0:
        parts = []
        if qty:
            parts.append(qty + " of")
        if g("item_no"):
            parts.append(g("item_no"))
        elif g("customer_part_no"):
            parts.append("our part " + g("customer_part_no"))
        if g("unit_price"):
            parts.append("@ " + g("unit_price"))
        if g("line_total"):
            parts.append("= " + g("line_total"))
        txt = " ".join(parts)
        if g("description"):
            txt += " - " + g("description")
        if g("item_no") and g("customer_part_no"):
            txt += " (our part " + g("customer_part_no") + ")"
        if g("requested_date"):
            txt += ", need by " + g("requested_date")
        return txt
    ids = " / ".join(v for v in (g("item_no"), g("customer_part_no")) if v)
    parts = [ids] if ids else []
    if qty:
        parts.append("qty " + qty)
    if g("unit_price"):
        parts.append(g("unit_price") + " each")
    if g("line_total"):
        parts.append("total " + g("line_total"))
    txt = ", ".join(parts)
    if g("description"):
        txt += " - " + g("description")
    if g("requested_date"):
        txt += ", deliver " + g("requested_date")
    return txt


def draw(ctx: Ctx) -> None:
    sp = ctx.spec
    b = sp.get("buyer") or {}
    style = int(sp.get("seed") or 0) % 2

    def footer():
        ctx.text(PAGE_W / 2, 36, "- " + ctx.page_label() + " -", F, 9, "c")

    def new_page():
        footer()
        ctx.new_page()
        y = PAGE_H - 60
        if has(sp.get("po_number")):
            ctx.text(M, y, po_label(sp, "Order Ref") + " " + str(sp["po_number"]) + " (continued)",
                     F, SIZE)
            y -= 2 * LEAD
        return y

    y = PAGE_H - 64
    if has(b.get("logo_text")):
        ctx.text(M, y, b["logo_text"], FB, 15)
        y -= 20
    fl = Flow(ctx, M, y, W, 60, F, SIZE, LEAD, new_page)
    for ln in block_lines(b):
        fl.p(ln, after=0)
    if has(b.get("contact")):
        fl.p(b["contact"], after=0)
    fl.space(LEAD)
    if has(sp.get("po_date")):
        fl.p("Date: " + str(sp["po_date"]), after=0)
    sup = block_lines(sp.get("supplier"))
    if sup:
        fl.p("TO:   " + ", ".join(sup), hang=36, after=0)
    if has(sp.get("po_number")):
        fl.p("RE:   " + po_label(sp, "Order Ref") + " " + str(sp["po_number"]), FB, after=0)
    fl.space(LEAD)
    ctx.line(M, fl.y + 8, M + W, fl.y + 8, 0.6)
    fl.space(6)

    lines = sp.get("lines") or []
    if lines:
        fl.p("Please enter our order for the following:" if style == 0
             else "We would like to order the items listed below.")
        for ln in lines:
            no = str(ln["line_no"]) if has(ln.get("line_no")) else "-"
            lead_txt = (no + ") ") if style == 0 else (no + ". ")
            fl.p(lead_txt + _sentence(ln, style), indent=12, hang=24, after=4)
        fl.space(6)

    if has(sp.get("order_total")):
        txt = total_label(sp, "Order total") + ": " + str(sp["order_total"])
        if has(sp.get("currency")):
            txt += " " + str(sp["currency"])
        fl.p(txt, FB)
    elif has(sp.get("currency")):
        fl.p("All prices in " + str(sp["currency"]) + ".")

    ship, bill = block_lines(sp.get("ship_to")), block_lines(sp.get("bill_to"))
    if ship:
        fl.p("Ship to: " + ", ".join(ship), hang=24, after=2)
    if bill:
        fl.p("Bill to: " + ", ".join(bill), hang=24, after=2)
    car = sp.get("carrier") or {}
    if has(car.get("name")):
        fl.p("Ship via: " + str(car["name"]), after=2)
    if has(car.get("account_no")):
        lab = str(car["label"]) if has(car.get("label")) else "Carrier account"
        fl.p(lab + ": " + str(car["account_no"]), after=2)
    if has(sp.get("shipping_notes")):
        fl.p("Delivery notes: " + str(sp["shipping_notes"]), hang=24, after=2)
    if has(sp.get("payment_terms")):
        fl.p("Terms: " + str(sp["payment_terms"]), after=2)
    if ctx.visible_note:
        fl.p("Note: " + ctx.visible_note, hang=24, after=2)
    fl.space(LEAD)
    fl.need(4 * LEAD)
    fl.p("Please confirm receipt of this order.", after=LEAD)
    fl.p("Thank you,", after=0)
    if has(b.get("name")):
        fl.p(b["name"], after=0)
    footer()
