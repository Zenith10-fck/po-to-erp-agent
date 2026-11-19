"""Builds `run-report.html`: one self-contained page with the run summary, the review queue and
the detail of every order (page image with evidence boxes, fields, audit trail, CSV row).

    python -m po_agent.report <run_dir> [--out file.html]

Reads only the run folder: audit.jsonl, run.json, optional score.json, docs/, pages/, erp_import/.
Page images are embedded as base64 JPEG, so the file works offline and makes no network request.
Every number on the page comes from those files. Nothing is computed that a run did not measure:
without score.json the page says "not scored".

Design spec: docs/ui-reference-v2.md ("Proof sheet"). Fonts: Instrument Sans and IBM Plex Mono
(SIL OFL 1.1, see assets/fonts/), embedded as base64 so the page stays one file.
"""
from __future__ import annotations

import argparse
import base64
import csv
import io
import json
import re
from pathlib import Path

import pymupdf as fitz

from .gates.base import REASONS

HARD_CODES = {"R07", "R08", "R09", "R13", "R14"}   # bad tint; every other code uses the warn tint
PAGE_WIDTH_PX = 1000
JPEG_QUALITY = 72
BOX_PAD_PT = 2.0
COST_NOTE = "subscription, not billed per call"

# (field, label, kind) kind: id = mono, num = right/tabular, text
HEADER_FIELDS = [
    ("po_number", "PO number", "id"), ("po_date", "PO date", "id"),
    ("customer_name", "Customer", "text"), ("bill_to_name", "Bill-to name", "text"),
    ("bill_to_address", "Bill-to address", "text"), ("ship_to_name", "Ship-to name", "text"),
    ("ship_to_address", "Ship-to address", "text"), ("currency", "Currency", "id"),
    ("order_total", "Order total", "num"), ("carrier_name", "Carrier", "text"),
    ("carrier_account_no", "Carrier account", "id"), ("shipping_notes", "Shipping notes", "text"),
]
LINE_CELLS = [("item", "Item"), ("description", "Description"), ("qty", "Qty"), ("uom", "UoM"),
              ("unit_price", "Unit price"), ("line_total", "Total"), ("requested_date", "Requested")]

# Words used in the finding sentences.
FIELD_WORDS = {
    "po_number": "PO number", "po_date": "PO date", "customer_name": "customer name",
    "bill_to_name": "bill-to name", "bill_to_address": "bill-to address", "ship_to": "ship-to",
    "ship_to_name": "ship-to name", "ship_to_address": "ship-to address", "currency": "currency",
    "order_total": "order total", "carrier_name": "carrier", "carrier_account_no": "carrier account",
    "shipping_notes": "shipping notes", "item": "item", "item_no": "item number",
    "customer_part_no": "customer part number", "description": "description", "qty": "qty",
    "uom": "unit", "unit_price": "unit price", "line_total": "line total",
    "requested_date": "requested date", "suspicious_content": "suspicious content",
    "hidden_text": "hidden text", "legibility": "legibility", "classify": "classify call",
    "extract": "extract call", "extract2": "second read", "lines": "line count",
    "completeness": "completeness",
}
# Order-level findings that do not belong to one printed field go to an "Order checks" row.
CHECK_ROW = {"suspicious_content": "suspicious", "hidden_text": "suspicious", "legibility": "legibility",
             "classify": "model", "extract": "model", "extract2": "model", "lines": "model",
             "completeness": "model"}
# Fields the scan path compares between the two reads (gates/evidence.py). Others are not checked.
SCAN_ORDER = {"po_number", "po_date", "customer_name", "ship_to_name", "ship_to_address", "order_total",
              "carrier_account_no", "shipping_notes"}
SCAN_LINE = {"item", "qty", "uom", "unit_price", "line_total", "requested_date"}
# Fields that are only fully proven when the master-data gate could match the customer.
NEEDS_CUSTOMER = {"ship_to_name", "ship_to_address", "currency", "carrier_account_no"}
NEEDS_ITEM = {"uom", "unit_price"}
# An address is printed under its name: look for it there first.
NEAR_FIELD = {"ship_to_address": "ship_to_name", "bill_to_address": "bill_to_name", "bill_to_name": "customer_name"}
# What the reviewer sees instead of a code: a 2-3 word label, an icon, one short action and a
# "Why?" line. Codes stay in the data and the audit file; the page never shows them.
# Thresholds quoted here are the fixed ones in docs/reason-codes.md.
REASON_UI = {  # code: (label, icon, action (max 8 words), why)
    "R01": ("PO number missing", "hash", "Find the PO number, or ask the customer.",
            "No PO number was found on the document."),
    "R02": ("Customer unclear", "user", "Pick the right customer account.",
            "The customer name matches no customer in the master data, or matches two."),
    "R03": ("Ship-to unclear", "pin", "Confirm the delivery address with the customer.",
            "The ship-to is not one of this customer's saved addresses, or it fits two."),
    "R04": ("Item unknown", "box", "Find the right item number.",
            "The item is not in the item master, is inactive, or fits two items."),
    "R05": ("Unit unknown", "ruler", "Confirm the unit and the pack size.",
            "The unit is unknown, or has no conversion to the item's base unit."),
    "R06": ("Price differs", "tag", "Confirm the price with the customer.",
            "The price is missing, or differs from the price list by more than 0.5 % (or 0.01 per unit)."),
    "R07": ("Total doesn't add up", "sum", "Find which printed number is wrong.",
            "Quantity x unit price is not the line total, or the lines do not add up to the order total."),
    "R08": ("Not found on PDF", "search", "Read this value on the PDF yourself.",
            "A required value is missing, or it is not in the PDF text where the model said it was."),
    "R09": ("Reads disagree", "split", "Check the page; pick the right value.",
            "This is a scan. Two separate reads gave different values for the same field."),
    "R10": ("Duplicate order", "copy", "Compare with the earlier order. Likely a resend.",
            "This customer already sent this PO number, and it was processed before."),
    "R11": ("Hard to read", "eye", "Ask for a clearer copy.",
            "The page is too unclear to trust the values read from it."),
    "R12": ("Carrier account", "truck", "Confirm the carrier account with the customer.",
            "The carrier account is not on file for this customer, or two are given."),
    "R13": ("Suspicious text", "shield", "Don't follow it. Confirm the order by phone.",
            "The document has text that tries to give instructions to the software."),
    "R14": ("Couldn't read", "filex", "Enter this order by hand.",
            "The reading step failed (time-out, refusal or broken output), so nothing could be checked."),
}


# How the order view compares "read" with "expected" for a code: (left label, right label, difference).
REASON_COMPARE = {"R05": ("On PDF", "Known unit", None), "R06": ("On PDF", "Price list", "pct"),
                  "R07": ("Printed", "Calculated", "abs"), "R09": ("First read", "Second read", None)}
REASON_QUOTE = {"R13"}   # show the text itself, quoted, instead of a comparison


def reason_label(code: str) -> str:
    return REASON_UI[code][0] if code in REASON_UI else "Problem"


FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
FONTS = [  # (family, weight range, file) - SIL OFL 1.1, licence text next to the file
    ("Hanken Grotesk", "100 900", "hanken-grotesk-latin-wght-normal.woff2"),
]
GATES = [  # (name, codes) in pipeline order, from docs/reason-codes.md "Raised by"
    ("evidence", {"R01", "R08", "R09", "R11"}), ("math", {"R07"}),
    ("master data", {"R02", "R03", "R04", "R05", "R06", "R12"}), ("duplicate", {"R10"}),
    ("suspicious content", {"R13"}),
]


# ---- small helpers --------------------------------------------------------------------------

def _val(f) -> str | None:
    if not isinstance(f, dict) or f.get("value") is None:
        return None
    v = str(f["value"]).strip()
    return v or None


def _num(text: str | None) -> float | None:
    if text is None:
        return None
    t = re.sub(r"[^0-9.\-]", "", str(text).replace(",", ""))
    try:
        return float(t)
    except ValueError:
        return None


def _money(x: float | None) -> str | None:
    return None if x is None else f"{x:,.2f}"


def _secs(s: float) -> str:
    s = float(s or 0)
    if s < 60:
        return f"{s:.1f} s"
    m, r = divmod(int(round(s)), 60)
    return f"{m}m {r:02d}s"


def _line_no(scope: str) -> int | None:
    m = re.fullmatch(r"line (\d+)", scope or "")
    return int(m.group(1)) if m else None


def tone(code: str) -> str:
    return "bad" if code in HARD_CODES else "warn"


def finding_sentence(f: dict) -> str:
    """One sentence with the real values, e.g.
    'R06 Line 1 unit price 82.08 differs from the list price per CS 86.4000.'"""
    code, field = f.get("code", ""), f.get("field", "")
    read, exp, note = f.get("read"), f.get("expected"), (f.get("note") or "").strip()
    word = FIELD_WORDS.get(field, field.replace("_", " "))
    n = _line_no(f.get("scope", ""))
    subject = f"Line {n} {word}" if n else word[:1].upper() + word[1:]
    if code == "R06" and read and exp:
        s = f"{subject} {read} {note} {exp}"
    elif code == "R07" and field == "line_total" and exp:
        s = f"{subject} {read} is not qty x unit price ({exp})"
    elif code == "R07" and field == "order_total" and exp:
        s = f"{subject} {read} is not the sum of the lines ({exp})"
    elif code == "R09" and field == "lines":
        s = f"Line count: first read {read} lines, second read {exp} lines"
    elif code == "R09":
        s = f"{subject}: first read {read or 'empty'}, second read {exp or 'empty'}"
    elif code == "R13":
        where = f" on page {f['page']}" if f.get("page") else ""
        s = f"{subject}{where}: \u201c{read}\u201d ({note})" if read else f"{subject}{where}: {note}"
    else:
        s = subject + (f" {read}" if read else "") + (f": {note}" if note else "")
        if exp:
            s += f" (expected {exp})"
    s = f"{code} {s}"
    return s if s.endswith((".", "?")) else s + "."


def _targets(f: dict) -> list[str]:
    """Keys of the field rows a finding refers to."""
    field = f.get("field", "")
    n = _line_no(f.get("scope", ""))
    if n:
        cell = "item" if field in ("item", "item_no", "customer_part_no") else field
        return [f"l{n}", f"l{n}:{cell}"]
    if field in CHECK_ROW:
        return [f"c:{CHECK_ROW[field]}"]
    if field == "ship_to":
        return ["h:ship_to_name", "h:ship_to_address"]
    return [f"h:{field}"]


# ---- evidence boxes -------------------------------------------------------------------------

_EDGE = "$,:;()[]@=*#\"'\u201c\u201d"


def _tok(word: str) -> str:
    return word.strip(_EDGE).rstrip(".").strip(_EDGE).casefold()


class _PageText:
    def __init__(self, page):
        self.page = page
        self.w, self.h = page.rect.width, page.rect.height
        self.words = page.get_text("words")
        self.toks = [_tok(w[4]) for w in self.words]

    def hits(self, value: str | None) -> list[list[tuple]]:
        """Every place the value is printed: a list of rectangles per hit (one per text line)."""
        parts = [_tok(p) for p in (value or "").split()]
        parts = [p for p in parts if p]
        if not parts:
            return []
        out = []
        n = len(parts)
        for i in range(len(self.toks) - n + 1):
            if self.toks[i] == parts[0] and all(self.toks[i + k] == parts[k] for k in range(n)):
                lines: dict[tuple, list] = {}
                for w in self.words[i:i + n]:
                    lines.setdefault((w[5], w[6]), []).append(w)
                out.append([(min(w[0] for w in ws), min(w[1] for w in ws), max(w[2] for w in ws),
                             max(w[3] for w in ws)) for ws in lines.values()])
        if not out:
            out = [[(r.x0, r.y0, r.x1, r.y1)] for r in self.page.search_for(value)]
        return out


def _centre(hit) -> tuple[float, float]:
    r = hit[0]
    return (r[0] + r[2]) / 2, (r[1] + r[3]) / 2


def _closest(hits, point):
    if not hits:
        return None
    if point is None:
        return hits[0]
    return min(hits, key=lambda h: (abs(_centre(h)[1] - point[1]) * 4 + abs(_centre(h)[0] - point[0])))


class _Boxes:
    """Finds evidence boxes on a text PDF with PyMuPDF. Returns fractions of the page size."""

    def __init__(self, pdf_path: Path | None, enabled: bool):
        self.pages: list[_PageText] = []
        self.used: set[tuple] = set()      # one printed value gives evidence to one field only
        self._doc = None
        if enabled and pdf_path and pdf_path.exists():
            self._doc = fitz.open(pdf_path)
            self.pages = [_PageText(p) for p in self._doc]

    def close(self):
        if self._doc is not None:
            self._doc.close()

    def page(self, n) -> _PageText | None:
        if not isinstance(n, int) or n < 1 or n > len(self.pages):
            return None
        return self.pages[n - 1]

    def anchor(self, f: dict | None, fallback=None):
        """Centre of the quote of a field, used to pick the right hit of a short value."""
        pt = self.page((f or {}).get("page"))
        if not pt:
            return fallback
        q = (f or {}).get("quote")
        hit = pt.hits(q)[0] if q and pt.hits(q) else None
        return _centre(hit) if hit else fallback

    def find(self, f: dict | None, value: str | None, near=None, row_y=None):
        pt = self.page((f or {}).get("page"))
        if not pt or not value:
            return None, None
        hits = pt.hits(value)
        if not hits:
            return None, None
        page_no = f["page"]
        free = [h for h in hits if (page_no, tuple(round(v, 1) for v in h[0])) not in self.used] or hits
        if row_y is not None:
            hit = min(free, key=lambda h: abs(_centre(h)[1] - row_y))
        else:
            hit = _closest(free, near)
        self.used.add((page_no, tuple(round(v, 1) for v in hit[0])))
        rects = [{"p": f["page"],
                  "x": round(max(0.0, r[0] - BOX_PAD_PT) / pt.w, 5),
                  "y": round(max(0.0, r[1] - BOX_PAD_PT) / pt.h, 5),
                  "w": round((r[2] - r[0] + 2 * BOX_PAD_PT) / pt.w, 5),
                  "h": round((r[3] - r[1] + 2 * BOX_PAD_PT) / pt.h, 5)} for r in hit]
        return rects, _centre(hit)


# ---- page images ----------------------------------------------------------------------------

def _page_images(run_dir: Path, rec: dict) -> list[dict]:
    """Each page as a base64 JPEG about 1000px wide."""
    out = []
    pdf = run_dir / "docs" / rec["doc_id"] / (rec.get("source_file") or "")
    if rec.get("source_file") and pdf.is_file():
        with fitz.open(pdf) as doc:
            for p in doc:
                zoom = PAGE_WIDTH_PX / p.rect.width
                pix = p.get_pixmap(matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csRGB, alpha=False)
                out.append(_jpeg(pix))
        return out
    for png in sorted((run_dir / "pages" / rec["doc_id"]).glob("page-*.png"),
                      key=lambda p: int(re.sub(r"\D", "", p.stem) or 0)):
        pix = fitz.Pixmap(str(png))
        if pix.alpha:
            pix = fitz.Pixmap(pix, 0)
        out.append(_jpeg(pix))
    return out


def _jpeg(pix) -> dict:
    data = pix.tobytes("jpg", jpg_quality=JPEG_QUALITY)
    return {"src": "data:image/jpeg;base64," + base64.b64encode(data).decode("ascii"),
            "w": pix.width, "h": pix.height}


# ---- one order ------------------------------------------------------------------------------

def _cost(calls: list[dict]) -> float | None:
    costs = [c.get("cost_usd") for c in calls if c.get("cost_usd") is not None]
    return round(sum(costs), 4) if costs else None


