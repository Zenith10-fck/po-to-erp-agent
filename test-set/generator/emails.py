"""Writes the .eml files of the test set (stdlib `email` only).

Every sender domain ends in `.example` (RFC 2606), so no real company is named or mailed.
Headers are fixed (Date, Message-ID), so the same scenario always gives the same file.
"""
from __future__ import annotations

import datetime as dt
import pathlib
from email.message import EmailMessage
from email.utils import format_datetime


def build_message(email: dict, doc_id: str, pdf_bytes: bytes) -> EmailMessage:
    """email: from, to, subject, body, date (ISO string), attachment (file name)."""
    msg = EmailMessage()
    msg["From"] = email["from"]
    msg["To"] = email["to"]
    msg["Subject"] = email["subject"]
    msg["Date"] = format_datetime(dt.datetime.fromisoformat(email["date"]))
    msg["Message-ID"] = f"<{doc_id}@mail.northfield-supply.example>"
    msg.set_content(email["body"] + "\n")
    msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename=email["attachment"])
    return msg


def write_eml(path: pathlib.Path, email: dict, doc_id: str, pdf_bytes: bytes) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(build_message(email, doc_id, pdf_bytes).as_bytes())
    return path
