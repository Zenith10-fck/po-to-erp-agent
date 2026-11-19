"""Evidence gate. Is every value the model returned really in the document?

Text PDF: the value must be in the text layer of the page the model named, as a whole token
(86.40 does not match inside 186.40). Line values must also sit on the same printed row as
that line's item number, so a real number from another row cannot be borrowed.

Scan: there is no text layer to check against. The document is read twice and the two reads
must agree on every value that matters (see `compare_reads`).
"""
from __future__ import annotations

import re

from ..document import Document, Page
from ..normalize import norm_address, norm_code, norm_name, norm_tokens, parse_date, parse_number, squash
from .base import Finding, val

ROW_TOLERANCE_PT = 10.0   # how far apart (vertically) two values of one order line may sit
_EDGE = "$,:;()[]@=*#\"'"

ORDER_CODE_FIELDS = ("po_number", "po_date", "order_total", "carrier_account_no", "currency")
ORDER_TEXT_FIELDS = ("customer_name", "bill_to_name", "bill_to_address", "ship_to_name",
                     "ship_to_address", "carrier_name", "shipping_notes")
LINE_ID_FIELDS = ("item_no", "customer_part_no")
LINE_BOUND_FIELDS = ("qty", "uom", "unit_price", "line_total")
LINE_OTHER_FIELDS = ("requested_date",)


def _strip(word: str) -> str:
    """Drop punctuation around a word. A trailing full stop is never part of a value."""
    return word.strip(_EDGE).rstrip(".").strip(_EDGE)


def in_text(page: Page, value: str) -> bool:
    """Whole-token search of a short value in the page text."""
    v = squash(value)
    if not v:
        return False
    if not any(ch.isalnum() for ch in v):
        return v in page.text          # a bare symbol such as "$" is often glued to a number
    pattern = r"(?<![A-Za-z0-9])" + r"\s*".join(re.escape(part) for part in v.split(" ")) + r"(?![A-Za-z0-9])"
    for m in re.finditer(pattern, page.text):
        # '5' must not match the '5' of '5.50' or of '1,5'
        before = page.text[m.start() - 1] if m.start() else " "
        after = page.text[m.end():m.end() + 2]
        if before in ".," and m.start() >= 2 and page.text[m.start() - 2].isdigit():
            continue
        if len(after) == 2 and after[0] in ".," and after[1].isdigit():
            continue
        return True
    return False


def tokens_in_text(page: Page, value: str) -> bool:
    """For names, addresses and notes: every word of the value is on the page."""
    have = set(norm_tokens(page.text))
    need = norm_tokens(value)
    return bool(need) and all(t in have for t in need)


def occurrences(page: Page, value: str) -> list[float]:
    """Vertical positions of every place the value is printed on the page."""
    parts = [_strip(p) for p in squash(value).split(" ")]
    parts = [p for p in parts if p]
    if not parts:
        return []
    words = [(_strip(w.text), w.yc) for w in page.words]
    words = [w for w in words if w[0]]
    hits = []
    for i in range(len(words) - len(parts) + 1):
        if all(words[i + k][0] == parts[k] for k in range(len(parts))):
            hits.append(words[i][1])
    if not hits and len(parts) == 1:
        # value glued to its neighbour in one word, like 'x12' or '5CS' or '@86.40'
        pat = re.compile(r"(?<![A-Za-z0-9.])" + re.escape(parts[0]) + r"(?![A-Za-z0-9])")
        hits = [y for w, y in words if pat.search(w)]
    return hits