def _call_sentence(c: dict, rec: dict) -> str:
    kind = {"classify": "Classify call", "extract": "Extract call", "extract2": "Second read"}.get(
        c.get("kind"), str(c.get("kind")))
    cost = f"${c['cost_usd']:.4f} API-equivalent" if c.get("cost_usd") is not None else "cost not reported"
    model = ", ".join(c.get("model") or []) or "model not reported"
    tail = f"{_secs(c.get('seconds', 0))}, {cost}, model {model}."
    if not c.get("ok"):
        return f"{kind} failed: {c.get('error') or 'no error text'}. {tail}"
    if c.get("kind") == "classify":
        cls = rec.get("classify") or {}
        return f"{kind}: {cls.get('doc_type', 'unknown')}, \u201c{cls.get('reason', '')}\u201d {tail}"
    ex = rec.get("extraction") or {}
    lines = len(ex.get("lines") or [])
    if c.get("kind") == "extract2":
        return f"{kind} of the scan, made from a different page image, to compare with the first read. {tail}"
    return f"{kind}: header values and {lines} order line{'s' if lines != 1 else ''} returned. {tail}"


def build_order(run_dir: Path, rec: dict, index: int) -> dict:
    ex = rec.get("extraction") or None
    matched = rec.get("matched") or {}
    findings = rec.get("findings") or []
    mode = rec.get("mode")
    route = rec.get("route")
    codes = rec.get("reason_codes") or []

    fails: dict[str, list[str]] = {}
    fview = []
    for f in findings:
        sent = finding_sentence(f)
        keys = _targets(f)
        for k in keys:
            fails.setdefault(k, []).append(f"{reason_label(f.get('code', ''))}: " + sent.split(" ", 1)[-1])
        n = _line_no(f.get("scope", ""))
        fview.append({"code": f.get("code"), "name": REASONS.get(f.get("code"), ""), "tone": tone(f.get("code", "")),
                      "sentence": sent, "target": keys[0], "targets": keys, "page": f.get("page"),
                      "read": f.get("read"), "expected": f.get("expected"),
                      "where": f"Line {n}" if n else ("Whole order" if f.get("field") in CHECK_ROW else "Header"),
                      "subject": FIELD_WORDS.get(f.get("field", ""), f.get("field", "").replace("_", " ")),
                      "plain": sent[len(f.get("code", "")) + 1:] if sent.startswith(f.get("code", "") + " ") else sent,
                      "note": (f.get("note") or "").strip(), "label": reason_label(f.get("code", "")),
                      "icon": REASON_UI.get(f.get("code"), ("", "filex"))[1]})

    has_r14 = any(f.get("code") == "R14" for f in findings)
    customer_ok = bool(matched.get("customer_id"))
    boxes_on = mode == "text" and ex is not None
    bx = _Boxes(run_dir / "docs" / rec["doc_id"] / (rec.get("source_file") or ""), boxes_on)
    boxes: list[dict] = []
    counts = {"proven": 0, "failed": 0, "not_checked": 0}

    def result(key: str, name: str, value, line_item_ok=True) -> str:
        if key in fails:
            r = "failed"
        elif value is None or has_r14 or name == "description":
            r = "not_checked"
        elif mode == "scan" and name == "suspicious":
            r = "not_checked"      # no text layer: only the model's own flag was looked at
        elif mode == "scan" and name not in (SCAN_ORDER | SCAN_LINE | {"legibility", "model"}):
            r = "not_checked"
        elif not customer_ok and (name in NEEDS_CUSTOMER or name in {"item"} | NEEDS_ITEM):
            r = "not_checked"
        elif not line_item_ok and name in NEEDS_ITEM:
            r = "not_checked"
        else:
            r = "proven"
        counts[r] += 1
        return r

    def add_boxes(rects, key, row, label, value, res):
        for r in rects or []:
            boxes.append({**r, "k": key, "r": row, "label": label, "value": value, "st": res})

    header, checks, lines = [], [], []
    if ex is not None:
        # order checks
        leg = ex.get("legibility")
        checks.append({"key": "c:legibility", "label": "Legibility", "value": str(leg) if leg else None,
                       "result": result("c:legibility", "legibility", leg or "-"),
                       "reasons": fails.get("c:legibility", []), "page": None, "quote": None, "boxes": False})
        sc = ex.get("suspicious_content") or {}
        sus_reads = [f for f in findings if f.get("field") in ("suspicious_content", "hidden_text")]
        sus_val = sc.get("quote") if sc.get("present") else (sus_reads[0].get("read") if sus_reads else None)
        none_txt = "None found" if mode == "text" else "None reported by the model (no text layer to scan)"
        row = {"key": "c:suspicious", "label": "Suspicious text", "value": sus_val or none_txt,
               "result": result("c:suspicious", "suspicious", "-"), "reasons": fails.get("c:suspicious", []),
               "page": sc.get("page") or (sus_reads[0].get("page") if sus_reads else None), "quote": None,
               "boxes": False}
        if bx.pages and sus_val:
            f = {"page": row["page"]}
            for cand in (sus_val, " ".join(sus_val.split()[1:])):
                rects, _ = bx.find(f, cand)
                if rects:
                    add_boxes(rects, "c:suspicious", "c:suspicious", "Suspicious text", sus_val, row["result"])
                    row["boxes"] = True
                    break
        checks.append(row)
        if "c:model" in fails:
            checks.append({"key": "c:model", "label": "Model output", "value": None, "result": result("c:model", "model", "-"),
                           "reasons": fails["c:model"], "page": None, "quote": None, "boxes": False})

        ids = {"customer_name": matched.get("customer_id"), "bill_to_name": matched.get("bill_to_id"),
               "ship_to_name": matched.get("ship_to_id"),
               "carrier_account_no": "on file" if matched.get("carrier_account_no") else None}
        centres: dict[str, tuple] = {}
        for name, label, kind in HEADER_FIELDS:
            f = ex.get(name) or {}
            v = _val(f)
            key = f"h:{name}"
            res = result(key, name, v)
            near = centres.get(NEAR_FIELD.get(name, "")) or bx.anchor(f)
            rects, c = bx.find(f, v, near=near) if v else (None, None)
            if c:
                centres[name] = c
            add_boxes(rects, key, key, label, v, res)
            header.append({"key": key, "label": label, "value": v, "kind": kind, "page": f.get("page"),
                           "quote": f.get("quote"), "result": res, "reasons": fails.get(key, []),
                           "matched": ids.get(name) if res == "proven" else None, "boxes": bool(rects)})

        mlines = {m.get("line_no"): m for m in matched.get("lines") or []}
        for n, ln in enumerate(ex.get("lines") or [], start=1):
            row_key = f"l{n}"
            m = mlines.get(n) or {}
            item_f = ln.get("item_no") if _val(ln.get("item_no")) else ln.get("customer_part_no")
            item_ok = bool(m.get("item_id"))
            near = bx.anchor(item_f)
            rects, item_c = bx.find(item_f, _val(item_f), near=near)
            row_y = item_c[1] if item_c else (near[1] if near else None)
            cells = {}
            for name, label in LINE_CELLS:
                f = item_f if name == "item" else (ln.get(name) or {})
                v = _val(f)
                if name == "item" and _val(ln.get("item_no")) and _val(ln.get("customer_part_no")):
                    v = f"{_val(ln['item_no'])} / {_val(ln['customer_part_no'])}"
                key = f"{row_key}:{name}"
                res = result(key, name, v, item_ok)
                if name != "item":
                    rects, _ = bx.find(f, v, row_y=row_y) if v else (None, None)
                add_boxes(rects, key, row_key, f"Line {n} {label.lower()}", v, res)
                cells[name] = {"value": v, "page": (f or {}).get("page"), "quote": (f or {}).get("quote"),
                               "result": res, "boxes": bool(rects)}
            checked = [c["result"] for k, c in cells.items() if k != "description" and c["value"] is not None]
            lres = "failed" if row_key in fails or "failed" in checked else (
                "proven" if checked and all(r == "proven" for r in checked) else "not_checked")
            info = []
            if m.get("item_id"):
                info.append(f"Matched item {m['item_id']}.")
            if m.get("base_qty") not in (None, "None") and m.get("base_uom"):
                info.append(f"Base quantity {m['base_qty']} {m['base_uom']}.")
            if m.get("list_price") not in (None, "None"):
                info.append(f"List price {float(m['list_price']):.4f} per {m.get('order_uom') or 'unit'}.")
            lines.append({"key": row_key, "n": n, "cells": cells, "result": lres, "reasons": fails.get(row_key, []),
                          "matched": " ".join(info)})
    bx.close()

    # queue columns
    total_txt = _val((ex or {}).get("order_total"))
    total = _num(total_txt)
    if total is None and ex:
        parts = [_num(_val(ln.get("line_total"))) for ln in ex.get("lines") or []]
        total = sum(parts) if parts and None not in parts else None
    cls = rec.get("classify") or {}
    calls = rec.get("calls") or []

    # audit trail
    audit = [("email", f"Email received from {rec.get('sender') or 'unknown sender'}, subject "
                       f"\u201c{rec.get('subject') or ''}\u201d.")]
    if rec.get("source_file"):
        audit.append(("pdf", f"Attachment {rec['source_file']}: {rec.get('pages', 0)} page(s), "
                             + ("text layer found." if mode == "text" else "no text layer, handled as a scan.")))
    else:
        audit.append(("pdf", "No PDF attachment."))
    for c in calls:
        audit.append((c.get("kind", "call"), _call_sentence(c, rec)))
    if route == "ignored":
        why = cls.get("reason") or cls.get("error") or ""
        audit.append(("route", f"Ignored: classified as {cls.get('doc_type', 'not a purchase order')}"
                               + (f", \u201c{why}\u201d" if why else "") + ". No gates run. Nothing written."))
    else:
        if ex is None:
            audit.append(("gates", "Gates not run: the model output could not be used."))
            for f in findings:
                audit.append(("check", f"{reason_label(f['code'])}: " + finding_sentence(f)[len(f["code"]) + 1:]))
        else:
            for gate, gcodes in GATES:
                hits = [f for f in findings if f.get("code") in gcodes]
                label = gate
                if gate == "evidence":
                    label = "evidence (text layer)" if mode == "text" else "evidence (two reads compared)"
                extra = ""
                if gate == "master data" and not customer_ok:
                    extra = " Stopped after the customer step: no customer match, so ship-to, items and prices were not checked."
                if gate == "duplicate" and not customer_ok:
                    extra = " Not run: needs a matched customer."
                n = len(hits)
                audit.append(("gate", f"{label[:1].upper() + label[1:]} gate: "
                                      + ("passed." if not n else f"{n} finding{'s' if n > 1 else ''}.") + extra))
                for f in hits:
                    audit.append(("check", f"{reason_label(f['code'])}: " + finding_sentence(f)[len(f["code"]) + 1:]))
            other = [f for f in findings if not any(f.get("code") in g for _, g in GATES)]
            for f in other:
                audit.append(("check", f"{reason_label(f['code'])}: " + finding_sentence(f)[len(f["code"]) + 1:]))
        if route == "auto":
            audit.append(("route", f"Auto-approved. Written to erp_import/{rec.get('csv_file')}, "
                                   f"{len((ex or {}).get('lines') or [])} row(s)."))
        else:
            audit.append(("route", f"Sent for your check: {', '.join(dict.fromkeys(reason_label(c) for c in codes)) or 'no reason'}. "
                                   f"Review package in review/{rec['doc_id']}/. No CSV written."))

    csv_view = None
    if route == "auto" and rec.get("csv_file"):
        p = run_dir / "erp_import" / rec["csv_file"]
        if p.is_file():
            text = p.read_text(encoding="utf-8")
            rows = list(csv.reader(io.StringIO(text)))
            csv_view = {"file": rec["csv_file"], "text": text, "head": rows[0] if rows else [],
                        "rows": rows[1:]}

    proven = counts["proven"]
    if route == "auto":
        n_rows = len(csv_view["rows"]) if csv_view else 0
        summary_line = (f"All {proven} checks proven. Written to {rec.get('csv_file')}, "
                        f"{n_rows} row{'s' if n_rows != 1 else ''}.")
    elif route == "ignored":
        summary_line = (f"Ignored: classified as {cls.get('doc_type', 'not a purchase order')}. "
                        f"No checks ran and nothing was written.")
    else:
        summary_line = None

    return {
        "id": rec["doc_id"], "index": index, "route": route, "mode": mode,
        "source_file": rec.get("source_file"), "sender": rec.get("sender") or "", "subject": rec.get("subject") or "",
        "po": _val((ex or {}).get("po_number")), "customer": _val((ex or {}).get("customer_name")),
        "customer_id": matched.get("customer_id"),
        "lines_n": len((ex or {}).get("lines") or []) if ex else None,
        "total": _money(total), "total_num": total,
        "currency": matched.get("currency") or _val((ex or {}).get("currency")) or "",
        "seconds": round(sum(c.get("seconds") or 0 for c in calls), 1), "cost": _cost(calls),
        "codes": codes, "code_names": {c: REASONS.get(c, "") for c in codes},
        "code_tones": {c: tone(c) for c in codes},
        "classify": {"doc_type": cls.get("doc_type"), "reason": cls.get("reason") or cls.get("error")},
        "findings": fview, "summary_line": summary_line, "checks": checks, "header": header, "lines": lines,
        "boxes": boxes, "audit": [{"step": s, "text": t} for s, t in audit], "csv": csv_view,
        "pages": _page_images(run_dir, rec), "proven": proven, "counts": counts,
    }


# ---- the page -------------------------------------------------------------------------------

def _read_json(p: Path) -> dict | None:
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def build_data(run_dir: Path) -> dict:
    records = [json.loads(line) for line in (run_dir / "audit.jsonl").read_text(encoding="utf-8").splitlines()
               if line.strip()]
    run = _read_json(run_dir / "run.json") or {}
    score = _read_json(run_dir / "score.json")
    orders = [build_order(run_dir, r, i) for i, r in enumerate(records)]
    calls = [c for r in records for c in r.get("calls") or []]
    n = len(records)
    head = (score or {}).get("headline") or {}
    cost_note = ((score or {}).get("cost_and_time") or {}).get("note") or run.get("cost_note")
    run_id = str(run.get("run_id") or run_dir.name)
    return {
        "run_id": run_id,
        "demo": run_id.lower().startswith("demo"),
        "models": run.get("models") or sorted({m for c in calls for m in c.get("model") or []}),
        "model_seconds": run.get("model_seconds_total", round(sum(c.get("seconds") or 0 for c in calls), 1)),
        "model_calls": run.get("model_calls", len(calls)),
        "documents": n,
        "auto": sum(o["route"] == "auto" for o in orders),
        "review": sum(o["route"] == "review" for o in orders),
        "ignored": sum(o["route"] == "ignored" for o in orders),
        "cost": _cost(calls),
        "cost_note": COST_NOTE, "cost_note_full": cost_note or "",
        "scored": score is not None and "wrong_values_written" in head,
        "wrong_values": head.get("wrong_values_written"), "values_written": head.get("values_written"),
        "reason_help": {c: {"label": lb, "icon": ic, "todo": t, "why": w,
                            "cmp": list(REASON_COMPARE.get(c, ("On PDF", "Expected", None))), "quote": c in REASON_QUOTE}
                        for c, (lb, ic, t, w) in REASON_UI.items()},
        "orders": orders,
    }


def _font_css() -> str:
    """@font-face rules with the woff2 files inlined as base64 (no network request)."""
    out = []
    for family, weight, name in FONTS:
        b64 = base64.b64encode((FONT_DIR / name).read_bytes()).decode("ascii")
        out.append(f'@font-face{{font-family:"{family}";font-style:normal;font-weight:{weight};'
                   f'font-display:block;src:url(data:font/woff2;base64,{b64}) format("woff2")}}')
    return "\n".join(out)


