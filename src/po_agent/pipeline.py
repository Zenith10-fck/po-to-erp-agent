"""The pipeline: intake -> classify -> read -> gates -> decide -> write.

Phase 1 (model calls) can run in parallel. Phase 2 (gates and writing) runs one document at a
time in arrival order, so the duplicate check is deterministic. Phase 2 uses no model at all.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

from .document import Document, load_document, render_pages
from .gates import checks, evidence
from .gates.base import Finding
from .gates.master_data import Matched, check_master_data
from .intake import Mail
from .masterdata import MasterData
from .model_client import ModelClient
from .writer import build_rows, csv_name, write_csv, write_review

ROOT = Path(__file__).resolve().parents[2]
SECOND_READ_NOTE = (
    "\n\nReading order for this pass: start with the line items. Read the item rows one by one "
    "from the last row up to the first, then read the header blocks. Return the lines in "
    "document order (top to bottom) as usual."
)


def _load_contract() -> tuple[str, str, dict, dict]:
    return (
        (ROOT / "prompts" / "classify.md").read_text(encoding="utf-8"),
        (ROOT / "prompts" / "extract.md").read_text(encoding="utf-8"),
        json.loads((ROOT / "docs" / "classify.schema.json").read_text(encoding="utf-8")),
        json.loads((ROOT / "docs" / "schema.json").read_text(encoding="utf-8")),
    )


def _file_list(doc: Document, with_text: bool) -> str:
    names = []
    for p in doc.pages:
        names.append(f"page-{p.number}.png")
        if with_text:
            names.append(f"page-{p.number}.txt")
    return ", ".join(names)


def read_document(mail: Mail, out: Path, client: ModelClient) -> dict:
    """Phase 1 for one email: classify, then one read (text PDF) or two reads (scan).
    Returns the raw record that is also saved to raw/<doc_id>.json."""
    classify_sys, extract_sys, classify_schema, extract_schema = _load_contract()
    raw = {"doc_id": mail.doc_id, "sender": mail.sender, "subject": mail.subject, "body": mail.body,
           "source_file": None, "mode": None, "pages": 0, "classify": None, "extract": None,
           "extract2": None, "calls": []}
    if not mail.attachments:
        raw["classify"] = {"doc_type": "other", "reason": "no PDF attachment"}
        return raw
    name, data = mail.attachments[0]
    doc_dir = out / "docs" / mail.doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = doc_dir / name
    pdf_path.write_bytes(data)
    doc = load_document(pdf_path)
    raw.update(source_file=name, mode="text" if doc.is_text_pdf else "scan", pages=len(doc.pages))
    render_pages(pdf_path, out / "pages" / mail.doc_id, dpi=110)   # for the report page

    work = Path(tempfile.mkdtemp(prefix="po-agent-"))
    try:
        read1 = work / "read1"
        render_pages(pdf_path, read1, dpi=150)
        if doc.is_text_pdf:
            for p in doc.pages:
                (read1 / f"page-{p.number}.txt").write_text(p.text, encoding="utf-8")

        def call(kind, folder, system, user, schema):
            res = client.ask(kind, mail.doc_id, folder, system, user, schema)
            raw["calls"].append({"kind": kind, **res.meta()})
            return res

        user = (f"Email from: {mail.sender}\nSubject: {mail.subject}\nEmail text:\n{mail.body}\n\n"
                f"Attachment: {name}. Its first page is page-1.png in the current folder.")
        res = call("classify", read1, classify_sys, user, classify_schema)
        raw["classify"] = res.output if res.ok else {"error": res.error}
        if not res.ok or res.output["doc_type"] != "purchase_order":
            return raw

        user = (f"Document: {name}, {len(doc.pages)} page(s). Files in the current folder: "
                f"{_file_list(doc, doc.is_text_pdf)}. Read every file, then return the JSON.")
        res = call("extract", read1, extract_sys, user, extract_schema)
        raw["extract"] = res.output if res.ok else {"error": res.error}
        if res.ok and not doc.is_text_pdf:
            read2 = work / "read2"
            render_pages(pdf_path, read2, dpi=220, enhance=True)
            user2 = (f"Document: {name}, {len(doc.pages)} page(s). Files in the current folder: "
                     f"{_file_list(doc, False)}. Read every file, then return the JSON.")
            res2 = call("extract2", read2, extract_sys + SECOND_READ_NOTE, user2, extract_schema)
            raw["extract2"] = res2.output if res2.ok else {"error": res2.error}
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return raw


def _failed(part) -> bool:
    return part is None or "error" in part


def decide(raw: dict, out: Path, md: MasterData, ledger: checks.Ledger, run_id: str) -> dict:
    """Phase 2 for one document. Pure code: gates, decision, files."""
    rec = {"doc_id": raw["doc_id"], "source_file": raw["source_file"], "mode": raw["mode"],
           "pages": raw["pages"], "sender": raw["sender"], "subject": raw["subject"],
           "route": None, "reason_codes": [], "findings": [], "classify": raw["classify"],
           "extraction": None, "matched": None, "csv_file": None, "calls": raw["calls"]}
    cls = raw["classify"] or {}
    findings: list[Finding] = []
    matched = Matched()

    if "error" not in cls and cls.get("doc_type") != "purchase_order":
        rec["route"] = "ignored"
        return rec

    pdf_path = out / "docs" / raw["doc_id"] / raw["source_file"]
    doc = load_document(pdf_path)
    ex = raw["extract"]
    if "error" in cls:
        findings.append(Finding("R14", "order", "classify", note=str(cls["error"])[:200]))
    elif _failed(ex):
        findings.append(Finding("R14", "order", "extract", note=str((ex or {}).get("error"))[:200]))
    elif not ex.get("lines"):
        findings.append(Finding("R14", "order", "lines", note="the model returned no order lines"))
    else:
        rec["extraction"] = ex
        findings += evidence.check_required(ex)
        if raw["mode"] == "text":
            findings += evidence.check_text_pdf(doc, ex)
        elif _failed(raw["extract2"]):
            findings.append(Finding("R14", "order", "extract2",
                                    note=str((raw["extract2"] or {}).get("error"))[:200]))
        else:
            findings += evidence.compare_reads(ex, raw["extract2"])
        findings += evidence.check_legibility(ex)
        findings += checks.check_math(ex)
        matched, md_findings = check_master_data(md, ex)
        findings += md_findings
        findings += ledger.check(matched.customer_id, matched.po_number)
    findings += checks.check_suspicious(doc, ex if not _failed(ex) else None)
    findings += checks.check_email_text(raw.get("subject") or "", raw.get("body") or "")

    # Safety net: an order can only be written if every CSV value exists. A gap without a
    # reason code would be a bug in a gate, so it is caught here instead of written.
    if not findings:
        complete = matched.customer_id and matched.ship_to_id and matched.po_number and matched.lines and all(
            ln.item_id and ln.order_qty is not None and ln.order_uom and ln.base_qty is not None
            and ln.unit_price is not None for ln in matched.lines)
        if not complete:
            findings.append(Finding("R08", "order", "completeness", note="a value needed for the CSV is missing"))

    name = None
    rows: list[dict] = []
    if not findings:
        rows = build_rows(matched, raw["source_file"], run_id)
        findings += checks.check_csv_cells(rows)
    if not findings:
        name = csv_name(matched.customer_id, matched.po_number)
        if (out / "erp_import" / name).exists():
            findings.append(Finding("R10", "order", "po_number", read=matched.po_number,
                                    note="an import file for this customer and PO number already exists"))

    rec["matched"] = json.loads(json.dumps(asdict(matched), default=str))
    rec["findings"] = [f.to_dict() for f in findings]
    rec["reason_codes"] = sorted({f.code for f in findings})
    if findings:
        rec["route"] = "review"
        write_review(out / "review", raw["doc_id"], pdf_path, rec)
    else:
        rec["route"] = "auto"
        write_csv(out / "erp_import", name, rows)
        rec["csv_file"] = name
    ledger.add(matched.customer_id, matched.po_number, raw["doc_id"], rec["route"])
    return rec


def run(mails: list[Mail], out: Path, md: MasterData, client: ModelClient, run_id: str,
        workers: int = 4, replay: bool = False, progress=None) -> dict:
    """Runs the whole inbox. With `replay`, phase 1 is loaded from raw/ and no model is called."""
    out.mkdir(parents=True, exist_ok=True)
    raw_dir = out / "raw"
    raw_dir.mkdir(exist_ok=True)
    t0 = time.time()

    def phase1(mail: Mail) -> dict:
        target = raw_dir / f"{mail.doc_id}.json"
        if replay or target.exists():
            return json.loads(target.read_text(encoding="utf-8"))
        raw = read_document(mail, out, client)
        target.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
        if progress:
            progress(raw)
        return raw

    with ThreadPoolExecutor(max_workers=workers) as pool:
        raws = list(pool.map(phase1, mails))
    read_seconds = time.time() - t0

    # phase 2 always starts clean, so a replay gives the same result as the first run
    for sub in ("erp_import", "review", "state"):
        shutil.rmtree(out / sub, ignore_errors=True)
    ledger = checks.Ledger(out / "state" / "processed.csv")
    records = [decide(raw, out, md, ledger, run_id) for raw in raws]
    with (out / "audit.jsonl").open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    calls = [c for r in records for c in r["calls"]]
    summary = {
        "run_id": run_id,
        "documents": len(records),
        "auto": sum(r["route"] == "auto" for r in records),
        "review": sum(r["route"] == "review" for r in records),
        "ignored": sum(r["route"] == "ignored" for r in records),
        "model_calls": len(calls),
        "model_seconds_total": round(sum(c["seconds"] for c in calls), 1),
        "api_equivalent_cost_usd": round(sum(c["cost_usd"] or 0 for c in calls), 4),
        "models": sorted({m for c in calls for m in c["model"]}),
        "wall_seconds_phase1": round(read_seconds, 1),
        "replayed": replay,
        "cost_note": "claude -p on a subscription: no money is charged per call; cost is what the CLI reports as API-equivalent.",
    }
    # run.json always describes what is in the folder now. On a replay the reading time comes
    # from the original run, because no model was called this time.
    previous = out / "run.json"
    if replay and previous.exists():
        old = json.loads(previous.read_text(encoding="utf-8"))
        summary["wall_seconds_phase1"] = old.get("wall_seconds_phase1")
        summary["replayed_from_run"] = old.get("run_id")
    previous.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
