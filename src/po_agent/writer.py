"""Writes the ERP import CSV (docs/csv-spec.md) and the review package."""
from __future__ import annotations

import io
import json
import os
import re
import shutil
from decimal import Decimal
from pathlib import Path

from .gates.master_data import Matched
from .normalize import fmt_decimal, fmt_qty

COLUMNS = [
    "customer_id", "customer_po_number", "po_date", "bill_to_id", "ship_to_id", "currency",
    "line_no", "item_id", "customer_part_no", "order_qty", "order_uom", "base_qty", "base_uom",
    "unit_price", "line_total", "requested_date", "carrier_account_no", "shipping_notes",
    "source_file", "run_id",
]
NUMERIC = {"line_no", "order_qty", "base_qty", "unit_price", "line_total"}


def csv_name(customer_id: str, po_number: str) -> str:
    return f"{customer_id}_{re.sub(r'[^A-Za-z0-9_-]', '_', po_number)}.csv"


def build_rows(m: Matched, source_file: str, run_id: str) -> list[dict]:
    rows = []
    for ln in m.lines:
        total = (ln.order_qty * ln.unit_price).quantize(Decimal("0.01"))
        rows.append({
            "customer_id": m.customer_id, "customer_po_number": m.po_number, "po_date": m.po_date,
            "bill_to_id": m.bill_to_id, "ship_to_id": m.ship_to_id, "currency": m.currency,
            "line_no": str(ln.line_no), "item_id": ln.item_id, "customer_part_no": ln.customer_part_no,
            "order_qty": fmt_qty(ln.order_qty), "order_uom": ln.order_uom,
            "base_qty": fmt_qty(ln.base_qty), "base_uom": ln.base_uom,
            "unit_price": fmt_decimal(ln.unit_price, 4), "line_total": fmt_decimal(total, 2),
            "requested_date": ln.requested_date, "carrier_account_no": m.carrier_account_no,
            "shipping_notes": m.shipping_notes, "source_file": source_file, "run_id": run_id,
        })
    return rows


def render_csv(rows: list[dict]) -> str:
    def cell(col, v):
        v = "" if v is None else str(v)
        return v if col in NUMERIC else '"' + v.replace('"', '""') + '"'

    buf = io.StringIO()
    buf.write(",".join(f'"{c}"' for c in COLUMNS) + "\r\n")
    for r in rows:
        buf.write(",".join(cell(c, r[c]) for c in COLUMNS) + "\r\n")
    return buf.getvalue()


def write_csv(folder: Path, name: str, rows: list[dict]) -> Path:
    """Write to a .tmp file, then rename: a watched folder never sees half a file.
    Never overwrites: the caller has already checked for duplicates."""
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / name
    if target.exists():
        raise FileExistsError(target)
    tmp = folder / (name + ".tmp")
    tmp.write_text(render_csv(rows), encoding="utf-8", newline="")
    os.replace(tmp, target)
    return target


def write_review(folder: Path, doc_id: str, pdf: Path, record: dict) -> Path:
    """review/<doc_id>/: the PDF and one JSON with what was read, every failed check and why."""
    target = folder / doc_id
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(pdf, target / pdf.name)
    (target / "review.json").write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    return target