def _json_for_html(data: dict) -> str:
    s = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    # keep the script block closed and keep the file free of URL-like text
    return s.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026").replace("://", ":\\/\\/")


def build_report(run_dir: Path, out_html: Path | None = None) -> Path:
    run_dir = Path(run_dir)
    out_html = Path(out_html) if out_html else run_dir / "run-report.html"
    data = build_data(run_dir)
    title = f"PO intake, run {data['run_id']}" + (" (demo data)" if data["demo"] else "")
    html = (TEMPLATE.replace("__FONTS__", _font_css()).replace("__TITLE__", _esc(title))
            .replace("__DATA__", _json_for_html(data)))
    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_html.write_text(html, encoding="utf-8")
    return out_html


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="po_agent.report", description="Build run-report.html for a run folder")
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    path = build_report(a.run_dir, a.out)
    print(f"{path} ({path.stat().st_size / 1024:.0f} KB)")
    return 0


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
__FONTS__
/* "Signal" tokens: docs/ui-reference-v2.md section 4 */
:root{
  --bg:#f7f8fa;--surface:#ffffff;--sunk:#eef0f3;--hover:#f3f4f7;--sel:#edf1fd;
  --text:#17181c;--text-2:#5b606b;--line:#e4e6eb;--line-2:#cdd1d9;--line-strong:#878d98;
  --accent:#2453d6;--accent-bg:#ecf1fe;--accent-line:#b9c9f7;--on-accent:#ffffff;
  --ok:#167a43;--ok-bg:#e7f5ed;--muted-bg:#eef0f3;--danger:#c2261c;
  --pg-accent:#2453d6;--pg-ok:#167a43;--pg-quiet:#878d98;--pg-white:#ffffff;
  --lift:0 1px 2px rgba(16,18,24,.06),0 12px 32px rgba(16,18,24,.14);
  --sans:"Hanken Grotesk",ui-sans-serif,system-ui,"Segoe UI",sans-serif;
  --mono:ui-monospace,"Cascadia Mono",Consolas,monospace;
  --g:32px;--split:56%;color-scheme:light;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#0e0f12;--surface:#16181c;--sunk:#1b1d22;--hover:#1d2026;--sel:#1b2440;
  --text:#eceef2;--text-2:#a0a5b0;--line:#272a31;--line-2:#363a45;--line-strong:#6f7582;
  --accent:#7d9dff;--accent-bg:#1c2647;--accent-line:#34478a;--on-accent:#0e0f12;
  --ok:#4fc483;--ok-bg:#132a1d;--muted-bg:#22252c;--danger:#ff7a6e;
  --lift:0 12px 32px rgba(0,0,0,.55);color-scheme:dark}}
:root[data-theme="dark"]{
  --bg:#0e0f12;--surface:#16181c;--sunk:#1b1d22;--hover:#1d2026;--sel:#1b2440;
  --text:#eceef2;--text-2:#a0a5b0;--line:#272a31;--line-2:#363a45;--line-strong:#6f7582;
  --accent:#7d9dff;--accent-bg:#1c2647;--accent-line:#34478a;--on-accent:#0e0f12;
  --ok:#4fc483;--ok-bg:#132a1d;--muted-bg:#22252c;--danger:#ff7a6e;
  --lift:0 12px 32px rgba(0,0,0,.55);color-scheme:dark}
*{box-sizing:border-box}
html,body{margin:0;background:var(--bg);color:var(--text)}
body{font-family:var(--sans);font-size:14px;line-height:20px;font-variant-numeric:tabular-nums;-webkit-font-smoothing:antialiased}
button,input,select,textarea{font:inherit;color:inherit}
h1,h2,h3,p{margin:0}
h1,h2,h3{font-weight:600}
.file{font-family:var(--mono);font-size:12px}
.num{text-align:right;white-space:nowrap}
.muted{color:var(--text-2)}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
a,.link{color:var(--accent);text-decoration:none;background:none;border:0;padding:0;cursor:pointer;font-weight:500}
a:hover,.link:hover{text-decoration:underline;text-underline-offset:3px}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
svg.g{width:16px;height:16px;flex:none;fill:none;stroke:currentColor;stroke-width:1.5;stroke-linecap:round;stroke-linejoin:round}
svg.sm{width:12px;height:12px;stroke-width:1.8}
kbd{display:inline-block;min-width:20px;padding:0 5px;font-family:var(--sans);font-size:12px;line-height:18px;border:1px solid var(--line-2);border-radius:4px;background:var(--surface);color:var(--text-2)}
[hidden]{display:none !important}

/* controls */
.btn{height:32px;display:inline-flex;align-items:center;justify-content:center;gap:6px;padding:0 12px;border:1px solid var(--line-2);border-radius:6px;background:var(--surface);
  cursor:pointer;white-space:nowrap;font-weight:500;transition:background-color 120ms}
.btn:hover{background:var(--hover)}
.btn.icon{width:32px;padding:0}
.btn[disabled]{opacity:.45;cursor:default;background:var(--surface)}
.btn.primary{height:36px;padding:0 14px;background:var(--accent);border-color:var(--accent);color:var(--on-accent)}
.btn.primary:hover{background:var(--accent)}
.btn.ghost{border-color:transparent;background:transparent}
.btn.ghost:hover{background:var(--hover)}
.btn.sm{height:28px;padding:0 10px;font-size:13px}
select,input[type="search"],textarea{height:32px;border:1px solid var(--line-2);border-radius:6px;background:var(--surface);padding:0 10px}
select:hover,input[type="search"]:hover,textarea:hover{border-color:var(--line-strong)}
input[type="search"]{width:240px}
::placeholder{color:var(--text-2)}

/* status: dot or pill, the word always carries the meaning */
.dot{width:8px;height:8px;border-radius:50%;flex:none;display:inline-block;background:var(--line-strong)}
.dot.review{background:var(--accent)}.dot.auto{background:var(--ok)}
.pill{display:inline-flex;align-items:center;gap:6px;height:24px;padding:0 10px;border-radius:999px;font-size:13px;line-height:20px;font-weight:500;white-space:nowrap;background:var(--muted-bg);color:var(--text-2)}
.pill.review{background:var(--accent-bg);color:var(--accent)}
.pill.auto{background:var(--ok-bg);color:var(--ok)}
.prob{display:inline-flex;align-items:center;gap:6px;white-space:nowrap;font-weight:500;color:var(--text)}
.prob svg{color:var(--accent)}
.prob .where{font-weight:400;color:var(--text-2)}
.probs{display:inline-flex;align-items:center;gap:8px}
.more{font-size:12px;line-height:16px;color:var(--text-2);padding:2px 6px;border-radius:4px;background:var(--muted-bg);font-weight:500}
.res{display:inline-flex;align-items:center;gap:4px;font-size:13px;line-height:20px;white-space:nowrap}
.res.proven{color:var(--ok)}.res.failed{color:var(--accent);font-weight:500}.res.not_checked{color:var(--text-2)}
.n-pin{display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;flex:none;border-radius:50%;background:var(--accent);color:var(--on-accent);
  font-size:12px;line-height:16px;font-weight:600;border:0;padding:0}
.demo{display:inline-flex;align-items:center;height:22px;padding:0 8px;border-radius:999px;border:1px solid var(--accent-line);color:var(--accent);font-size:12px;font-weight:500;white-space:nowrap}
.tag{font-size:12px;line-height:16px;padding:2px 8px;border-radius:999px;background:var(--ok-bg);color:var(--ok);white-space:nowrap;font-weight:500}

/* top bar */
.bar{position:sticky;top:0;z-index:20;height:52px;display:flex;align-items:center;gap:12px;padding:0 var(--g);background:var(--surface);border-bottom:1px solid var(--line)}
.brand{display:inline-flex;align-items:center;gap:8px;font-weight:600;font-size:16px;white-space:nowrap}
.brand .mk{width:22px;height:22px;border-radius:6px;background:var(--text);color:var(--surface);display:inline-flex;align-items:center;justify-content:center}
.brand .mk svg{width:14px;height:14px;stroke-width:2}
.bar .run{color:var(--text-2);white-space:nowrap}
.bar .grow{flex:1}
.bar .meta{font-size:13px;color:var(--text-2);white-space:nowrap}

/* queue */
.page{max-width:1440px;padding:0 var(--g) 48px}
.flow{display:flex;align-items:center;gap:12px;margin-top:20px;padding:10px 12px 10px 16px;background:var(--surface);border:1px solid var(--line);border-radius:8px;flex-wrap:wrap}
.flow ol{display:flex;align-items:center;gap:8px;list-style:none;margin:0;padding:0;flex-wrap:wrap;flex:1}
.flow li{display:inline-flex;align-items:center;gap:8px;font-weight:500;white-space:nowrap}
.flow li .ic{width:28px;height:28px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;background:var(--muted-bg);color:var(--text-2)}
.flow li.ok .ic{background:var(--ok-bg);color:var(--ok)}
.flow li.you .ic{background:var(--accent-bg);color:var(--accent)}
.flow li.you{color:var(--accent)}
.flow .to{color:var(--line-strong)}
.flow .or{color:var(--text-2);font-weight:400}
.head{display:flex;align-items:flex-end;justify-content:space-between;gap:32px;flex-wrap:wrap;padding:32px 0 20px}
.head h1{font-size:28px;line-height:36px;letter-spacing:-.015em}
.head h1 .n{color:var(--accent)}
.head h1.calm .n{color:var(--ok)}
.head .cta{display:flex;align-items:center;gap:12px;margin-top:16px}
.head .cta .kh{font-size:13px;color:var(--text-2)}
.stats{display:flex;gap:0;margin:0}
.stats>div{padding:0 20px;border-left:1px solid var(--line)}
.stats>div:first-child{padding-left:0;border-left:0}
.stats dt{font-size:13px;line-height:20px;color:var(--text-2)}
.stats dd{margin:2px 0 0;font-size:20px;line-height:28px;font-weight:600;white-space:nowrap}
.stats dd small{font-size:13px;font-weight:400;color:var(--text-2);margin-left:4px}
.stats dd.bad{color:var(--danger)}
.stats dd.none{font-size:16px;font-weight:500;color:var(--text-2)}
.dist{display:flex;gap:4px;align-items:stretch}
.dist button{flex:var(--n) 1 0;min-width:136px;display:flex;flex-direction:column;align-items:flex-start;gap:8px;padding:0 0 8px;border:0;background:none;cursor:pointer;text-align:left;color:var(--text-2);border-radius:4px}
.dist button .b{display:block;width:100%;height:6px;border-radius:3px;background:var(--line-2);opacity:.45;transition:background-color 120ms}
.dist button.review .b{background:var(--accent)}.dist button.auto .b{background:var(--ok)}.dist button.ignored .b{background:var(--line-strong)}
.dist button[aria-pressed="true"] .b{opacity:1}
.dist button .l{display:inline-flex;align-items:baseline;gap:6px;font-weight:500;white-space:nowrap}
.dist button .l b{font-size:16px;font-weight:600;color:var(--text)}
.dist button[aria-pressed="true"] .l{color:var(--text)}
.dist button:hover .l{color:var(--text)}
.dist .all{flex:0 0 auto;min-width:0;padding-left:12px}
.dist .all .b{background:transparent;opacity:1}
.tools{display:flex;align-items:center;gap:8px;margin-top:16px}
.tools .grow{flex:1}
.tools .count{color:var(--text-2)}
.list{margin-top:12px;background:var(--surface);border:1px solid var(--line);border-radius:8px;overflow:hidden}
table{width:100%;border-collapse:collapse}
.list th{height:40px;padding:0 16px;text-align:left;font-size:13px;line-height:20px;font-weight:500;color:var(--text-2);border-bottom:1px solid var(--line);white-space:nowrap}
.list th.num{text-align:right}
.list th button{all:unset;cursor:pointer;display:inline-flex;align-items:center;gap:4px}
.list th button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.list th .arrow{visibility:hidden}
.list th[aria-sort] .arrow{visibility:visible}
.list td{height:56px;padding:0 16px;border-bottom:1px solid var(--line);white-space:nowrap}
.list tbody tr{cursor:pointer;transition:background-color 120ms}
.list tbody tr:hover{background:var(--hover)}
.list tbody tr[aria-selected="true"]{background:var(--sel)}
.list tbody tr[aria-selected="true"] td:first-child{box-shadow:inset 3px 0 0 var(--accent)}
.list tbody tr:focus{outline:none}
.list tbody tr:focus-visible{outline:2px solid var(--accent);outline-offset:-2px}
.list tbody tr:last-child td{border-bottom:0}
.list td.st{width:40px;padding-right:0}
.list .who{font-weight:500;overflow:hidden;text-overflow:ellipsis;max-width:320px}
.list .po{font-size:13px;line-height:18px;color:var(--text-2)}
.list .calm{color:var(--text-2);display:inline-flex;align-items:center;gap:6px}
.list .calm svg{color:var(--ok)}
.list .calm.ign svg{color:var(--text-2)}
.list td .cur{color:var(--text-2);margin-left:4px;font-size:13px}
.list td.go{width:44px;color:var(--line-strong)}
.list .mine{margin-left:8px}
.w-n{width:72px}.w-tot{width:150px}
.m-prob{display:none}
.empty td{height:auto;padding:40px 16px;cursor:default;white-space:normal;text-align:left}
.empty .e{display:flex;align-items:center;gap:12px}
.empty .e .ic{width:36px;height:36px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;background:var(--ok-bg);color:var(--ok)}
.empty b{display:block;font-weight:600}
.empty .muted{display:block}
.lfoot{display:flex;justify-content:space-between;align-items:center;gap:16px;margin-top:12px;font-size:13px;color:var(--text-2);flex-wrap:wrap}

