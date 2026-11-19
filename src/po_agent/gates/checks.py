"""The small gates: math, duplicates, suspicious content."""
from __future__ import annotations

import csv
import re
from decimal import Decimal
from pathlib import Path

from ..document import Document
from ..normalize import norm_code, parse_number
from .base import Finding, val

LINE_TOLERANCE = Decimal("0.01")

# Text that talks to the reader or to a system instead of ordering goods.
_INJECTION = [
    r"\bignore\b.{0,40}\b(rules?|instructions?|validation|checks?|above|previous)\b",
    r"\b(system|developer)\s+(note|message|prompt|instruction)",
    r"\b(ai|llm)\s+(agent|assistant|model|system)\b",
    r"\b(language model|chatbot|assistant)\b.{0,40}\b(must|should|please|shall)\b",
    r"\b(skip|bypass|disable|override)\b.{0,30}\b(validation|review|checks?|rules?|approval|gates?)\b",
    r"\bdo not (flag|review|check|validate)\b",
    r"\b(approve|process)\b.{0,30}\bwithout\b.{0,20}\b(review|checks?|validation)\b",
    r"\bset\b.{0,25}\b(price|prices|total|quantity)\b.{0,15}\bto\b",
    r"\byou are (now|an?)\b",
]
_INJECTION_RE = [re.compile(p, re.IGNORECASE) for p in _INJECTION]


def _snippet(text: str, start: int, end: int, before: int = 30, after: int = 60) -> str:
    """The matched text with some context, cut at word boundaries."""
    a = max(0, start - before)
    if a > 0:
        space = text.find(" ", a, start)
        a = space + 1 if space != -1 else start
    b = min(len(text), end + after)
    if b < len(text):
        space = text.rfind(" ", end, b)
        b = space if space != -1 else b
    return text[a:b].strip()


def check_math(ex: dict) -> list[Finding]:
    """qty x unit price = line total, and the lines add up to the order total, when printed."""
    findings = []
    computed_sum = Decimal(0)
    can_sum = True
    lines = ex.get("lines") or []
    for n, line in enumerate(lines, start=1):
        qty = parse_number(val(line.get("qty")))
        price = parse_number(val(line.get("unit_price")))
        total = parse_number(val(line.get("line_total")))
        computed = (qty * price).quantize(Decimal("0.01")) if qty is not None and price is not None else None
        if total is not None and computed is not None and abs(total - computed) > LINE_TOLERANCE:
            findings.append(Finding("R07", f"line {n}", "line_total", read=val(line.get("line_total")),
                                    expected=str(computed), page=(line.get("line_total") or {}).get("page"),
                                    note="qty x unit price is not the printed line total"))
        best = computed if computed is not None else total
        if best is None:
            can_sum = False
        else:
            computed_sum += best
    order_total = parse_number(val(ex.get("order_total")))
    if order_total is not None and can_sum and lines:
        # line totals are already rounded to cents, so their sum is exact: one cent of slack
        if abs(order_total - computed_sum) > LINE_TOLERANCE:
            findings.append(Finding("R07", "order", "order_total", read=val(ex.get("order_total")),
                                    expected=str(computed_sum), page=(ex.get("order_total") or {}).get("page"),
                                    note="the lines do not add up to the printed order total"))
    return findings


def check_suspicious(doc: Document, ex: dict | None) -> list[Finding]:
    """R13 from three sources: the model's flag, a pattern scan of the text layer, and hidden
    (white or tiny) text. The code scan does not depend on the model being honest."""
    findings = []
    sc = (ex or {}).get("suspicious_content") or {}
    if sc.get("present"):
        findings.append(Finding("R13", "order", "suspicious_content", read=sc.get("quote"),
                                page=sc.get("page"), note="reported by the model"))
    for page in doc.pages:
        for rx in _INJECTION_RE:
            m = rx.search(page.text)
            if m:
                findings.append(Finding("R13", "order", "suspicious_content",
                                        read=_snippet(page.text, m.start(), m.end()), page=page.number,
                                        note="instruction-like text found by the code scan"))
                break
        if page.hidden_text:
            findings.append(Finding("R13", "order", "hidden_text", read=" ".join(page.hidden_text)[:200],
                                    page=page.number, note="white or tiny text in the document"))
    return findings


def check_email_text(subject: str, body: str) -> list[Finding]:
    """R13 when the email itself carries instruction-like text (the classifier reads it)."""
    text = f"{subject}\n{body}"
    for rx in _INJECTION_RE:
        m = rx.search(text)
        if m:
            return [Finding("R13", "order", "email_text", read=_snippet(text, m.start(), m.end()),
                            note="instruction-like text in the email, found by the code scan")]
    return []


_FORMULA_START = ("=", "+", "@", "\t", "\r")


def check_csv_cells(rows: list[dict]) -> list[Finding]:
    """R13 when a text cell would start a spreadsheet formula (CSV injection), for example a
    printed shipping note '=HYPERLINK(...)'. The order goes to review instead of being written."""
    findings = []
    for r in rows:
        for col, v in r.items():
            s = "" if v is None else str(v)
            if s.startswith(_FORMULA_START) or (s.startswith("-") and len(s) > 1 and not s[1].isdigit()):
                findings.append(Finding("R13", f"line {r.get('line_no')}", col, read=s[:80],
                                        note="value would start a spreadsheet formula"))
    return findings


class Ledger:
    """Customer + PO number of every order already handled (state/processed.csv)."""

    def __init__(self, path: Path):
        self.path = path
        self.seen: dict[tuple[str, str], str] = {}
        if path.exists():
            with path.open(encoding="utf-8", newline="") as f:
                for r in csv.DictReader(f):
                    self.seen[(r["customer_id"], norm_code(r["customer_po_number"]))] = r["doc_id"]

    def check(self, customer_id: str | None, po_number: str) -> list[Finding]:
        if not customer_id or not po_number:
            return []
        first = self.seen.get((customer_id, norm_code(po_number)))
        if first:
            return [Finding("R10", "order", "po_number", read=po_number,
                            note=f"this customer and PO number were already processed ({first})")]
        return []

    def add(self, customer_id: str | None, po_number: str, doc_id: str, result: str) -> None:
        if not customer_id or not po_number:
            return
        self.seen[(customer_id, norm_code(po_number))] = doc_id
        new = not self.path.exists()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["customer_id", "customer_po_number", "doc_id", "result"])
            w.writerow([customer_id, po_number, doc_id, result])