def check_text_pdf(doc: Document, ex: dict) -> list[Finding]:
    findings: list[Finding] = []

    def miss(scope, name, f, note):
        findings.append(Finding("R08", scope, name, read=val(f), page=(f or {}).get("page"), note=note))

    def page_of(f) -> Page | None:
        return doc.page((f or {}).get("page"))

    for name in ORDER_CODE_FIELDS + ORDER_TEXT_FIELDS:
        f = ex.get(name)
        v = val(f)
        if v is None:
            continue
        page = page_of(f)
        if page is None:
            miss("order", name, f, "page number is missing or not in the document")
        elif name in ORDER_CODE_FIELDS and not in_text(page, v):
            miss("order", name, f, "value is not in the text of that page")
        elif name in ORDER_TEXT_FIELDS and not tokens_in_text(page, v):
            miss("order", name, f, "some words of the value are not on that page")

    lines = ex.get("lines") or []
    ignored = set(ex.get("ignored_pages") or [])

    # 1. Every place each line's item number is printed, as (page, y).
    candidates: list[list[tuple[int, float]]] = []
    for n, line in enumerate(lines, start=1):
        found: list[tuple[int, float]] = []
        for name in LINE_ID_FIELDS:
            f = line.get(name)
            v = val(f)
            if v is None:
                continue
            page = page_of(f)
            ys = occurrences(page, v) if page else []
            if not ys:
                miss(f"line {n}", name, f, "value is not in the text of that page")
            found += [(page.number, y) for y in ys]
        candidates.append(sorted(found))
        ids = [val(line.get(k)) for k in LINE_ID_FIELDS if val(line.get(k))]
        pages_with_item = {p.number for p in doc.pages for v in ids if occurrences(p, v)}
        if len(pages_with_item) > 1:
            # e.g. a second price table on a terms page: which table is the order is not proven
            findings.append(Finding("R08", f"line {n}", "item", read=val(line.get("item_no")) or val(line.get("customer_part_no")),
                                    note=f"item number is printed on more than one page ({', '.join(map(str, sorted(pages_with_item)))})"))

    # 2. One printed row per order line, one to one, in document order. The same item printed
    #    on two rows (a split delivery) can no longer lend one row's numbers to the other.
    anchors: list[tuple[int, float] | None] = []
    cursor = (0, float("-inf"))
    for n, found in enumerate(candidates, start=1):
        nxt = next((c for c in found if c[0] > cursor[0] or (c[0] == cursor[0] and c[1] > cursor[1] + 1)), None)
        if found and nxt is None:
            findings.append(Finding("R08", f"line {n}", "item", read=val(lines[n - 1].get("item_no")),
                                    note="no printed row of this item is left in document order"))
        anchors.append(nxt)
        if nxt:
            cursor = nxt

    # 3. Row tolerance shrinks when rows are printed close together.
    def tolerance(i: int) -> float:
        me = anchors[i]
        gaps = [abs(me[1] - o[1]) for j, o in enumerate(anchors)
                if j != i and o and o[0] == me[0] and abs(me[1] - o[1]) > 1]
        return min(ROW_TOLERANCE_PT, 0.45 * min(gaps)) if gaps else ROW_TOLERANCE_PT

    for i, line in enumerate(lines):
        scope = f"line {i + 1}"
        anchor = anchors[i]
        for name in LINE_BOUND_FIELDS + LINE_ID_FIELDS + LINE_OTHER_FIELDS:
            f = line.get(name)
            if val(f) is not None and (f or {}).get("page") in ignored:
                miss(scope, name, f, "value comes from a page the reading marked as cover or terms")
        for name in LINE_BOUND_FIELDS:
            f = line.get(name)
            v = val(f)
            if v is None:
                continue
            page = page_of(f)
            ys = occurrences(page, v) if page else []
            if not ys:
                miss(scope, name, f, "value is not in the text of that page")
            elif anchor and not (page.number == anchor[0] and any(abs(y - anchor[1]) <= tolerance(i) for y in ys)):
                miss(scope, name, f, "value is on the page but not on the same row as the item number")
        for name in LINE_OTHER_FIELDS:
            f = line.get(name)
            v = val(f)
            if v is None:
                continue
            page = page_of(f)
            if page is None or not in_text(page, v):
                miss(scope, name, f, "value is not in the text of that page")

    for name in ORDER_CODE_FIELDS + ORDER_TEXT_FIELDS:
        f = ex.get(name)
        if val(f) is not None and (f or {}).get("page") in ignored:
            miss("order", name, f, "value comes from a page the reading marked as cover or terms")
    return findings


