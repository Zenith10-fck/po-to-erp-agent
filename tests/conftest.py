"""Shared fixtures: a tiny master data set, a tiny text PDF and a matching 'model answer'.

These tests use a fake model. They prove the code, not how a real model performs.
"""
from __future__ import annotations

import copy
import csv
import sys
from email.message import EmailMessage
from pathlib import Path

import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from po_agent.masterdata import MasterData  # noqa: E402

MASTER = {
    "customers.csv": [
        ["customer_id", "name", "aliases", "bill_to_id", "bill_to_address", "currency", "price_list_id", "active"],
        ["C0001", "Harlow Fastener Supply Inc.", "Harlow Fastener", "B0001", "410 Mill Road, Dayton, OH 45402", "USD", "PL-A", "Y"],
        ["C0002", "Kessler Machine Works", "", "B0002", "9 Lake St, Akron, OH 44301", "USD", "PL-A", "Y"],
        ["C0003", "Kessler Machine Works East", "", "B0003", "77 Pine Ave, Canton, OH 44702", "USD", "PL-A", "Y"],
    ],
    "ship_tos.csv": [
        ["ship_to_id", "customer_id", "name", "address"],
        ["S0001", "C0001", "Harlow Plant 2", "88 Foundry St, Springfield, OH 45503"],
        ["S0002", "C0001", "Harlow Main", "410 Mill Road, Dayton, OH 45402"],
        ["S0003", "C0002", "Kessler Dock", "9 Lake St, Akron, OH 44301"],
    ],
    "items.csv": [
        ["item_id", "description", "base_uom", "legacy_item_no", "active"],
        ["IT-10442", "Hex bolt M8 x 40 zinc", "EA", "OLD-442", "Y"],
        ["IT-10500", "Flat washer M8", "EA", "", "Y"],
        ["IT-10999", "Discontinued nut", "EA", "", "N"],
    ],
    "customer_parts.csv": [
        ["customer_id", "customer_part_no", "item_id"],
        ["C0001", "HF-2291", "IT-10442"],
    ],
    "uom_conversions.csv": [
        ["item_id", "from_uom", "factor"],
        ["IT-10442", "CS", "12"],
    ],
    "uom_aliases.csv": [
        ["alias", "uom"],
        ["case", "CS"], ["cs", "CS"], ["each", "EA"], ["ea", "EA"],
    ],
    "price_lists.csv": [
        ["price_list_id", "item_id", "uom", "unit_price"],
        ["PL-A", "IT-10442", "EA", "7.20"],
        ["PL-A", "IT-10500", "EA", "0.15"],
    ],
    "carrier_accounts.csv": [
        ["customer_id", "carrier", "account_no"],
        ["C0001", "UPS", "A1B2C3"],
    ],
}


@pytest.fixture
def master_dir(tmp_path) -> Path:
    folder = tmp_path / "master"
    folder.mkdir()
    for name, rows in MASTER.items():
        with (folder / name).open("w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerows(rows)
    return folder


@pytest.fixture
def md(master_dir) -> MasterData:
    return MasterData.load(master_dir)


def make_pdf(path: Path, extra_lines: list[tuple[str, tuple]] | None = None, po_number="PO-48213",
             price="86.40", total="432.00", order_total="447.00") -> Path:
    """One-page text PO. Line 1: 5 CS of IT-10442. Line 2: 100 EA of IT-10500."""
    c = canvas.Canvas(str(path), pagesize=letter)
    c.setFont("Helvetica", 10)
    y = 740
    for text in ["Harlow Fastener Supply Inc.", "410 Mill Road, Dayton, OH 45402",
                 f"Purchase Order No. {po_number}", "Date: 10/02/2026",
                 "To: Northfield Industrial Supply, 1200 Commerce Pkwy, Columbus, OH 43215",
                 "Ship To: Harlow Plant 2", "88 Foundry St, Springfield, OH 45503",
                 "Ship collect, UPS acct A1B2C3", "Notes: Dock 3, call before delivery"]:
        c.drawString(60, y, text)
        y -= 16
    y -= 10
    cols = [60, 150, 330, 380, 430, 500]
    for x, t in zip(cols, ["Item No", "Description", "Qty", "U/M", "Price", "Amount"]):
        c.drawString(x, y, t)
    rows = [("IT-10442", "Hex bolt M8 x 40 zinc", "5", "CS", price, total),
            ("IT-10500", "Flat washer M8", "100", "EA", "0.15", "15.00")]
    for row in rows:
        y -= 18
        for x, t in zip(cols, row):
            c.drawString(x, y, t)
    y -= 26
    c.drawString(430, y, f"Total {order_total}")
    for text, pos in extra_lines or []:
        c.drawString(pos[0], pos[1], text)
    c.save()
    return path


def fld(value, quote=None, page=1):
    if value is None:
        return {"value": None, "page": None, "quote": None}
    return {"value": value, "page": page, "quote": quote or value}


def good_extraction() -> dict:
    return {
        "legibility": "clear", "po_pages": [1], "ignored_pages": [],
        "suspicious_content": {"present": False, "page": None, "quote": None},
        "po_number": fld("PO-48213"), "po_date": fld("10/02/2026"),
        "customer_name": fld("Harlow Fastener Supply Inc."),
        "bill_to_name": fld("Harlow Fastener Supply Inc."),
        "bill_to_address": fld("410 Mill Road, Dayton, OH 45402"),
        "ship_to_name": fld("Harlow Plant 2"),
        "ship_to_address": fld("88 Foundry St, Springfield, OH 45503"),
        "currency": fld(None), "order_total": fld("447.00"),
        "carrier_name": fld("UPS"), "carrier_account_no": fld("A1B2C3"),
        "shipping_notes": fld("Dock 3, call before delivery"),
        "lines": [
            {"line_no": fld(None), "item_no": fld("IT-10442"), "customer_part_no": fld(None),
             "description": fld("Hex bolt M8 x 40 zinc"), "qty": fld("5"), "uom": fld("CS"),
             "unit_price": fld("86.40"), "line_total": fld("432.00"), "requested_date": fld(None)},
            {"line_no": fld(None), "item_no": fld("IT-10500"), "customer_part_no": fld(None),
             "description": fld("Flat washer M8"), "qty": fld("100"), "uom": fld("EA"),
             "unit_price": fld("0.15"), "line_total": fld("15.00"), "requested_date": fld(None)},
        ],
    }


@pytest.fixture
def extraction() -> dict:
    return copy.deepcopy(good_extraction())


def make_eml(path: Path, pdf: Path | None, subject="PO attached") -> Path:
    msg = EmailMessage()
    msg["From"] = "purchasing@harlow.example"
    msg["To"] = "orders@northfield.example"
    msg["Subject"] = subject
    msg.set_content("Please see the attached purchase order.")
    if pdf is not None:
        msg.add_attachment(pdf.read_bytes(), maintype="application", subtype="pdf", filename=pdf.name)
    path.write_bytes(msg.as_bytes())
    return path
