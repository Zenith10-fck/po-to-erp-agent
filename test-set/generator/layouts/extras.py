"""Pages that are not the PO itself: the fax cover sheet (before the PO) and the terms and
conditions page (after it). Neither page carries any order line."""
from __future__ import annotations

from reportlab.pdfbase.pdfmetrics import stringWidth

from ._common import BLACK, GREY, PAGE_H, PAGE_W, Ctx, block_lines, has

M = 54


def draw_cover(ctx: Ctx, total_pages: int) -> None:
    """Fax-style cover sheet. `total_pages` counts every page of the file, cover included."""
    sp = ctx.spec
    b = sp.get("buyer") or {}
    s = sp.get("supplier") or {}
    W = PAGE_W - 2 * M
    y = PAGE_H - 80
    if has(b.get("logo_text")):
        ctx.text(M, y + 8, b["logo_text"], "Helvetica-Bold", 16)
        y -= 14
    for i, ln in enumerate(block_lines(b)):
        ctx.text(M, y, ln, "Helvetica-Bold" if i == 0 else "Helvetica", 9.5)
        y -= 12
    ctx.text(PAGE_W - M, PAGE_H - 92, "FAX", "Helvetica-Bold", 54, "r")
    y = min(y, PAGE_H - 110) - 18
    ctx.line(M, y, PAGE_W - M, y, 2.0)
    y -= 34

    rows = [("To:", s.get("name")), ("Attn:", "Order Desk"), ("Fax:", "555-0190"),
            ("From:", b.get("name")), ("Contact:", b.get("contact")),
            ("Date:", sp.get("po_date")), ("Pages:", f"{total_pages} (including this cover)"),
            ("Re:", "Purchase order")]
    for lab, val in rows:
        if not has(val):
            continue
        ctx.text(M, y, lab, "Helvetica-Bold", 12)
        ctx.text(M + 90, y, str(val), "Helvetica", 12, width=W - 100)
        ctx.line(M + 86, y - 4, PAGE_W - M, y - 4, 0.4, GREY)
        y -= 28

    y -= 10
    boxes = ["Urgent", "For Review", "Please Comment", "Please Reply"]
    x = M
    for i, lab in enumerate(boxes):
        ctx.rect(x, y - 2, 9, 9, lw=0.8)
        if i == 0:
            ctx.line(x + 1.5, y + 2.5, x + 4, y, 1.2)
            ctx.line(x + 4, y, x + 8, y + 6, 1.2)
        ctx.text(x + 14, y, lab, "Helvetica", 10.5)
        x += 118
    y -= 40
    ctx.text(M, y, "Comments:", "Helvetica-Bold", 11)
    y -= 20
    msg = ("Please find our purchase order on the following pages. Kindly confirm the order and "
           "the delivery dates by return fax or e-mail within two working days.")
    y = ctx.para(M, y, msg, "Helvetica", 11, W, 15)
    for _ in range(4):
        y -= 12
        ctx.line(M, y, PAGE_W - M, y, 0.4, GREY)

    ctx.text(M, 74, "CONFIDENTIALITY NOTICE", "Helvetica-Bold", 7.5)
    ctx.para(M, 64, "This fax may contain confidential information meant only for the person named "
             "above. If you received it by mistake, please call us right away and destroy all "
             "copies.", "Helvetica", 7.5, W, 9.5)


