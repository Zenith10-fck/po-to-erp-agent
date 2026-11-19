"""Intake: reads `.eml` files from a folder and pulls out the email text and PDF attachments.

A real mailbox (IMAP, Microsoft 365 / Graph) would feed the same `Mail` objects. Not built here.
"""
from __future__ import annotations

from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from pathlib import Path


@dataclass
class Mail:
    doc_id: str
    sender: str
    subject: str
    body: str
    attachments: list[tuple[str, bytes]]   # (file name, PDF bytes)


def read_eml(path: Path) -> Mail:
    with path.open("rb") as f:
        msg = BytesParser(policy=policy.default).parse(f)
    body_part = msg.get_body(preferencelist=("plain", "html"))
    body = body_part.get_content() if body_part else ""
    pdfs = []
    for part in msg.iter_attachments():
        name = part.get_filename() or "attachment"
        if part.get_content_type() == "application/pdf" or name.lower().endswith(".pdf"):
            pdfs.append((name, part.get_payload(decode=True)))
    return Mail(doc_id=path.stem, sender=str(msg.get("From", "")), subject=str(msg.get("Subject", "")),
                body=body.strip()[:4000], attachments=pdfs)


def read_inbox(folder: Path) -> list[Mail]:
    """All emails in a folder, in file-name order (the order they 'arrived').

    Each PDF attachment becomes its own document, so a second PO in the same email is never
    dropped. The first keeps the email's name; the next ones get '-att2', '-att3' ..."""
    out: list[Mail] = []
    for p in sorted(folder.glob("*.eml")):
        mail = read_eml(p)
        if len(mail.attachments) <= 1:
            out.append(mail)
            continue
        for i, att in enumerate(mail.attachments, start=1):
            out.append(Mail(doc_id=mail.doc_id if i == 1 else f"{mail.doc_id}-att{i}", sender=mail.sender,
                            subject=mail.subject, body=mail.body, attachments=[att]))
    return out