/* order detail */
.detail{display:flex;flex-direction:column;height:calc(100vh - 52px)}
.dhead{display:flex;align-items:center;gap:16px;padding:12px var(--g);background:var(--surface);border-bottom:1px solid var(--line);flex-wrap:wrap}
.dhead .t{min-width:0;flex:1}
.dhead h1{font-size:20px;line-height:28px;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.dhead h1 .po{font-size:16px;font-weight:400;color:var(--text-2)}
.dhead .sub{font-size:13px;line-height:18px;color:var(--text-2);margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.dhead .nav{display:flex;align-items:center;gap:8px}
.dhead .pos{color:var(--text-2);white-space:nowrap;font-size:13px}
.mtabs{display:none}
.split{flex:1;min-height:0;display:flex}
.docpane{flex:0 0 var(--split);min-width:0;display:flex;flex-direction:column;background:var(--sunk)}
.splitter{flex:0 0 5px;cursor:col-resize;background:var(--line);position:relative}
.splitter:hover{background:var(--accent-line)}
.splitter:focus-visible{outline:2px solid var(--accent);outline-offset:-2px}
.side{flex:1;min-width:0;overflow:auto;background:var(--surface)}
.dbar{height:44px;flex:none;display:flex;align-items:center;gap:6px;padding:0 12px;border-bottom:1px solid var(--line);background:var(--surface)}
.dbar .btn{height:28px}.dbar .btn.icon{width:28px}
.dbar .zoom{min-width:44px;text-align:right;font-size:13px;color:var(--text-2)}
.dbar .pg{font-size:13px;color:var(--text-2);white-space:nowrap;margin-right:6px}
.dbar .grow{flex:1}
.key{display:inline-flex;align-items:center;gap:6px;font-size:13px;color:var(--text-2);white-space:nowrap;margin-left:8px}
.key i{display:inline-block;width:14px;height:10px;border-radius:2px}
.key i.k-acc{border:2px solid var(--pg-accent)}.key i.k-ok{border:1px solid var(--pg-quiet)}
.hint{display:flex;align-items:center;gap:8px;padding:8px 12px;font-size:13px;color:var(--text-2);background:var(--surface);border-bottom:1px solid var(--line)}
.hint .grow{flex:1}
.canvas{flex:1;min-height:0;overflow:auto;padding:24px}
.sheet{position:relative;margin:0 auto;background:var(--pg-white);border-radius:2px;outline:1px solid var(--line-2)}
.sheet img{display:block;width:100%;height:auto;user-select:none;border-radius:2px}
/* the PDF image is white in both themes: boxes use fixed page colours */
.box{position:absolute;border:1px solid var(--pg-quiet);border-radius:3px;cursor:pointer;color:var(--pg-quiet);opacity:.35}
.box.failed{border:2px solid var(--pg-accent);color:var(--pg-accent);opacity:1}
.box.not_checked{border-style:dashed}
.box.on{opacity:1}
.box.proven.on{border-color:var(--pg-ok);color:var(--pg-ok)}
.box.on::after{content:"";position:absolute;inset:0;background:currentColor;opacity:.12}
.box .n-pin{position:absolute;left:-26px;top:50%;margin-top:-10px;background:var(--pg-accent);color:var(--pg-white)}
.box.ping{animation:locate 700ms ease-out 2}
@keyframes locate{from{outline:2px solid currentColor;outline-offset:10px}to{outline:2px solid currentColor;outline-offset:0}}
.pop{position:absolute;z-index:6;min-width:180px;max-width:320px;padding:8px 12px;background:var(--surface);color:var(--text);border:1px solid var(--line);
  border-radius:8px;box-shadow:var(--lift);pointer-events:none}
.pop .v{font-weight:500;overflow-wrap:anywhere}
.pop .l{display:flex;justify-content:space-between;gap:12px;margin-top:2px;font-size:13px;color:var(--text-2)}
.nodoc{padding:24px;color:var(--text-2)}

.verdict{padding:20px var(--g) 24px 24px}
.verdict h2{font-size:16px;line-height:24px;display:flex;align-items:center;gap:8px}
.issues{list-style:none;margin:12px 0 0;padding:0;display:flex;flex-direction:column;gap:12px}
.issue{padding:14px 16px 12px;border:1px solid var(--line);border-radius:8px;background:var(--surface);transition:background-color 120ms}
.issue:hover{background:var(--hover)}
.issue .ih{display:flex;align-items:center;gap:10px}
.issue .ih .prob{font-size:16px;line-height:24px;font-weight:600}
.issue .ih .where{font-size:14px}
.issue .ih .grow{flex:1}
.cmp{display:flex;align-items:center;gap:12px;margin:12px 0 0 30px;flex-wrap:wrap}
.cmp .v{display:flex;flex-direction:column;gap:2px;min-width:0}
.cmp .k{font-size:13px;line-height:18px;color:var(--text-2)}
.cmp .x{font-size:20px;line-height:28px;font-weight:600;overflow-wrap:anywhere}
.cmp .read .x{color:var(--accent)}
.cmp .ar{color:var(--line-strong);align-self:flex-end;margin-bottom:6px}
.cmp .d{align-self:flex-end;margin-bottom:4px;font-size:13px;line-height:20px;font-weight:600;padding:0 8px;border-radius:999px;background:var(--accent-bg);color:var(--accent)}
.quote{margin:12px 0 0 30px;padding:8px 12px;border-left:3px solid var(--accent-line);background:var(--sunk);border-radius:0 6px 6px 0;font-size:13px;line-height:20px;
  overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.fact{margin:8px 0 0 30px;color:var(--text-2)}
.act{display:flex;align-items:center;gap:8px;margin:12px 0 0 30px;font-weight:500}
.act svg{color:var(--accent)}
.ifoot{display:flex;align-items:center;gap:16px;margin:10px 0 0 30px;font-size:13px}
.ifoot details{color:var(--text-2)}
.ifoot summary{cursor:pointer;color:var(--text-2);list-style:none;font-weight:500}
.ifoot summary::-webkit-details-marker{display:none}
.ifoot summary:hover{color:var(--text)}
.why{margin:6px 0 0 30px;font-size:13px;line-height:20px;color:var(--text-2)}
.allclear{display:flex;gap:12px;align-items:center}
.allclear .ic{width:36px;height:36px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;background:var(--ok-bg);color:var(--ok);flex:none}
.allclear.ign .ic{background:var(--muted-bg);color:var(--text-2)}
.allclear b{display:block;font-size:16px;line-height:24px}
.allclear span{color:var(--text-2)}
.mine{display:flex;align-items:center;gap:12px;margin-top:16px;padding:10px 14px;border-radius:8px;background:var(--sunk);flex-wrap:wrap}
.mine label{display:inline-flex;align-items:center;gap:8px;font-weight:500;cursor:pointer}
.mine input[type="checkbox"]{width:16px;height:16px;margin:0;accent-color:var(--accent)}
.mine .note{font-size:13px;color:var(--text-2)}
.mine .grow{flex:1}
.mine textarea{flex:1 1 100%;height:56px;padding:6px 10px;resize:vertical}

.tabs{position:sticky;top:0;z-index:4;display:flex;gap:16px;height:44px;align-items:flex-end;padding:0 var(--g) 0 24px;background:var(--surface);border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.tabs button{border:0;background:none;padding:0 2px;height:43px;cursor:pointer;color:var(--text-2);border-bottom:2px solid transparent;margin-bottom:-1px;white-space:nowrap;font-weight:500}
.tabs button[aria-selected="true"]{color:var(--text);border-bottom-color:var(--accent)}
.tabs button:focus-visible{outline:2px solid var(--accent);outline-offset:-2px}
.tabs .c{font-size:12px;color:var(--text-2);margin-left:6px;font-weight:500}
.sum{display:flex;gap:8px;flex-wrap:wrap;padding:14px var(--g) 6px 24px}
.sect{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:16px var(--g) 6px 24px}
.sect h3{font-size:13px;line-height:20px;font-weight:600;color:var(--text-2)}
.frow{display:grid;grid-template-columns:140px minmax(0,1fr) auto;gap:0 12px;align-items:start;padding:6px var(--g) 6px 22px;border-left:2px solid transparent;transition:background-color 120ms}
.frow:hover,.frow.hl{background:var(--hover)}
.frow.cur{background:var(--sel)}
.frow:focus{outline:none}
.frow:focus-visible{outline:2px solid var(--accent);outline-offset:-2px}
.frow.failed{border-left-color:var(--accent);padding-top:10px;padding-bottom:10px}
.frow .lab{color:var(--text-2)}
.frow .val{min-width:0;overflow-wrap:anywhere}
.frow .val .id{margin-left:8px;font-size:13px;color:var(--text-2);white-space:nowrap}
.frow .rcol{justify-self:end;display:inline-flex}
.frow .ex{grid-column:2 / 4;min-width:0}
.ev{display:none;margin-top:4px;font-size:13px;line-height:20px;color:var(--text-2);overflow-wrap:anywhere}
.frow.failed .ev,.frow.cur .ev,.frow:focus .ev,.lmore.cur .ev,.lmore.show .ev{display:block}
.cmpline{margin-top:2px;font-size:13px;line-height:20px;color:var(--accent);font-weight:500}
.nc{padding:8px var(--g) 8px 24px;font-size:13px;color:var(--text-2)}
.ltable{overflow-x:auto}
.ltable table{min-width:520px}
.ltable th{height:36px;padding:0 8px;text-align:left;font-size:13px;font-weight:500;color:var(--text-2);border-bottom:1px solid var(--line);white-space:nowrap}
.ltable th:first-child,.ltable td:first-child{padding-left:22px}
.ltable th.num{text-align:right}
.ltable td{height:36px;padding:0 8px;border-bottom:1px solid var(--line);white-space:nowrap}
.ltable td.trunc{max-width:200px;overflow:hidden;text-overflow:ellipsis}
.ltable tr>td:first-child{border-left:2px solid transparent}
.ltable tr.lrow{transition:background-color 120ms}
.ltable tr.lrow.failed>td:first-child{border-left-color:var(--accent)}
.ltable tr.lrow.cur{background:var(--sel)}
.ltable tr.lrow.hl{background:var(--hover)}
.ltable tr.lrow:focus{outline:none}
.ltable tr.lrow:focus-visible{outline:2px solid var(--accent);outline-offset:-2px}
.ltable td.bad{color:var(--accent);font-weight:600}
.ltable tr.lmore td{height:auto;padding:0 8px 10px 22px;white-space:normal}
.ltable tr.lmore{display:none}
.ltable tr.lmore.show,.ltable tr.lmore.cur{display:table-row}
.ltable tr.lmore.cur{background:var(--sel)}
.ltable tr.lrow.failed+tr.lmore>td:first-child{border-left-color:var(--accent)}
.audit{list-style:none;margin:16px var(--g) 24px 24px;padding:0}
.audit li{display:grid;grid-template-columns:72px minmax(0,1fr);gap:12px;padding:8px 0;border-top:1px solid var(--line)}
.audit li:first-child{border-top:0}
.audit .sx{font-size:13px;color:var(--text-2);font-weight:500}
.audit .tx{overflow-wrap:anywhere}
.csvt{margin:12px var(--g) 12px 24px;border:1px solid var(--line);border-radius:8px;overflow-x:auto}
.csvt th,.csvt td{height:32px;padding:0 12px;text-align:left;border-bottom:1px solid var(--line);font-size:13px;white-space:nowrap}
.csvt th{font-weight:500;color:var(--text-2)}
.csvt td:first-child{color:var(--text-2)}
pre.raw{margin:0 var(--g) 24px 24px;padding:10px 12px;background:var(--sunk);border-radius:8px;overflow-x:auto;font-family:var(--mono);font-size:12px;line-height:20px}
.note-p{padding:16px var(--g) 16px 24px;color:var(--text-2)}
.dialog{position:fixed;z-index:30;top:60px;right:var(--g);width:400px;max-height:calc(100vh - 80px);overflow:auto;background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:16px 20px 20px;box-shadow:var(--lift)}
.dialog .dh{display:flex;align-items:center;justify-content:space-between;margin-bottom:4px}
.dialog h2{font-size:16px;line-height:24px}
.dialog h3{font-size:13px;line-height:20px;color:var(--text-2);margin:16px 0 8px;font-weight:600}
.dialog ul{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:8px}
.dialog li{display:grid;grid-template-columns:20px minmax(0,1fr);gap:2px 10px;align-items:start}
.dialog li svg{color:var(--accent);margin-top:2px}
.dialog li b{font-weight:500}
.dialog li span.w{grid-column:2;font-size:13px;line-height:18px;color:var(--text-2)}
.dialog dl{display:grid;grid-template-columns:84px 1fr;gap:6px 12px;margin:0}
.dialog dt{white-space:nowrap}.dialog dd{margin:0;color:var(--text-2)}
.printfoot,.printonly{display:none}

@media screen and (max-width:1099px){
  .detail{height:auto;min-height:calc(100vh - 52px)}
  .mtabs{display:flex;gap:4px;padding:8px var(--g);background:var(--surface);border-bottom:1px solid var(--line)}
  .mtabs button{height:36px;padding:0 14px;border:1px solid transparent;border-radius:6px;background:transparent;cursor:pointer;color:var(--text-2);font-weight:500}
  .mtabs button[aria-pressed="true"]{background:var(--sunk);color:var(--text)}
  .split{display:block;flex:none}
  .splitter{display:none}
  .detail[data-m="doc"] .side,.detail[data-m="fields"] .docpane{display:none}
  .side{overflow:visible}
  .tabs{top:52px}
}
@media screen and (max-width:767px){
  :root{--g:16px}
  .bar{gap:8px}
  .bar .meta,.bar .opt{display:none}
  .flow{padding:10px 12px}
  .flow .to{display:none}
  .flow ol{gap:6px 12px}
  .head{padding:24px 0 16px;gap:16px}
  .head h1{font-size:28px;line-height:36px}
  .head .cta{width:100%}
  .head .cta .btn.primary{flex:1;height:44px}
  .head .cta .kh{display:none}
  .stats{width:100%}
  .stats>div{flex:1;padding:0 12px}
  .stats dd{font-size:16px;line-height:24px}
  .dist button{min-width:0}
  .tools{flex-wrap:wrap}
  .tools .grow{display:none}
  .tools select,.tools input[type="search"]{flex:1 1 100%;width:auto;height:40px}
  .c-opt{display:none}
  .list td{padding:10px 12px;height:auto;white-space:normal}
  .list td.st{padding-left:14px;vertical-align:top;padding-top:16px}
  .list td.go{vertical-align:top;padding-top:14px}
  .list .who{max-width:190px;white-space:nowrap}
  .list td.num{vertical-align:top}
  .m-prob{display:block;margin-top:4px}
  .m-prob .probs,.m-prob .prob,.m-prob .calm{display:inline;white-space:normal}
  .m-prob svg{vertical-align:-3px;margin-right:6px}
  .m-prob .where{margin-left:4px}
  .m-prob .more{margin-left:6px}
  .dist{display:grid;grid-template-columns:1fr 1fr;gap:12px 8px}
  .dist .all{padding-left:0}
  .dist .all .b{background:var(--line);opacity:1}
  .dist button .l{white-space:nowrap;flex-direction:row;gap:6px}
  .stats dt{font-size:12px;line-height:16px}
  .dhead{gap:8px}
  .dhead .pos{display:none}
  .dhead .t{flex:1 1 100%;order:2}
  .dhead .nav{order:1;margin-left:auto}
  .btn{height:40px}.btn.icon{width:40px}
  .frow{grid-template-columns:110px minmax(0,1fr) auto;padding-right:16px}
  .verdict{padding:16px}
  .cmp,.quote,.fact,.act,.ifoot,.why{margin-left:0}
  .dbar .key{display:none}
  .dialog{left:16px;right:16px;width:auto}
}
@media (prefers-reduced-motion:reduce){*{transition:none !important;animation:none !important}}
@media print{
  :root,:root[data-theme="dark"]{
    --bg:#ffffff;--surface:#ffffff;--sunk:#eef0f3;--hover:#f3f4f7;--sel:#edf1fd;
    --text:#17181c;--text-2:#5b606b;--line:#e4e6eb;--line-2:#cdd1d9;--line-strong:#878d98;
    --accent:#2453d6;--accent-bg:#ecf1fe;--accent-line:#b9c9f7;--on-accent:#ffffff;
    --ok:#167a43;--ok-bg:#e7f5ed;--muted-bg:#eef0f3;--danger:#c2261c;color-scheme:light}
  .bar{position:static}
  .noprint,.btn,.tools,.splitter,.tabs,.mtabs,.dialog,.pop,.flow,.hint,.dbar,.mine textarea{display:none !important}
  thead{display:table-header-group}
  tr,.frow,.audit li,.issue{break-inside:avoid}
  .pill,.n-pin,.d{border:1px solid currentColor}
  .detail{display:block;height:auto}
  .split{display:block}
  .docpane,.side{display:block !important;overflow:visible}
  .canvas{overflow:visible;padding:0}
  .sheet{width:auto !important;max-width:520px;break-inside:avoid}
  .side>section{display:block !important}
  .ev,.why{display:block}
  .ltable tr.lmore{display:table-row}
  .printonly{display:flex}
  .printfoot{display:block;margin:16px var(--g);font-size:12px;line-height:16px;color:var(--text-2)}
}
</style>
</head>
<body>
<template id="glyphs">
<svg class="g" data-g="review" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="5.5"/><path d="M8 5v3.5M8 11v.01"/></svg>
<svg class="g" data-g="auto" viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 8.5l3 3 6-7"/></svg>
<svg class="g" data-g="ignored" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="5.5"/><path d="M5.5 8h5"/></svg>
<svg class="g" data-g="proven" viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 8.5l3 3 6-7"/></svg>
<svg class="g" data-g="not_checked" viewBox="0 0 16 16" aria-hidden="true"><path d="M5 8h6"/></svg>
<svg class="g" data-g="failed" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="5.5"/><path d="M8 5v3.5M8 11v.01"/></svg>
<svg class="g" data-g="hash" viewBox="0 0 16 16" aria-hidden="true"><path d="M6.5 2.5L5 13.5M11 2.5L9.5 13.5M3 6h10.5M2.5 10H13"/></svg>
<svg class="g" data-g="user" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="5.5" r="2.5"/><path d="M3 13.5c.8-2.6 2.8-4 5-4s4.2 1.4 5 4"/></svg>
<svg class="g" data-g="pin" viewBox="0 0 16 16" aria-hidden="true"><path d="M8 14s4.5-4.2 4.5-7.5a4.5 4.5 0 0 0-9 0C3.5 9.8 8 14 8 14z"/><circle cx="8" cy="6.5" r="1.6"/></svg>
<svg class="g" data-g="box" viewBox="0 0 16 16" aria-hidden="true"><path d="M2.5 5L8 2.5 13.5 5v6L8 13.5 2.5 11z"/><path d="M2.5 5L8 7.5 13.5 5M8 7.5v6"/></svg>
<svg class="g" data-g="ruler" viewBox="0 0 16 16" aria-hidden="true"><path d="M2 11l9-9 3 3-9 9z"/><path d="M5 8l1.5 1.5M7 6l1.5 1.5M9 4l1.5 1.5"/></svg>
<svg class="g" data-g="tag" viewBox="0 0 16 16" aria-hidden="true"><path d="M2.5 2.5h5l6 6-5 5-6-6z"/><circle cx="5.5" cy="5.5" r=".9"/></svg>
<svg class="g" data-g="sum" viewBox="0 0 16 16" aria-hidden="true"><path d="M12 3H4l4.5 5L4 13h8"/></svg>
<svg class="g" data-g="search" viewBox="0 0 16 16" aria-hidden="true"><circle cx="7" cy="7" r="4"/><path d="M10 10l3.5 3.5"/></svg>
<svg class="g" data-g="split" viewBox="0 0 16 16" aria-hidden="true"><path d="M2.5 5h9L9 2.5M13.5 11h-9L7 13.5"/></svg>
<svg class="g" data-g="copy" viewBox="0 0 16 16" aria-hidden="true"><rect x="5.5" y="5.5" width="8" height="8" rx="1.5"/><path d="M3 10.5V4A1.5 1.5 0 0 1 4.5 2.5H11"/></svg>
<svg class="g" data-g="eye" viewBox="0 0 16 16" aria-hidden="true"><path d="M2 8s2.2-4.5 6-4.5S14 8 14 8s-2.2 4.5-6 4.5S2 8 2 8z"/><circle cx="8" cy="8" r="1.8"/><path d="M3 13L13 3"/></svg>
<svg class="g" data-g="truck" viewBox="0 0 16 16" aria-hidden="true"><path d="M1.5 4.5h8v6.5h-8zM9.5 7h3l2 2.2V11h-5"/><circle cx="4.5" cy="12" r="1.2"/><circle cx="11.5" cy="12" r="1.2"/></svg>
<svg class="g" data-g="shield" viewBox="0 0 16 16" aria-hidden="true"><path d="M8 2l5 2v4c0 3-2.2 5.2-5 6-2.8-.8-5-3-5-6V4z"/><path d="M8 5.5v3M8 10.6v.01"/></svg>
<svg class="g" data-g="filex" viewBox="0 0 16 16" aria-hidden="true"><path d="M4 2h5.5L12.5 5v9h-8.5zM9.5 2v3h3M6.5 8.5l3 3M9.5 8.5l-3 3"/></svg>
<svg class="g" data-g="doc" viewBox="0 0 16 16" aria-hidden="true"><path d="M4 2h5.5L12.5 5v9h-8.5zM9.5 2v3h3M6 8.5h4M6 11h4"/></svg>
<svg class="g" data-g="read" viewBox="0 0 16 16" aria-hidden="true"><path d="M2 8s2.2-4.5 6-4.5S14 8 14 8s-2.2 4.5-6 4.5S2 8 2 8z"/><circle cx="8" cy="8" r="1.8"/></svg>
<svg class="g" data-g="checks" viewBox="0 0 16 16" aria-hidden="true"><path d="M2 5.5l2 2 3.5-4M2 11.5l2 2 3.5-4M10 5.5h4M10 11.5h4"/></svg>
<svg class="g" data-g="erp" viewBox="0 0 16 16" aria-hidden="true"><rect x="2.5" y="2.5" width="11" height="11" rx="2"/><path d="M2.5 6.5h11M6.5 6.5v7"/></svg>
<svg class="g" data-g="arrow" viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8h9.5M9 4.5L12.5 8 9 11.5"/></svg>
<svg class="g" data-g="left" viewBox="0 0 16 16" aria-hidden="true"><path d="M10 3.5L5.5 8l4.5 4.5"/></svg>
<svg class="g" data-g="right" viewBox="0 0 16 16" aria-hidden="true"><path d="M6 3.5L10.5 8 6 12.5"/></svg>
<svg class="g" data-g="minus" viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 8h9"/></svg>
<svg class="g" data-g="plus" viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 8h9M8 3.5v9"/></svg>
<svg class="g" data-g="close" viewBox="0 0 16 16" aria-hidden="true"><path d="M4.5 4.5l7 7M11.5 4.5l-7 7"/></svg>
<svg class="g" data-g="help" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6"/><path d="M6.3 6.3a1.8 1.8 0 1 1 2.5 1.7c-.5.2-.8.6-.8 1.1v.4M8 11.3v.01"/></svg>
<svg class="g sm arrow" data-g="up" viewBox="0 0 16 16" aria-hidden="true"><path d="M4.5 10L8 6.5l3.5 3.5"/></svg>
<svg class="g sm arrow" data-g="down" viewBox="0 0 16 16" aria-hidden="true"><path d="M4.5 6.5L8 10l3.5-3.5"/></svg>
</template>
<header class="bar" id="top"></header>
<main id="main"></main>
<div class="dialog" id="help" hidden role="dialog" aria-label="Help"></div>
<div class="printfoot" id="printfoot"></div>
<script type="application/json" id="data">__DATA__</script>
<script>
(function(){
"use strict";
var D = JSON.parse(document.getElementById("data").textContent);
var ORDERS = D.orders, HELP = D.reason_help;
var BYID = {}; ORDERS.forEach(function(o){ BYID[o.id] = o; });
var ROUTE_LABEL = {auto:"Written to ERP", review:"Needs check", ignored:"Not an order"};
var ROUTE_TIP = {auto:"Every value was proven, so the order is in the ERP import file.",
  review:"A check failed, so nothing was written. It waits for you.", ignored:"Invoice, quote or newsletter. Nothing was checked."};
var ROUTE_RANK = {review:0, auto:1, ignored:2};
var RES_LABEL = {proven:"Proven", failed:"Check", not_checked:"Not checked"};
var DEFAULT_FILTER = D.review ? "review" : "all";
var ZOOMS = [0.5, 0.67, 0.8, 1, 1.25, 1.5, 2, 3];
var STEP = {email:"Email", pdf:"PDF", classify:"Sort", extract:"Read", extract2:"Read 2", gate:"Check", gates:"Check", check:"Problem", route:"Result"};
var S = {filter:DEFAULT_FILTER, reason:"", q:"", sort:"", dir:1, order:null, tab:"fields", m:"fields",
         page:{}, zoom:null, focusQ:null, scrollQ:0, cur:null};

/* ---------- browser-only memory (may be missing: private window, blocked storage) ---------- */
var KEY = "po-intake:" + D.run_id;
function load(k, dflt){ try { var v = window.localStorage.getItem(KEY + ":" + k); return v === null ? dflt : JSON.parse(v); } catch (e) { return dflt; } }
function save(k, v){ try { window.localStorage.setItem(KEY + ":" + k, JSON.stringify(v)); return true; } catch (e) { return false; } }
var MINE = load("mine", {}) || {};
var GUIDE = load("guide", true) !== false;
var HINT = load("hint", true) !== false;

/* ---------- tiny DOM helpers (all text goes through textContent) ---------- */
function h(tag, attrs){
  var e = document.createElement(tag), i, k, v;
  if (attrs) for (k in attrs) { v = attrs[k];
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") e.className = v;
    else if (k === "text") e.textContent = v;
    else if (k.slice(0,2) === "on") e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? "" : v); }
  for (i = 2; i < arguments.length; i++) add(e, arguments[i]);
  return e;
}
function add(e, c){
  if (c === null || c === undefined || c === false) return;
  if (Array.isArray(c)) { c.forEach(function(x){ add(e, x); }); return; }
  e.appendChild(c instanceof Node ? c : document.createTextNode(String(c)));
}
function glyph(name){ var t = document.getElementById("glyphs").content.querySelector('[data-g="' + name + '"]') || document.getElementById("glyphs").content.querySelector('[data-g="review"]'); return t.cloneNode(true); }
function lab(c){ return (HELP[c] || {}).label || "Problem"; }
function prob(c, where){ return h("span", {class:"prob", title:(HELP[c] || {}).why || null}, glyph((HELP[c] || {}).icon), lab(c), where ? h("span", {class:"where", text:"· " + where}) : null); }
function pill(route){ return h("span", {class:"pill " + route, title:ROUTE_TIP[route]}, glyph(route), ROUTE_LABEL[route] || route); }
function dot(route){ return h("span", {class:"dot " + route, title: ROUTE_LABEL[route] + ". " + ROUTE_TIP[route]}, h("span", {class:"sr", text:ROUTE_LABEL[route]})); }
function result(r, pin){
  if (r === "failed" && pin) return h("span", {class:"res failed", title:"Needs your check"}, h("span", {class:"n-pin", "aria-hidden":"true", text:pin}), RES_LABEL[r]);
  return h("span", {class:"res " + r, title: r === "proven" ? "Found on the PDF and matched the master data" : r === "not_checked" ? "Not printed, or not part of the checks here" : "Needs your check"}, glyph(r), RES_LABEL[r]);
}
function kbd(t){ return h("kbd", {text:t}); }
function money(x){ return x === null || x === undefined ? null : "$" + x.toFixed(x < 0.01 && x > 0 ? 4 : 2); }
function secs(s){ s = +s || 0; if (s < 60) return s.toFixed(1) + " s"; var m = Math.floor(Math.round(s) / 60), r = Math.round(s) % 60; if (m >= 60) return Math.floor(m / 60) + "h " + (m % 60) + "m"; return m + "m " + (r < 10 ? "0" : "") + r + "s"; }
function plural(n, one, many){ return n + " " + (n === 1 ? one : (many || one + "s")); }
function typing(e){ var t = e.target; return t && (t.tagName === "INPUT" || t.tagName === "SELECT" || t.tagName === "TEXTAREA"); }
function cap(s){ s = String(s || ""); return s.charAt(0).toUpperCase() + s.slice(1); }
function poText(po){ return /^P\.?O\b/i.test(po) ? po : "PO " + po; }
function docType(o){ return String(o.classify.doc_type || "not a purchase order").replace(/_/g, " "); }
function whereOf(f, long){
  if (/^Line /.test(f.where)) return long ? f.where + " · " + f.subject : f.where.toLowerCase();
  return f.where === "Whole order" ? null : cap(f.subject);
}
function groups(o){       /* one card per problem: the same check found twice (model and code scan) is one card */
  var G = [], seen = {};
  o.findings.forEach(function(f){ var k = f.code + "|" + f.target;
    if (seen[k]) { seen[k].also.push(f); return; }
    var g = {f:f, also:[]}; seen[k] = g; G.push(g); });
  G.forEach(function(g, i){ g.pin = i + 1; });
  return G;
}

/* ---------- hash state ---------- */
function readHash(){
  var p = new URLSearchParams(location.hash.slice(1));
  S.filter = ["all","review","auto","ignored"].indexOf(p.get("filter")) >= 0 ? p.get("filter") : DEFAULT_FILTER;
  S.reason = HELP[p.get("problem")] ? p.get("problem") : "";
  S.q = p.get("q") || "";
  var so = (p.get("sort") || "").split("-");
  S.sort = so[0] || ""; S.dir = so[1] === "desc" ? -1 : 1;
  S.order = BYID[p.get("order")] ? p.get("order") : null;
  if (["fields","audit","csv"].indexOf(p.get("tab")) >= 0) S.tab = p.get("tab");
}
function hashFor(order){
  var p = new URLSearchParams();
  if (order) p.set("order", order);
  if (S.filter !== DEFAULT_FILTER) p.set("filter", S.filter);
  if (S.reason) p.set("problem", S.reason);
  if (S.q) p.set("q", S.q);
  if (S.sort) p.set("sort", S.sort + (S.dir < 0 ? "-desc" : ""));
  if (order && S.tab !== "fields") p.set("tab", S.tab);
  var s = p.toString();
  return s ? "#" + s : "#";
}
function replaceHash(){ history.replaceState(null, "", hashFor(S.order)); footer(); }

/* ---------- top bar ---------- */
function topbar(){
  var t = document.getElementById("top");
  t.textContent = "";
  add(t, [h("span", {class:"brand"}, h("span", {class:"mk"}, glyph("auto")), "PO intake"),
    h("span", {class:"run", text:"Run " + D.run_id})]);
  if (D.demo) add(t, h("span", {class:"demo", title:"Built with a fake model on demo documents. These numbers are not results."}, "Demo data, fake model"));
  add(t, h("span", {class:"grow"}));
  add(t, h("span", {class:"meta", title: plural(D.model_calls, "model call")}, D.models.length ? D.models.join(", ") : "model not reported"));
  add(t, h("button", {class:"btn ghost noprint", type:"button", "aria-keyshortcuts":"?", title:"How it works and shortcuts (?)", onclick: toggleHelp}, glyph("help"), h("span", {class:"opt"}, "Help")));
}

/* ---------- queue ---------- */
function visible(){
  var q = S.q.trim().toLowerCase();
  var L = ORDERS.filter(function(o){
    if (S.filter !== "all" && o.route !== S.filter) return false;
    if (S.reason && o.codes.indexOf(S.reason) < 0) return false;
    if (q) { var hay = [o.id, o.po, o.customer, o.customer_id, o.sender, o.subject, o.source_file, o.codes.map(lab).join(" ")].join(" ").toLowerCase();
      if (hay.indexOf(q) < 0) return false; }
    return true;
  });
  var key = {order:function(o){ return (o.customer || o.sender || "~").toLowerCase(); },
    what:function(o){ return o.codes.length ? lab(o.codes[0]) : "~"; }, lines:function(o){ return o.lines_n == null ? -1 : o.lines_n; },
    total:function(o){ return o.total_num == null ? -1 : o.total_num; }}[S.sort];
  L.sort(function(a, b){
    if (key) { var x = key(a), y = key(b); if (x < y) return -S.dir; if (x > y) return S.dir; }
    return (ROUTE_RANK[a.route] - ROUTE_RANK[b.route]) || (a.index - b.index);
  });
  return L;
}
function count(route){ return ORDERS.filter(function(o){ return route === "all" || o.route === route; }).length; }
function firstToCheck(){ var L = ORDERS.filter(function(o){ return o.route === "review"; }); return L.filter(function(o){ return !(MINE[o.id] || {}).checked; })[0] || L[0] || null; }

function flow(){
  return h("section", {class:"flow noprint", "aria-label":"How it works"},
    h("ol", null,
      h("li", null, h("span", {class:"ic"}, glyph("doc")), "PDF arrives"), h("span", {class:"to", "aria-hidden":"true"}, glyph("arrow")),
      h("li", null, h("span", {class:"ic"}, glyph("read")), "Claude reads it"), h("span", {class:"to", "aria-hidden":"true"}, glyph("arrow")),
      h("li", null, h("span", {class:"ic"}, glyph("checks")), "Code checks every value"), h("span", {class:"to", "aria-hidden":"true"}, glyph("arrow")),
      h("li", {class:"ok"}, h("span", {class:"ic"}, glyph("auto")), "Proven: written"),
      h("span", {class:"or", text:"or"}),
      h("li", {class:"you"}, h("span", {class:"ic"}, glyph("review")), "Doubtful: waits for you")),
    h("button", {class:"btn ghost sm", type:"button", onclick:toggleHelp}, "Learn more"),
    h("button", {class:"btn ghost icon", type:"button", "aria-label":"Hide this", title:"Hide this", onclick:function(){ GUIDE = false; save("guide", false); var g = document.querySelector(".flow"); if (g) g.remove(); }}, glyph("close")));
}
function head(){
  var first = firstToCheck(), n = D.review;
  var done = ORDERS.filter(function(o){ return o.route === "review" && (MINE[o.id] || {}).checked; }).length;
  var title = n ? h("h1", null, h("span", {class:"n", text:n}), " " + (n === 1 ? "order needs" : "orders need") + " your check")
                : h("h1", {class:"calm"}, D.documents ? "Nothing needs your check" : "No orders in this run");
  var wrong = !D.scored ? h("dd", {class:"none", text:"not scored"}) :
    h("dd", {class: D.wrong_values > 0 ? "bad" : null}, String(D.wrong_values), D.values_written != null ? h("small", {text:"of " + D.values_written.toLocaleString("en-US")}) : null);
  var cost = D.cost === null ? h("dd", {class:"none", text:"not reported"}) : h("dd", {text:money(D.cost)});
  return h("section", {class:"head", "aria-label":"Run summary"},
    h("div", null, title,
      first ? h("div", {class:"cta noprint"},
        h("button", {class:"btn primary", type:"button", id:"start", onclick:function(){ S.filter = "review"; open(first.id); }},
          done ? "Review next order" : "Review first order", glyph("arrow")),
        h("span", {class:"kh"}, "or press ", kbd("Enter"))) : null),
    h("dl", {class:"stats"},
      h("div", {title: D.scored ? "Values written to the ERP file that differ from the answer key" : "No score file for this run"}, h("dt", {text:"Wrong values written"}), wrong),
      h("div", {title: D.cost_note_full || D.cost_note}, h("dt", {text:"API-equivalent cost"}), cost),
      h("div", {title: plural(D.model_calls, "model call") + ", time summed"}, h("dt", {text:"Model time"}), h("dd", {text:secs(D.model_seconds)}))));
}
function dist(){
  var segs = [["review","Need check"],["auto","Written to ERP"],["ignored","Not an order"]];
  return h("div", {class:"dist", role:"group", "aria-label":"Show orders"},
    segs.map(function(s){ var n = count(s[0]); if (!n) return null;
      return h("button", {type:"button", class:s[0], style:"--n:" + n, title: ROUTE_TIP[s[0]], "aria-pressed": S.filter === s[0] ? "true" : "false",
        onclick:function(){ S.filter = S.filter === s[0] ? "all" : s[0]; replaceHash(); renderQueue(); }},
        h("span", {class:"b"}), h("span", {class:"l"}, h("b", {text:n}), s[1])); }),
    h("button", {type:"button", class:"all", "aria-pressed": S.filter === "all" ? "true" : "false", onclick:function(){ S.filter = "all"; replaceHash(); renderQueue(); }},
      h("span", {class:"b"}), h("span", {class:"l"}, h("b", {text:D.documents}), "All")));
}
function renderQueue(){
  var main = document.getElementById("main");
  main.textContent = "";
  var page = h("div", {class:"page"});
  add(main, page);
  if (GUIDE) add(page, flow());
  add(page, head());
  add(page, dist());
  var codes = {}; ORDERS.forEach(function(o){ o.codes.forEach(function(c){ codes[c] = (codes[c] || 0) + 1; }); });
  var sel = h("select", {id:"reason", "aria-label":"Problem", onchange:function(){ S.reason = this.value; replaceHash(); renderQueue(); }},
    h("option", {value:"", text:"All problems"}),
    Object.keys(codes).sort(function(a, b){ return lab(a) < lab(b) ? -1 : 1; }).map(function(c){ return h("option", {value:c, text: lab(c) + " (" + codes[c] + ")"}); }));
  sel.value = S.reason;
  var search = h("input", {type:"search", id:"search", placeholder:"Search customer or PO", "aria-label":"Search", value:S.q,
    "aria-keyshortcuts":"/", oninput:function(){ S.q = this.value; replaceHash(); fillRows(); }});
  add(page, h("div", {class:"tools"}, h("span", {class:"count", id:"shown"}), h("span", {class:"grow"}), sel, search));
  add(page, h("div", {class:"list"}, h("table", {id:"queue", "aria-label":"Orders"}, thead(), h("tbody", {id:"rows"}))));
  add(page, h("div", {class:"lfoot"}, h("span", {id:"notes"}), h("span", {class:"c-opt"}, "Press ", kbd("?"), " for shortcuts")));
  fillRows();
  notesLink();
}
function thead(){
  var cols = [["","",""],["order","Customer",""],["what","Problem","c-opt"],["lines","Lines","num c-opt w-n"],["total","Total","num w-tot"],["","",""]];
  return h("thead", null, h("tr", null, cols.map(function(c){
    if (!c[0]) return h("th", {class:c[2]}, h("span", {class:"sr", text: c === cols[0] ? "Status" : "Open"}));
    var on = S.sort === c[0];
    return h("th", {class:c[2], scope:"col", "aria-sort": on ? (S.dir > 0 ? "ascending" : "descending") : null},
      h("button", {type:"button", onclick:function(){ if (S.sort === c[0]) { if (S.dir > 0) S.dir = -1; else { S.sort = ""; S.dir = 1; } } else { S.sort = c[0]; S.dir = 1; } replaceHash(); renderQueue(); }},
        c[1], glyph(on && S.dir < 0 ? "down" : "up")));
  })));
}
function probCell(o){
  if (o.route === "review") {
    var G = groups(o), f = G[0].f;
    return h("span", {class:"probs", title: f.plain}, prob(f.code, whereOf(f)), G.length > 1 ? [" ", h("span", {class:"more", text:"+" + (G.length - 1)})] : null);
  }
  if (o.route === "auto") return h("span", {class:"calm"}, glyph("auto"), plural(o.proven, "check") + " passed");
  return h("span", {class:"calm ign"}, glyph("ignored"), cap(docType(o)));
}
function fillRows(){
  var tb = document.getElementById("rows"); if (!tb) return;
  tb.textContent = "";
  var L = visible();
  if (!ORDERS.length) add(tb, h("tr", {class:"empty"}, h("td", {colspan:"6"}, h("div", {class:"e"}, h("span", {class:"ic"}, glyph("doc")),
    h("span", null, h("b", {text:"No emails in this run"}), h("span", {class:"muted", text:"Run the pipeline on an inbox folder, then build this page again."}))))));
  else if (!L.length) {
    var clean = S.filter === "review" && !S.q && !S.reason;
    add(tb, h("tr", {class:"empty"}, h("td", {colspan:"6"}, h("div", {class:"e"}, h("span", {class:"ic"}, glyph(clean ? "auto" : "search")),
      h("span", null, h("b", {text: clean ? "All clear" : "No orders match"}),
        clean ? h("span", {class:"muted", text:"Every order was proven and written, or was not an order."}) :
          h("button", {class:"link", type:"button", onclick:function(){ S.filter = "all"; S.reason = ""; S.q = ""; replaceHash(); renderQueue(); }}, "Show all orders"))))));
  }
  L.forEach(function(o){
    var who = o.customer || o.sender;
    var tr = h("tr", {tabindex:"-1", "data-id":o.id, "aria-selected": S.focusQ === o.id ? "true" : "false",
        onclick:function(){ open(o.id); }, onfocus:function(){ markQ(o.id); }},
      h("td", {class:"st"}, dot(o.route)),
      h("td", null, h("div", {class:"who", title:who}, who, (MINE[o.id] || {}).checked ? h("span", {class:"tag mine", text:"Checked"}) : null),
        h("div", {class:"po", text: o.po ? poText(o.po) : (o.route === "ignored" ? "No PO" : "PO not read")}),
        h("div", {class:"m-prob"}, probCell(o))),
      h("td", {class:"c-opt"}, probCell(o)),
      h("td", {class:"num c-opt", text: o.lines_n == null ? "—" : o.lines_n}),
      h("td", {class:"num"}, o.total ? [o.total, o.currency ? h("span", {class:"cur", text:o.currency}) : null] : h("span", {class:"muted", text:"—"})),
      h("td", {class:"go", "aria-hidden":"true"}, glyph("right")));
    add(tb, tr);
  });
  var rows = tb.querySelectorAll("tr[data-id]");
  if (rows.length) { var f = tb.querySelector('tr[aria-selected="true"]') || rows[0]; f.tabIndex = 0; }
  var sh = document.getElementById("shown");
  if (sh) sh.textContent = (S.filter === "all" && !S.q && !S.reason) ? plural(L.length, "order") : L.length + " of " + ORDERS.length;
}
function markQ(id){
  S.focusQ = id;
  Array.prototype.forEach.call(document.querySelectorAll("#rows tr[data-id]"), function(r){
    var on = r.getAttribute("data-id") === id; r.setAttribute("aria-selected", on ? "true" : "false"); r.tabIndex = on ? 0 : -1; });
}
function moveQ(d){
  var rows = Array.prototype.slice.call(document.querySelectorAll("#rows tr[data-id]"));
  if (!rows.length) return;
  var i = rows.findIndex(function(r){ return r.getAttribute("data-id") === S.focusQ; });
  i = i < 0 ? 0 : Math.max(0, Math.min(rows.length - 1, i + d));
  rows[i].focus(); markQ(rows[i].getAttribute("data-id"));
}

/* ---------- reviewer notes: this browser only, exported as a file on request ---------- */
function notesLink(){
  var el = document.getElementById("notes"); if (!el) return;
  el.textContent = "";
  var n = Object.keys(MINE).filter(function(k){ return BYID[k] && (MINE[k].checked || MINE[k].note); }).length;
  if (!n) return;
  add(el, [plural(n, "order") + " marked in this browser · ",
    h("button", {class:"link noprint", type:"button", onclick:exportNotes}, "Download notes (CSV)")]);
}
function cell(v){ v = String(v == null ? "" : v); if (/^[=+\-@\t\r]/.test(v)) v = "'" + v; return '"' + v.replace(/"/g, '""') + '"'; }
function exportNotes(){
  var rows = [["run","document","po_number","customer","status","problems","checked","checked_at","note"]];
  ORDERS.forEach(function(o){ var m = MINE[o.id]; if (!m || !(m.checked || m.note)) return;
    rows.push([D.run_id, o.id, o.po || "", o.customer || o.sender, ROUTE_LABEL[o.route], o.codes.map(lab).join("; "), m.checked ? "yes" : "no", m.at || "", m.note || ""]); });
  var blob = new Blob([rows.map(function(r){ return r.map(cell).join(","); }).join("\r\n") + "\r\n"], {type:"text/csv"});
  var a = h("a", {download: "review-notes-" + D.run_id + ".csv"});
  a.href = URL.createObjectURL(blob); document.body.appendChild(a); a.click();
  setTimeout(function(){ URL.revokeObjectURL(a.href); a.remove(); }, 0);
}
function setMine(id, patch){
  var m = MINE[id] || {}; for (var k in patch) m[k] = patch[k];
  if (patch.checked !== undefined) m.at = patch.checked ? new Date().toISOString().slice(0, 16).replace("T", " ") : "";
  MINE[id] = m; return save("mine", MINE);
}

/* ---------- detail ---------- */
function open(id){ S.scrollQ = window.scrollY; S.focusQ = id; S.fromQueue = true; location.hash = hashFor(id); }
function back(){ if (S.fromQueue) { S.fromQueue = false; history.back(); } else { S.order = null; location.hash = hashFor(null); } }
function pinsFor(o){
  var p = {}; o.groups = groups(o);
  o.groups.forEach(function(g){ (g.f.targets || [g.f.target]).forEach(function(k){ if (!p[k]) p[k] = g.pin; }); });
  return p;
}
function renderDetail(){
  var o = BYID[S.order], main = document.getElementById("main");
  main.textContent = "";
  var L = visible(), pos = L.findIndex(function(x){ return x.id === o.id; });
  var inFilter = pos >= 0;
  if (pos < 0) { L = ORDERS.slice().sort(function(a, b){ return (ROUTE_RANK[a.route] - ROUTE_RANK[b.route]) || (a.index - b.index); }); pos = L.indexOf(o); }
  var prev = pos > 0 ? L[pos - 1] : null, next = pos < L.length - 1 ? L[pos + 1] : null;
  S.cur = null;
  o.pins = pinsFor(o);
  if (!S.page[o.id]) S.page[o.id] = firstPinPage(o) || 1;
  var group = !inFilter || S.filter === "all" ? "" : " " + ROUTE_LABEL[S.filter].toLowerCase();
  var head = h("div", {class:"dhead"},
    h("button", {class:"btn ghost icon noprint", type:"button", onclick:back, title:"Back to orders (Esc)", "aria-label":"Back to orders"}, glyph("left")),
    h("div", {class:"t"},
      h("h1", null, h("span", {text: o.customer || (o.route === "ignored" ? o.sender : o.source_file || o.id)}),
        o.po ? h("span", {class:"po", text:poText(o.po)}) : null, pill(o.route)),
      h("div", {class:"sub", title: "From " + (o.sender || "unknown sender")}, h("span", {class:"file", text:o.source_file || "No PDF"}),
        o.pages.length ? " · " + plural(o.pages.length, "page") : null,
        o.route === "ignored" ? null : (o.mode === "text" ? " · text PDF" : o.mode === "scan" ? " · scan, read twice" : null))),
    h("div", {class:"nav noprint"},
      h("span", {class:"pos", text: (pos + 1) + " of " + L.length + group}),
      h("button", {class:"btn icon", type:"button", title:"Previous order (p)", "aria-label":"Previous order", disabled: !prev, onclick:function(){ if (prev) go(prev.id); }}, glyph("left")),
      h("button", {class:"btn icon", type:"button", title:"Next order (n)", "aria-label":"Next order", disabled: !next, onclick:function(){ if (next) go(next.id); }}, glyph("right"))));
  var det = h("div", {class:"detail", "data-m": S.m});
  var mt = h("div", {class:"mtabs noprint", role:"group", "aria-label":"Show"},
    [["fields", o.route === "review" ? "Problems" : "Details"],["doc","PDF"]].map(function(t){
      return h("button", {type:"button", "aria-pressed": S.m === t[0] ? "true" : "false", onclick:function(){ setM(t[0]); }}, t[1]);
    }));
  var docpane = h("section", {class:"docpane", "aria-label":"The PDF"});
  var splitter = h("div", {class:"splitter", role:"separator", tabindex:"0", "aria-orientation":"vertical", "aria-label":"Resize panes",
    "aria-valuemin":"30", "aria-valuemax":"75", "aria-valuenow": parseInt(getComputedStyle(document.documentElement).getPropertyValue("--split")) || 56});
  var side = h("div", {class:"side", id:"side"});
  add(det, [head, mt, h("div", {class:"split"}, docpane, splitter, side)]);
  add(main, det);
  buildDoc(o, docpane);
  buildSide(o, side);
  wireSplitter(splitter);
  footer();
}
function setM(m){
  S.m = m; var det = document.querySelector(".detail"); if (det) det.setAttribute("data-m", m);
  Array.prototype.forEach.call(document.querySelectorAll(".mtabs button"), function(b, i){ b.setAttribute("aria-pressed", (i === 0) === (m === "fields") ? "true" : "false"); });
  if (m === "doc") layoutPage();
}
function go(id){ S.focusQ = id; history.replaceState(null, "", hashFor(id)); S.order = id; renderDetail(); document.getElementById("side").scrollTop = 0; }
function firstPinPage(o){ for (var i = 0; i < o.boxes.length; i++) if (o.boxes[i].st === "failed") return o.boxes[i].p; return null; }

/* document pane */
function buildDoc(o, pane){
  pane.textContent = "";
  var n = o.pages.length, cur = S.page[o.id];
  var failedBoxes = o.boxes.some(function(b){ return b.st === "failed"; });
  var bar = h("div", {class:"dbar"},
    h("span", {class:"pg", id:"pageof", text: n ? "Page " + cur + " of " + n : "No pages"}),
    n > 1 ? h("button", {class:"btn icon", type:"button", "aria-label":"Previous page", disabled: cur <= 1, onclick:function(){ setPage(o, cur - 1); }}, glyph("left")) : null,
    n > 1 ? h("button", {class:"btn icon", type:"button", "aria-label":"Next page", disabled: cur >= n, onclick:function(){ setPage(o, cur + 1); }}, glyph("right")) : null,
    h("span", {class:"grow"}),
    o.boxes.length ? [failedBoxes ? h("span", {class:"key", title:"A value that needs your check"}, h("i", {class:"k-acc"}), "Problem") : null,
      h("span", {class:"key", title:"Where a proven value was found"}, h("i", {class:"k-ok"}), "Proven")] :
      (o.route !== "ignored" && n ? h("span", {class:"key", text: o.mode === "scan" ? "Scan: no text to box" : "No boxes"}) : null),
    h("button", {class:"btn icon ghost", type:"button", "aria-label":"Zoom out", title:"Zoom out (-)", onclick:function(){ zoom(-1); }}, glyph("minus")),
    h("span", {class:"zoom", id:"zoomv"}),
    h("button", {class:"btn icon ghost", type:"button", "aria-label":"Zoom in", title:"Zoom in (+)", onclick:function(){ zoom(1); }}, glyph("plus")),
    h("button", {class:"btn ghost", type:"button", title:"Fit width (0)", onclick:function(){ S.zoom = null; layoutPage(); }}, "Fit"));
  var hint = HINT && o.boxes.length ? h("div", {class:"hint noprint"},
    h("span", {class:"grow", text: failedBoxes ? "Numbered boxes are the problems. Hover a field to find it on the page." : "Hover a field to find it on the page."}),
    h("button", {class:"btn ghost icon", type:"button", "aria-label":"Hide tip", onclick:function(){ HINT = false; save("hint", false); this.parentNode.remove(); layoutPage(); }}, glyph("close"))) : null;
  var canvas = h("div", {class:"canvas", id:"canvas", tabindex:"-1"});
  add(pane, [bar, hint, canvas]);
  if (!n) { add(canvas, h("div", {class:"nodoc", text:"This email had no PDF attachment."})); return; }
  var pg = o.pages[cur - 1];
  var sheet = h("div", {class:"sheet", id:"sheet"}, h("img", {src: pg.src, alt: "Page " + cur + " of " + (o.source_file || "the document"), width: pg.w, height: pg.h, draggable:"false"}));
  var pinned = {};
  o.boxes.forEach(function(b, i){
    if (b.p !== cur) return;
    var pin = b.st === "failed" ? (o.pins[b.k] || o.pins[b.r]) : null;
    var el = h("div", {class:"box " + b.st, "data-k": b.k, "data-r": b.r, "data-i": i, title: b.label + ": " + (b.value || ""),
      style: "left:" + (b.x * 100) + "%;top:" + (b.y * 100) + "%;width:" + (b.w * 100) + "%;height:" + (b.h * 100) + "%",
      onmouseenter:function(){ light(b.r, b.k, true); }, onmouseleave:function(){ unlight(); },
      onclick:function(){ focusField(b.r, true); }},
      pin && !pinned[pin] ? h("span", {class:"n-pin", "aria-hidden":"true", text:pin}) : null);
    if (pin) pinned[pin] = true;
    add(sheet, el);
  });
  add(canvas, sheet);
  canvas.addEventListener("wheel", function(e){ if (e.ctrlKey) { e.preventDefault(); zoom(e.deltaY < 0 ? 1 : -1); } }, {passive:false});
  layoutPage();
}
function setPage(o, n){ if (n < 1 || n > o.pages.length) return; S.page[o.id] = n; buildDoc(o, document.querySelector(".docpane")); if (S.cur) light(S.cur, null, false); }
function layoutPage(){
  var o = BYID[S.order], sheet = document.getElementById("sheet"), canvas = document.getElementById("canvas"), zv = document.getElementById("zoomv");
  if (!o || !sheet || !canvas || !o.pages.length) return;
  var pg = o.pages[S.page[o.id] - 1], w;
  if (S.zoom === null) w = Math.max(200, Math.min(canvas.clientWidth - 50, 980));
  else w = pg.w * S.zoom;
  sheet.style.width = Math.round(w) + "px";
  if (zv) zv.textContent = Math.round(100 * w / pg.w) + "%";
}
function zoom(d){
  var o = BYID[S.order]; if (!o || !o.pages.length) return;
  var pg = o.pages[S.page[o.id] - 1], sheet = document.getElementById("sheet");
  var now = S.zoom === null ? sheet.getBoundingClientRect().width / pg.w : S.zoom, i;
  if (d > 0) { for (i = 0; i < ZOOMS.length && ZOOMS[i] <= now + 0.001; i++); S.zoom = ZOOMS[Math.min(i, ZOOMS.length - 1)]; }
  else { for (i = ZOOMS.length - 1; i >= 0 && ZOOMS[i] >= now - 0.001; i--); S.zoom = ZOOMS[Math.max(i, 0)]; }
  layoutPage();
}

/* highlight: field <-> box */
function boxesFor(row, key){
  return Array.prototype.filter.call(document.querySelectorAll("#sheet .box"), function(b){
    return key ? b.getAttribute("data-k") === key : b.getAttribute("data-r") === row; });
}
function light(row, key, pop){
  unlight(true);
  Array.prototype.forEach.call(document.querySelectorAll('#side [data-key="' + row + '"]'), function(r){ r.classList.add("hl"); });
  var bs = boxesFor(row, key); if (!bs.length) bs = boxesFor(row, null);
  bs.forEach(function(b){ b.classList.add("on"); });
  if (pop && bs.length) showPop(bs[0]);
}
function unlight(keepCur){
  Array.prototype.forEach.call(document.querySelectorAll(".hl"), function(e){ e.classList.remove("hl"); });
  Array.prototype.forEach.call(document.querySelectorAll("#sheet .box.on"), function(b){ b.classList.remove("on"); });
  hidePop();
  if (!keepCur && S.cur) boxesFor(S.cur, null).forEach(function(b){ b.classList.add("on"); });
}
function showPop(box){
  hidePop();
  var o = BYID[S.order], b = o.boxes[+box.getAttribute("data-i")], sheet = document.getElementById("sheet");
  var pop = h("div", {class:"pop", id:"pop", role:"tooltip"},
    h("div", {class:"v", text: b.value || "—"}),
    h("div", {class:"l"}, h("span", {text: b.label}), result(b.st)));
  add(sheet, pop);
  var top = box.offsetTop + box.offsetHeight + 8;
  if (top + pop.offsetHeight > sheet.clientHeight) top = Math.max(0, box.offsetTop - pop.offsetHeight - 8);
  pop.style.top = top + "px";
  pop.style.left = Math.max(0, Math.min(box.offsetLeft, sheet.clientWidth - pop.offsetWidth)) + "px";
}
function hidePop(){ var p = document.getElementById("pop"); if (p) p.remove(); }
function scrollBoxIntoView(row, ping){
  var bs = boxesFor(row, null), canvas = document.getElementById("canvas");
  if (!bs.length || !canvas) return false;
  var b = bs[0].getBoundingClientRect(), c = canvas.getBoundingClientRect();
  if (b.top < c.top + 8 || b.bottom > c.bottom - 8) canvas.scrollTop += (b.top - c.top) - c.height / 3;
  if (b.left < c.left || b.right > c.right) canvas.scrollLeft += (b.left - c.left) - 24;
  if (ping) {
    var pb = typeof ping === "string" ? boxesFor(null, ping) : bs.filter(function(x){ return x.classList.contains("failed"); });
    (pb.length ? pb : bs).forEach(function(x){ x.classList.remove("ping"); void x.offsetWidth; x.classList.add("ping"); }); }
  return true;
}
function boxOf(o, f){
  var keys = f.targets || [f.target], b = null;
  o.boxes.some(function(x){ if (keys.indexOf(x.k) >= 0) { b = x; return true; } return false; });
  if (!b) o.boxes.some(function(x){ if (keys.indexOf(x.r) >= 0 && x.st === "failed") { b = x; return true; } return false; });
  return b;
}
function showOnPage(o, f){
  var b = boxOf(o, f); if (!b) return;
  if (window.innerWidth < 1100) setM("doc");
  if (b.p !== S.page[o.id]) { S.page[o.id] = b.p; buildDoc(o, document.querySelector(".docpane")); }
  setCur(b.r, b.k);
  unlight(); light(b.r, b.k, true);
}

/* side pane: problems, your mark, then fields / history / ERP file */
function buildSide(o, side){
  side.textContent = "";
  add(side, verdict(o));
  var tabs = [["fields","Fields"],["audit","History"],["csv","ERP file"]];
  var tl = h("div", {class:"tabs noprint", role:"tablist"}, tabs.map(function(t){
    return h("button", {type:"button", role:"tab", id:"tab-" + t[0], "aria-selected": S.tab === t[0] ? "true" : "false", "aria-controls":"panel-" + t[0],
      tabindex: S.tab === t[0] ? "0" : "-1", onclick:function(){ setTab(t[0]); },
      onkeydown:function(e){ if (e.key === "ArrowRight" || e.key === "ArrowLeft") { var i = tabs.findIndex(function(x){ return x[0] === S.tab; });
        i = (i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length; setTab(tabs[i][0]); document.getElementById("tab-" + tabs[i][0]).focus(); e.preventDefault(); } }},
      t[1], t[0] === "fields" && o.header.length ? h("span", {class:"c", text: o.counts.proven + "/" + (o.counts.proven + o.counts.failed)}) : null);
  }));
  add(side, [tl, fieldsPanel(o), auditPanel(o), csvPanel(o)]);
  setTab(S.tab);
}
function cmpLabels(code){ return (HELP[code] || {}).cmp || ["On PDF", "Expected", null]; }
function numOf(s){ var t = String(s == null ? "" : s).replace(/[,$\s]/g, ""); return /^-?\d+(\.\d+)?$/.test(t) ? parseFloat(t) : null; }
function tidy(s, like){
  var v = numOf(s); if (v === null) return String(s);
  var dec = /^-?\d+\.\d{3,}$/.test(String(s)) ? 2 : ((String(s).split(".")[1] || "").length);
  return /,/.test(String(like || "")) ? v.toLocaleString("en-US", {minimumFractionDigits:dec, maximumFractionDigits:dec}) : v.toFixed(dec);
}
function diffBadge(code, a, b){
  var x = numOf(a), y = numOf(b); if (x === null || y === null || y === 0 || x === y) return null;
  if (cmpLabels(code)[2] === "pct") { var p = 100 * (x - y) / Math.abs(y); return (p > 0 ? "+" : "−") + Math.abs(p).toFixed(1) + "%"; }
  if (cmpLabels(code)[2] !== "abs") return null;
  var d = x - y; return (d > 0 ? "+" : "−") + Math.abs(d).toFixed(2);
}
function issueCard(o, g){
  var f = g.f, hp = HELP[f.code] || {label:"Problem", icon:"filex", todo:"", why:""}, lb = cmpLabels(f.code);
  var hasBox = !!boxOf(o, f);
  var body = [];
  if (hp.quote && f.read) body.push(h("div", {class:"quote", title:f.read, text:"“" + f.read + "”"}));
  else if (f.read && f.expected) {
    var d = diffBadge(f.code, f.read, f.expected);
    body.push(h("div", {class:"cmp"},
      h("div", {class:"v read"}, h("span", {class:"k", text:lb[0]}), h("span", {class:"x", text:f.read})),
      h("span", {class:"ar", "aria-hidden":"true"}, glyph("arrow")),
      h("div", {class:"v"}, h("span", {class:"k", text:lb[1]}), h("span", {class:"x", text:tidy(f.expected, f.read)})),
      d ? h("span", {class:"d", title:"Difference", text:d}) : null));
  } else if (f.read || f.note) {
    var dup = /\(([^)]+)\)\s*$/.exec(f.note || ""), earlier = dup && BYID[dup[1]];
    body.push(h("p", {class:"fact"}, f.read ? h("b", {text: f.read === "partly_unclear" ? "Partly unclear" : f.read}) : null,
      f.read && f.note ? " · " : null, f.note ? (earlier ? f.note.replace(/\s*\([^)]*\)\s*$/, "") : f.note) : null,
      earlier ? [" · ", h("a", {href: "#order=" + encodeURIComponent(earlier.id), text:"Open earlier order"})] : null));
  }
  var why = h("p", {class:"why", hidden:true}, hp.why + " ", h("span", {text: f.plain}));
  return h("li", {class:"issue", "data-key": f.target},
    h("div", {class:"ih"}, h("span", {class:"n-pin", text:g.pin, "aria-hidden":"true"}),
      prob(f.code, whereOf(f, true)), h("span", {class:"grow"})),
    body,
    h("p", {class:"act"}, glyph("arrow"), hp.todo),
    h("div", {class:"ifoot noprint"},
      hasBox ? h("button", {class:"link", type:"button", onclick:function(){ showOnPage(o, f); }}, "Show on PDF") :
        h("button", {class:"link", type:"button", onclick:function(){ focusField(f.target, true); }}, "Show field"),
      h("button", {class:"link", type:"button", "aria-expanded":"false", onclick:function(){ why.hidden = !why.hidden; this.setAttribute("aria-expanded", why.hidden ? "false" : "true"); }}, "Why?")),
    why);
}
function verdict(o){
  var sec = h("section", {class:"verdict", "aria-label":"Result"});
  if (o.route === "review") {
    var G = o.groups;
    add(sec, h("h2", {text: plural(G.length, "problem") + " to check"}));
    add(sec, h("ol", {class:"issues"}, G.map(function(g){ return issueCard(o, g); })));
    var m = MINE[o.id] || {};
    var note = h("textarea", {"aria-label":"Your note", placeholder:"Note for the order desk", maxlength:"500", hidden: m.note ? null : true,
      oninput:function(){ setMine(o.id, {note:this.value}); }, text: m.note || ""});
    var msg = h("span", {class:"note", text:"Notes stay in this browser"});
    add(sec, h("div", {class:"mine"},
      h("label", null, h("input", {type:"checkbox", checked: m.checked ? true : null, onchange:function(){ if (!setMine(o.id, {checked:this.checked})) msg.textContent = "This browser cannot save; the mark is lost on close"; }}), "Mark as checked"),
      msg, h("span", {class:"grow"}),
      m.note ? null : h("button", {class:"link noprint", type:"button", onclick:function(){ note.hidden = false; note.focus(); this.remove(); }}, "Add note"),
      note));
  } else if (o.route === "auto") {
    add(sec, h("div", {class:"allclear"}, h("span", {class:"ic"}, glyph("auto")),
      h("div", null, h("b", {text:"Nothing to check"}), h("span", {text: plural(o.proven, "check") + " passed · written to " + (o.csv ? o.csv.file : "the ERP file")}))));
  } else {
    add(sec, h("div", {class:"allclear ign"}, h("span", {class:"ic"}, glyph("ignored")),
      h("div", null, h("b", {text:"Not a purchase order"}), h("span", {text: cap(docType(o)) + " · nothing checked or written"}))));
  }
  return sec;
}
function setTab(t){
  var changed = S.tab !== t;
  S.tab = t;
  if (changed && S.order) replaceHash();
  ["fields","audit","csv"].forEach(function(x){
    var b = document.getElementById("tab-" + x), p = document.getElementById("panel-" + x);
    if (b) { b.setAttribute("aria-selected", x === t ? "true" : "false"); b.tabIndex = x === t ? 0 : -1; }
    if (p) p.hidden = x !== t;
  });
}
function evidence(page, quote, hasBox){
  if (!page && !quote) return null;
  return h("div", {class:"ev"}, "Page " + (page || "?") + (hasBox ? "" : ", place not marked") + (quote ? ": “" + quote + "”" : ""));
}
function compareLine(o, key){
  var f = o.findings.filter(function(x){ return (x.targets || [x.target]).indexOf(key) >= 0; })[0];
  if (!f) return null;
  var lb = cmpLabels(f.code);
  if (f.read && f.expected) return h("div", {class:"cmpline", text: lab(f.code) + ": " + f.read + " → " + lb[1].toLowerCase() + " " + tidy(f.expected, f.read)});
  return h("div", {class:"cmpline", text: lab(f.code) + (f.note ? ": " + f.note : "")});
}
function frow(o, f, isCheck){
  var pin = f.result === "failed" ? o.pins[f.key] : null;
  var val = f.value === null || f.value === undefined ? h("span", {class:"muted", text:"—"}) : h("span", {text: f.value});
  return h("div", {class:"frow " + f.result, tabindex:"-1", "data-key":f.key, "data-failed": f.result === "failed" ? "1" : null,
      onmouseenter:function(){ light(f.key, null, true); }, onmouseleave:function(){ unlight(); },
      onfocus:function(){ setCur(f.key); }, onclick:function(){ focusField(f.key, false); }},
    h("div", {class:"lab", text:f.label}),
    h("div", {class:"val"}, val, f.matched ? h("span", {class:"id", text: f.matched === "on file" ? "on file" : "→ " + f.matched}) : null),
    h("div", {class:"rcol"}, result(f.result, pin)),
    h("div", {class:"ex"}, f.result === "failed" ? compareLine(o, f.key) : null, isCheck ? null : evidence(f.page, f.quote, f.boxes)));
}
function fieldsPanel(o){
  var p = h("section", {id:"panel-fields", role:"tabpanel", "aria-labelledby":"tab-fields"});
  if (o.route === "ignored") { add(p, h("div", {class:"note-p", text:"No fields were read."})); return p; }
  if (!o.header.length) { add(p, h("div", {class:"note-p", text:"No fields: the model output could not be used."})); return p; }
  var rows = o.checks.concat(o.header);
  var bad = rows.filter(function(f){ return f.result === "failed"; }), ok = rows.filter(function(f){ return f.result === "proven"; }),
      nc = rows.filter(function(f){ return f.result === "not_checked"; });
  if (bad.length) { add(p, h("div", {class:"sect"}, h("h3", {text:"Needs your check"}))); bad.forEach(function(f){ add(p, frow(o, f, f.key.slice(0, 2) === "c:")); }); }
  add(p, h("div", {class:"sect"}, h("h3", {text:"Proven"}), h("span", {class:"res proven", text: ok.length + " of " + (ok.length + bad.length)})));
  ok.forEach(function(f){ add(p, frow(o, f, f.key.slice(0, 2) === "c:")); });
  if (nc.length) add(p, h("div", {class:"nc", title:"Not printed on this document, or not part of the checks for it"}, "Not checked: " + nc.map(function(f){ return f.label; }).join(", ")));
  if (!o.lines.length) { add(p, h("div", {class:"note-p", text:"No order lines."})); return p; }
  var okL = o.lines.filter(function(l){ return l.result === "proven"; }).length;
  add(p, h("div", {class:"sect"}, h("h3", {text:"Order lines"}), h("span", {class:"res " + (okL === o.lines.length ? "proven" : "failed"), text: okL + " of " + o.lines.length + " proven"})));
  var cols = [["#","num"],["Item",""],["Description",""],["Qty","num"],["Unit",""],["Price","num"],["Total","num"],["",""]];
  var tb = h("tbody");
  o.lines.forEach(function(l){
    var c = l.cells;
    function td(name, cls){
      var x = c[name], badc = x.result === "failed";
      return h("td", {class:(cls || "") + (badc ? " bad" : ""), title: x.value ? null : "not printed",
        onmouseenter:function(){ light(l.key, l.key + ":" + name, true); }},
        x.value === null ? h("span", {class:"muted", text:"—"}) : x.value);
    }
    var pin = l.result === "failed" ? o.pins[l.key] : null;
    add(tb, h("tr", {class:"lrow " + l.result, tabindex:"-1", "data-key":l.key, "data-failed": l.result === "failed" ? "1" : null,
        onmouseenter:function(){ light(l.key, null, true); }, onmouseleave:function(){ unlight(); },
        onfocus:function(){ setCur(l.key); }, onclick:function(){ focusField(l.key, false); }},
      h("td", {class:"num muted", text:l.n}), td("item"), td("description", "trunc"), td("qty", "num"), td("uom"),
      td("unit_price", "num"), td("line_total", "num"), h("td", null, result(l.result, pin))));
    var first = c.item.value ? c.item : c.qty;
    var cmps = Object.keys(c).map(function(k){ return c[k].result === "failed" ? compareLine(o, l.key + ":" + k) : null; }).filter(Boolean);
    add(tb, h("tr", {class:"lmore" + (l.result === "failed" ? " show" : ""), "data-key":l.key},
      h("td", {colspan:"8"}, cmps.length ? cmps : null, evidence(first.page, first.quote, first.boxes))));
  });
  add(p, h("div", {class:"ltable"}, h("table", null, h("thead", null, h("tr", null, cols.map(function(c){ return h("th", {class:c[1], scope:"col", text:c[0]}); }))), tb)));
  return p;
}
function auditPanel(o){
  var p = h("section", {id:"panel-audit", role:"tabpanel", "aria-labelledby":"tab-audit"});
  add(p, h("div", {class:"sect printonly"}, h("h3", {text:"History"})));
  add(p, h("ol", {class:"audit"}, o.audit.map(function(a){
    return h("li", null, h("span", {class:"sx", text: STEP[a.step] || cap(a.step)}), h("span", {class:"tx", text:a.text}));
  })));
  return p;
}
function csvPanel(o){
  var p = h("section", {id:"panel-csv", role:"tabpanel", "aria-labelledby":"tab-csv"});
  add(p, h("div", {class:"sect printonly"}, h("h3", {text:"ERP file"})));
  if (!o.csv) {
    add(p, h("div", {class:"note-p", text: o.route === "ignored" ? "No ERP file: not a purchase order." :
      o.route === "review" ? "Not written. Enter this order by hand after your check." : "No ERP file found for this order."}));
    return p;
  }
  add(p, h("div", {class:"sect"}, h("h3", null, h("span", {class:"file", text:"erp_import/" + o.csv.file})),
    h("span", {class:"muted", text: plural(o.csv.rows.length, "row") + " · " + o.csv.head.length + " columns"})));
  var head = h("tr", null, h("th", {scope:"col", text:"Column"}), o.csv.rows.map(function(r, i){ return h("th", {scope:"col", text:"Row " + (i + 1)}); }));
  add(p, h("div", {class:"csvt"}, h("table", null, h("thead", null, head),
    h("tbody", null, o.csv.head.map(function(col, j){
      return h("tr", null, h("td", {text:col}), o.csv.rows.map(function(r){ return h("td", {text: r[j]}); }));
    })))));
  add(p, h("div", {class:"sect"}, h("h3", {text:"File content"})));
  add(p, h("pre", {class:"raw", text:o.csv.text}));
  return p;
}

/* field focus */
function fieldRows(){ return Array.prototype.slice.call(document.querySelectorAll("#panel-fields .frow, #panel-fields tr.lrow")); }
function setCur(key, ping){
  S.cur = key;
  Array.prototype.forEach.call(document.querySelectorAll("#panel-fields .cur"), function(e){ e.classList.remove("cur"); });
  Array.prototype.forEach.call(document.querySelectorAll('#panel-fields [data-key="' + key + '"]'), function(e){ e.classList.add("cur"); });
  fieldRows().forEach(function(r){ r.tabIndex = r.getAttribute("data-key") === key ? 0 : -1; });
  var o = BYID[S.order], b = o.boxes.filter(function(x){ return x.r === key; })[0];
  if (b && b.p !== S.page[o.id]) { S.page[o.id] = b.p; buildDoc(o, document.querySelector(".docpane")); }
  unlight();
  scrollBoxIntoView(key, ping);
}
function focusField(key, fromOutside){
  if (S.tab !== "fields") setTab("fields");
  if (fromOutside && window.innerWidth < 1100 && S.m !== "fields") setM("fields");
  var row = document.querySelector('#panel-fields [data-key="' + key + '"]');
  if (!row) return;
  row.focus({preventScroll:true});
  row.scrollIntoView({block:"center"});
  setCur(key, fromOutside);
}
function moveField(d){
  var rows = fieldRows(); if (!rows.length) return;
  if (S.tab !== "fields") setTab("fields");
  var i = rows.findIndex(function(r){ return r.getAttribute("data-key") === S.cur; });
  i = i < 0 ? (d > 0 ? 0 : rows.length - 1) : Math.max(0, Math.min(rows.length - 1, i + d));
  focusField(rows[i].getAttribute("data-key"), false);
}
function nextFailed(){
  var rows = fieldRows().filter(function(r){ return r.getAttribute("data-failed"); });
  if (!rows.length) return;
  var all = fieldRows(), i = all.findIndex(function(r){ return r.getAttribute("data-key") === S.cur; });
  var nxt = rows.filter(function(r){ return all.indexOf(r) > i; })[0] || rows[0];
  focusField(nxt.getAttribute("data-key"), true);
}

/* splitter */
function wireSplitter(sp){
  function set(v){ v = Math.max(30, Math.min(75, v)); document.documentElement.style.setProperty("--split", v + "%"); sp.setAttribute("aria-valuenow", Math.round(v)); layoutPage(); }
  sp.addEventListener("pointerdown", function(e){
    var box = sp.parentNode.getBoundingClientRect(); sp.setPointerCapture(e.pointerId);
    function mv(ev){ set(100 * (ev.clientX - box.left) / box.width); }
    function up(){ sp.removeEventListener("pointermove", mv); sp.removeEventListener("pointerup", up); }
    sp.addEventListener("pointermove", mv); sp.addEventListener("pointerup", up);
  });
  sp.addEventListener("keydown", function(e){
    var v = +sp.getAttribute("aria-valuenow");
    if (e.key === "ArrowLeft") { set(v - 5); e.preventDefault(); }
    if (e.key === "ArrowRight") { set(v + 5); e.preventDefault(); }
  });
}

/* help: the longer explanation lives here, not on the page */
function toggleHelp(){
  var hb = document.getElementById("help");
  if (!hb.hidden) { hb.hidden = true; return; }
  hb.textContent = "";
  var keys = [["Enter", "Open; next problem"], ["j / k", "Next / previous row"], ["n / p", "Next / previous order"],
    ["Esc", "Back"], ["/", "Search"], ["+ / - / 0", "Zoom, fit"], ["?", "This panel"]];
  add(hb, [h("div", {class:"dh"}, h("h2", {text:"How it works"}),
      h("button", {class:"btn ghost icon", type:"button", "aria-label":"Close", onclick:toggleHelp}, glyph("close"))),
    h("ul", null,
      h("li", null, glyph("read"), h("b", {text:"Claude reads each emailed PDF"}), h("span", {class:"w", text:"Every value, with the page and words it came from."})),
      h("li", null, glyph("checks"), h("b", {text:"Code checks every value"}), h("span", {class:"w", text:"Against the PDF text, price list and master data. The model does not decide."})),
      h("li", null, glyph("auto"), h("b", {text:"Proven orders are written"}), h("span", {class:"w", text:"Only orders where every check passed go to the ERP import file."})),
      h("li", null, glyph("review"), h("b", {text:"The rest wait for you"}), h("span", {class:"w", text:"Nothing here is sent anywhere. Marks and notes stay in this browser."}))),
    h("h3", {text:"Problems"}),
    h("ul", null, Object.keys(HELP).map(function(c){ var x = HELP[c];
      return h("li", null, glyph(x.icon), h("b", {text:x.label}), h("span", {class:"w", text:x.why})); })),
    h("h3", {text:"Keys"}),
    h("dl", null, keys.map(function(k){ return [h("dt", null, kbd(k[0])), h("dd", {text:k[1]})]; }))]);
  hb.hidden = false;
}

/* keys */
document.addEventListener("keydown", function(e){
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  var hb = document.getElementById("help");
  if (e.key === "Escape") {
    if (!hb.hidden) { hb.hidden = true; return; }
    if (typing(e)) { e.target.blur(); if (!S.order) moveQ(0); return; }
    if (document.getElementById("pop")) { hidePop(); return; }
    if (S.order) back();
    return;
  }
  if (typing(e)) return;
  if (e.key === "?") { toggleHelp(); e.preventDefault(); return; }
  var onBtn = e.target && (e.target.tagName === "BUTTON" || e.target.tagName === "A" || e.target.tagName === "SUMMARY");
  if (!S.order) {
    if (e.key === "j" || e.key === "ArrowDown") { moveQ(1); e.preventDefault(); }
    else if (e.key === "k" || e.key === "ArrowUp") { moveQ(-1); e.preventDefault(); }
    else if ((e.key === "Enter" && !onBtn) || e.key === "o") {
      var row = S.focusQ && document.querySelector('#rows tr[data-id="' + S.focusQ + '"]');
      if (row && document.activeElement === row) { open(S.focusQ); e.preventDefault(); }
      else { var f = firstToCheck(); if (f) { S.filter = "review"; open(f.id); e.preventDefault(); } else moveQ(0); } }
    else if (e.key === "/") { var s = document.getElementById("search"); if (s) { s.focus(); e.preventDefault(); } }
    return;
  }
  if (e.target && e.target.getAttribute && e.target.getAttribute("role") === "separator") return;
  if (e.key === "j" || e.key === "ArrowDown") { moveField(1); e.preventDefault(); }
  else if (e.key === "k" || e.key === "ArrowUp") { moveField(-1); e.preventDefault(); }
  else if (e.key === "Enter" && !onBtn) { nextFailed(); e.preventDefault(); }
  else if (e.key === "n" || e.key === "p") {
    var L = visible(), i = L.findIndex(function(x){ return x.id === S.order; }), t = L[i + (e.key === "n" ? 1 : -1)];
    if (t) go(t.id); e.preventDefault();
  }
  else if (e.key === "+" || e.key === "=") zoom(1);
  else if (e.key === "-") zoom(-1);
  else if (e.key === "0") { S.zoom = null; layoutPage(); }
});
window.addEventListener("resize", function(){ if (S.order) layoutPage(); });

function footer(){
  document.getElementById("printfoot").textContent = "Run " + D.run_id + (D.demo ? " (demo data, fake model)" : "") + " · " + (location.hash || "#");
}
function route(){
  readHash();
  document.getElementById("help").hidden = true;
  if (S.order) { renderDetail(); window.scrollTo(0, 0); }
  else {
    renderQueue();
    window.scrollTo(0, S.scrollQ || 0);
    var row = S.focusQ && document.querySelector('#rows tr[data-id="' + S.focusQ + '"]');
    if (row) { markQ(S.focusQ); row.focus({preventScroll:true}); }
  }
  footer();
}
window.addEventListener("hashchange", route);
topbar();
route();
})();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