TERMS = [
    ("Acceptance", "This purchase order becomes a binding contract when Seller accepts it in "
     "writing, ships any part of the goods, or starts any work under it, whichever happens first. "
     "Any terms in Seller's quotation, acknowledgment or invoice that add to or differ from these "
     "terms are rejected unless Buyer agrees to them in a writing signed by an authorized "
     "purchasing agent."),
    ("Prices", "Prices are firm for the life of this order and include all charges for packing, "
     "boxing and cartage unless the face of the order states otherwise. Seller warrants that the "
     "prices are no higher than those charged to any other customer for similar quantities. Price "
     "increases notified after 03/31/2026 do not apply to open orders."),
    ("Delivery", "Time is of the essence. Goods must arrive on the date stated, not earlier than 5 "
     "working days before it and not later than the date itself. Buyer may return early deliveries "
     "at Seller's cost, or hold them and pay on the original schedule. Partial shipments need prior "
     "approval. If Seller expects any delay, Seller shall notify Buyer within 24 hours and state the "
     "cause and the new date."),
    ("Packing and Documents", "Every shipment must carry a packing list showing the purchase order "
     "number, line number, item number, quantity and unit of measure. Cartons may not exceed 50 lb "
     "(22.7 kg). Pallets must be 48 x 40 in, four-way entry, and stacked no higher than 60 in. "
     "Shipments without a packing list may be refused at the dock."),
    ("Inspection", "All goods are subject to inspection and test by Buyer within 30 days after "
     "receipt. Payment does not mean acceptance. Buyer may reject goods that do not conform and "
     "return them at Seller's risk and expense, including freight both ways, and may charge a "
     "handling fee of 15% of the value of the rejected goods."),
    ("Invoices and Payment", "Invoices must be sent to the bill-to address and must show the "
     "purchase order number. One invoice per shipment. The payment period starts on the later of "
     "the receipt of the goods and the receipt of a correct invoice, and cash discounts are "
     "calculated from the same date. Buyer may set off any amount owed by Seller against any "
     "amount payable under this order."),
    ("Taxes", "Unless the order says otherwise, prices include all federal, state and local taxes "
     "except sales and use taxes, which Seller shall show as a separate item on the invoice. Buyer "
     "will supply an exemption certificate where one applies."),
    ("Title and Risk", "Title and risk of loss pass to Buyer when the goods are delivered and "
     "accepted at the ship-to address, whatever the freight terms. Seller bears the risk of loss "
     "for goods rejected by Buyer from the time of rejection."),
    ("Warranty", "Seller warrants that the goods are new, of merchantable quality, free from "
     "defects in material and workmanship, fit for the purpose stated, and conform to all drawings "
     "and specifications, for 18 months from delivery or 12 months from first use, whichever ends "
     "first. This warranty survives inspection, acceptance and payment."),
    ("Changes", "Buyer may at any time change the quantities, the delivery dates or the place of "
     "delivery by written notice. If a change causes an increase or decrease in cost or time, a "
     "fair adjustment shall be made, provided Seller asserts its claim within 10 days of the "
     "notice."),
    ("Cancellation", "Buyer may cancel all or part of this order for convenience by written notice. "
     "Seller shall then stop work, and Buyer shall pay for finished goods delivered and for work in "
     "process at cost, not to exceed the order price. Buyer may cancel for default if Seller fails "
     "to deliver on time or breaches any term and does not cure within 10 days."),
    ("Tooling", "Tools, dies, patterns and fixtures paid for by Buyer are Buyer's property, must be "
     "marked as such, kept in good repair and insured by Seller, and returned within 15 days of a "
     "written request."),
    ("Compliance", "Seller shall comply with all applicable laws, including those on safety, labor, "
     "export control and hazardous materials. Safety data sheets must come with the first shipment "
     "of any regulated product and with every revision issued after 01/01/2026."),
    ("Insurance and Indemnity", "Seller shall keep general liability insurance of at least "
     "1,000,000 per occurrence and shall defend and hold Buyer harmless from all claims arising "
     "from the goods, from Seller's work on Buyer's premises, or from any infringement of a patent, "
     "trademark or copyright."),
    ("Confidentiality", "Drawings, specifications and prices supplied by Buyer remain Buyer's "
     "property, must be kept confidential, and must be returned on request. Seller may not name "
     "Buyer in any advertising without prior written consent."),
    ("Force Majeure", "Neither party is liable for delay caused by events beyond its reasonable "
     "control, such as fire, flood, strike or government action, provided it gives notice within "
     "5 days. If the delay lasts more than 45 days, Buyer may cancel the affected part of the order "
     "without liability."),
    ("Assignment and Waiver", "Seller may not assign this order or subcontract any substantial "
     "part of it without Buyer's written consent. A failure by Buyer to insist on any term is not "
     "a waiver of that term or of any other term."),
    ("Governing Law", "This order is governed by the laws of the state shown in Buyer's address, "
     "without regard to its conflict of law rules. Any dispute shall be heard in the state or "
     "federal courts for that county. These terms, revision 7, are effective from 02/15/2026 and "
     "replace all earlier versions."),
]


def terms_word_count() -> int:
    return sum(len((h + " " + t).split()) for h, t in TERMS)


def draw_terms(ctx: Ctx) -> None:
    """Dense two-column terms and conditions page. The font size shrinks until it fits."""
    sp = ctx.spec
    b = sp.get("buyer") or {}
    m = 40
    gap = 18
    colw = (PAGE_W - 2 * m - gap) / 2
    top = PAGE_H - 84
    bottom = 44
    title = "STANDARD TERMS AND CONDITIONS OF PURCHASE"
    ctx.text(PAGE_W / 2, PAGE_H - 50, title, "Times-Bold", 13, "c")
    if has(b.get("name")):
        ctx.text(PAGE_W / 2, PAGE_H - 64, str(b["name"]), "Times-Roman", 9.5, "c")
    ctx.line(m, PAGE_H - 72, PAGE_W - m, PAGE_H - 72, 0.6)

    size = 8.6
    while True:
        lead = size * 1.17
        items = []   # (font, text) per printed line, None for a paragraph gap
        for n, (head, body) in enumerate(TERMS, start=1):
            first = f"{n}. {head.upper()}."
            lines = ctx.wrap(first + " " + body, "Times-Roman", size, colw)
            for i, ln in enumerate(lines):
                items.append(("head" if i == 0 else "body", ln, first))
            items.append(None)
        per_col = int((top - bottom) / lead)
        if len(items) <= 2 * per_col or size < 5.5:
            break
        size -= 0.2

    # balance the two columns: break near the middle, at a paragraph gap
    half = (len(items) + 1) // 2
    x, y, col = m, top, 0
    for k, it in enumerate(items):
        if col == 0 and k >= half and items[k - 1] is None:
            col = 1
            x, y = m + colw + gap, top
        if y < bottom:
            col += 1
            x, y = m + col * (colw + gap), top
        if it is None:
            y -= lead * 0.35
            continue
        kind, ln, first = it
        if kind == "head" and ln.startswith(first):
            ctx.text(x, y, first, "Times-Bold", size)
            rest = ln[len(first):]
            ctx.text(x + stringWidth(first, "Times-Bold", size), y, rest, "Times-Roman", size)
        else:
            ctx.text(x, y, ln, "Times-Roman", size)
        y -= lead
    ctx.line(PAGE_W / 2, top + 8, PAGE_W / 2, bottom - 4, 0.3, GREY)
    ctx.text(PAGE_W / 2, 26, "Terms of Purchase, rev. 7, 02/15/2026", "Times-Italic", 7.5, "c", BLACK)