# ---- scans: compare two independent reads ---------------------------------------------------

def _same(kind: str, a: str | None, b: str | None) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if kind == "number":
        return parse_number(a) is not None and parse_number(a) == parse_number(b)
    if kind == "date":
        return parse_date(a) is not None and parse_date(a) == parse_date(b)
    if kind == "code":
        return norm_code(a) == norm_code(b)
    if kind == "name":
        return norm_name(a) == norm_name(b)
    return norm_address(a) == norm_address(b)


ORDER_COMPARE = {
    "po_number": "code", "po_date": "date", "customer_name": "name", "ship_to_name": "name",
    "ship_to_address": "text", "order_total": "number", "carrier_account_no": "code",
    "shipping_notes": "text",
}
LINE_COMPARE = {
    "item_no": "code", "customer_part_no": "code", "qty": "number", "uom": "code",
    "unit_price": "number", "line_total": "number", "requested_date": "date",
}


def compare_reads(first: dict, second: dict) -> list[Finding]:
    """R09 for every value that the two reads do not agree on. The first read is the one used."""
    findings = []
    for name, kind in ORDER_COMPARE.items():
        a, b = val(first.get(name)), val(second.get(name))
        if not _same(kind, a, b):
            findings.append(Finding("R09", "order", name, read=a, expected=b,
                                    page=(first.get(name) or {}).get("page"), note="second read differs"))
    la, lb = first.get("lines") or [], second.get("lines") or []
    if len(la) != len(lb):
        findings.append(Finding("R09", "order", "lines", read=str(len(la)), expected=str(len(lb)),
                                note="the two reads found a different number of lines"))
        return findings
    for n, (x, y) in enumerate(zip(la, lb), start=1):
        for name, kind in LINE_COMPARE.items():
            a, b = val(x.get(name)), val(y.get(name))
            if not _same(kind, a, b):
                findings.append(Finding("R09", f"line {n}", name, read=a, expected=b,
                                        page=(x.get(name) or {}).get("page"), note="second read differs"))
    return findings


def check_required(ex: dict) -> list[Finding]:
    """R01 / R08 for required values that are missing (see docs/reason-codes.md)."""
    findings = []
    if val(ex.get("po_number")) is None:
        findings.append(Finding("R01", "order", "po_number", note="no PO number in the document"))
    codes = [("order", "po_number", ex.get("po_number")), ("order", "carrier_account_no", ex.get("carrier_account_no"))]
    for n, line in enumerate(ex.get("lines") or [], start=1):
        codes += [(f"line {n}", "item_no", line.get("item_no")), (f"line {n}", "customer_part_no", line.get("customer_part_no"))]
    for scope, name, f in codes:
        v = val(f)
        if v and not v.isascii():
            findings.append(Finding("R08", scope, name, read=v, page=(f or {}).get("page"),
                                    note="code contains non-Latin characters (possible look-alike letters)"))
    if val(ex.get("customer_name")) is None:
        findings.append(Finding("R08", "order", "customer_name", note="required value is missing"))
    if val(ex.get("ship_to_name")) is None and val(ex.get("ship_to_address")) is None:
        findings.append(Finding("R08", "order", "ship_to", note="required value is missing"))
    for n, line in enumerate(ex.get("lines") or [], start=1):
        for name in ("qty", "uom"):
            if val(line.get(name)) is None:
                findings.append(Finding("R08", f"line {n}", name, note="required value is missing"))
        if val(line.get("item_no")) is None and val(line.get("customer_part_no")) is None:
            findings.append(Finding("R08", f"line {n}", "item", note="no item number or customer part number"))
    return findings


def check_legibility(ex: dict) -> list[Finding]:
    if ex.get("legibility") != "clear":
        return [Finding("R11", "order", "legibility", read=str(ex.get("legibility")),
                        note="the model could not read every field with certainty")]
    return []
