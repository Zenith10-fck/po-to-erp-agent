"""Helpers to build answer-key JSON (see SPEC.md, "Answer key").

The answer key is built from how a scenario was constructed. No gate code is run here.
Values in `truth` use the ERP CSV format (docs/csv-spec.md): dates YYYY-MM-DD, unit price with
4 decimals, line total with 2 decimals, quantities without useless zeros.
"""
from __future__ import annotations

import json
import pathlib
from decimal import Decimal

CATEGORIES = ["clean", "layout", "scan", "handwritten", "multipage", "trap", "injection", "non_po"]
ROUTES = ["auto", "review", "ignored"]
SCAN_REVIEW_OK = ["R09", "R11"]


def fmt_qty(value: Decimal | int) -> str:
    """5 not 5.00; 2.5 stays 2.5 (same rule as the writer)."""
    value = Decimal(value)
    if value == value.to_integral_value():
        return str(int(value))
    return format(value.normalize(), "f")


def fmt_price(value: Decimal) -> str:
    return str(Decimal(value).quantize(Decimal("0.0001")))


def fmt_total(value: Decimal) -> str:
    return str(Decimal(value).quantize(Decimal("0.01")))


def truth_line(line_no: int, item_id: str | None, customer_part_no: str | None, order_qty,
               order_uom: str | None, factor: int | None, base_uom: str | None,
               unit_price: Decimal | None, requested_date: str | None) -> dict:
    """One expected CSV row (line part). Unknown values are None."""
    base_qty = None
    if factor is not None and order_qty is not None:
        base_qty = fmt_qty(Decimal(order_qty) * factor)
    total = None
    if unit_price is not None and order_qty is not None:
        total = fmt_total(Decimal(order_qty) * unit_price)
    return {
        "line_no": line_no,
        "item_id": item_id,
        "customer_part_no": customer_part_no or "",
        "order_qty": fmt_qty(order_qty) if order_qty is not None else None,
        "order_uom": order_uom,
        "base_qty": base_qty,
        "base_uom": base_uom,
        "unit_price": fmt_price(unit_price) if unit_price is not None else None,
        "line_total": total,
        "requested_date": requested_date or "",
    }


def make_truth(customer_id: str | None, po_number: str | None, po_date: str | None,
               bill_to_id: str | None, ship_to_id: str | None, currency: str | None,
               lines: list[dict], carrier_account_no: str | None, shipping_notes: str | None) -> dict:
    return {
        "customer_id": customer_id,
        "customer_po_number": po_number,
        "po_date": po_date or "",
        "bill_to_id": bill_to_id,
        "ship_to_id": ship_to_id,
        "currency": currency,
        "lines": lines,
        "carrier_account_no": carrier_account_no or "",
        "shipping_notes": " ".join((shipping_notes or "").split()),
    }


def make_key(doc_id: str, split: str, category: str, is_po: bool, trap: str | None,
             expected_route: str, expected_reason_codes: list[str], truth: dict | None, *,
             acceptable_extra_codes: list[str] | None = None,
             acceptable_review_codes: list[str] | None = None,
             source_file: str = "", **extra) -> dict:
    assert category in CATEGORIES, category
    assert expected_route in ROUTES, expected_route
    key = {
        "doc_id": doc_id,
        "split": split,
        "category": category,
        "is_po": is_po,
        "trap": trap,
        "expected_route": expected_route,
        "expected_reason_codes": sorted(expected_reason_codes),
        "acceptable_extra_codes": sorted(acceptable_extra_codes or []),
        "acceptable_review_codes": sorted(acceptable_review_codes or []),
        "source_file": source_file,
        "truth": truth,
    }
    key.update(extra)
    return key


def write_key(path: pathlib.Path, key: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(key, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
