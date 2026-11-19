"""Scores one live run against the answer key.

    uv run python measure.py --run test-set/runs/<batch>

A run folder is the pipeline's `--out` folder (audit.jsonl, erp_import/, review/, raw/, run.json).
The split (dev or heldout) is read from the doc ids. The score is written to
<run>/score.json. With `--publish`, a held-out score is also merged into results.json, the only
source of published numbers. Dev scores are never published.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from po_agent.gates.base import val  # noqa: E402
from po_agent.masterdata import MasterData  # noqa: E402
from po_agent.normalize import norm_code, parse_date, parse_number  # noqa: E402

CSV_COMPARE = ["customer_id", "customer_po_number", "po_date", "bill_to_id", "ship_to_id", "currency",
               "line_no", "item_id", "customer_part_no", "order_qty", "order_uom", "base_qty", "base_uom",
               "unit_price", "line_total", "requested_date", "carrier_account_no", "shipping_notes"]
NUMERIC = {"order_qty", "base_qty", "unit_price", "line_total", "line_no"}


def _eq(col: str, got: str | None, want) -> bool:
    got = "" if got is None else str(got)
    want = "" if want is None else str(want)
    if col in NUMERIC:
        try:
            return Decimal(got or "0") == Decimal(want or "0") and bool(got) == bool(want)
        except Exception:
            return False
    if col == "customer_po_number":
        return norm_code(got) == norm_code(want)
    return got.strip() == want.strip()


def truth_rows(key: dict) -> list[dict]:
    t = key.get("truth") or {}
    rows = []
    for ln in t.get("lines") or []:
        row = {c: t.get(c) for c in CSV_COMPARE if c in t}
        row.update(ln)
        rows.append(row)
    return rows


def wrong_values_in_csv(path: Path, key: dict) -> tuple[int, int, list[dict]]:
    """(wrong values, values written, details) for one written CSV file."""
    with path.open(encoding="utf-8", newline="") as f:
        got = list(csv.DictReader(f))
    want = truth_rows(key)
    wrong, written, details = 0, 0, []
    for i, row in enumerate(got):
        exp = want[i] if i < len(want) else {}
        for col in CSV_COMPARE:
            written += 1
            if not exp or not _eq(col, row.get(col), exp.get(col)):
                wrong += 1
                details.append({"line": i + 1, "column": col, "written": row.get(col),
                                "truth": exp.get(col) if exp else "(no such line)"})
    if len(got) < len(want):
        details.append({"line": None, "column": "lines", "written": len(got), "truth": len(want)})
    return wrong, written, details


def field_reads(rec: dict, key: dict, md: MasterData) -> list[tuple[str, bool]]:
    """Did the model read each value right? Compared after parsing, so format does not count."""
    ex, t = rec.get("extraction"), key.get("truth") or {}
    if not ex or not t:
        return []
    out = [("po_number", norm_code(val(ex.get("po_number"))) == norm_code(t.get("customer_po_number")))]
    if t.get("po_date"):
        d = parse_date(val(ex.get("po_date")))
        out.append(("po_date", d is not None and d.isoformat() == t["po_date"]))
    lines, want = ex.get("lines") or [], t.get("lines") or []
    out.append(("line_count", len(lines) == len(want)))
    # A planted misprint: the model should read what is PRINTED, not the correct value.
    printed = {}
    td = key.get("trap_detail") or {}
    if td.get("field") and td.get("printed") is not None and td.get("line_no"):
        printed[(int(td["line_no"]), td["field"])] = td["printed"]
    for n, (got, exp) in enumerate(zip(lines, want), start=1):
        for name, col in (("qty", "order_qty"), ("unit_price", "unit_price"), ("line_total", "line_total")):
            target = printed.get((n, name), exp.get(col))
            if target in (None, ""):
                continue
            v = parse_number(val(got.get(name)))
            out.append((name, v is not None and v == parse_number(str(target))))
        out.append(("uom", md.uom_code(val(got.get("uom"))) == exp.get("order_uom")))
        nums = {norm_code(val(got.get("item_no"))), norm_code(val(got.get("customer_part_no")))} - {""}
        out.append(("item_number", bool(nums)))
        if exp.get("requested_date"):
            d = parse_date(val(got.get("requested_date")))
            out.append(("requested_date", d is not None and d.isoformat() == exp["requested_date"]))
    return out


def score(run_dir: Path, master: Path) -> dict:
    md = MasterData.load(master)
    records = [json.loads(x) for x in (run_dir / "audit.jsonl").read_text(encoding="utf-8").splitlines() if x]
    run_meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    keys = {r["doc_id"]: json.loads((ROOT / "test-set" / "answer-key" / f"{r['doc_id']}.json").read_text(encoding="utf-8"))
            for r in records}
    splits = {k["split"] for k in keys.values()}

    per_doc, failures = [], []
    wrong_total = written_total = 0
    false_auto = 0
    route_ok = careful = false_review = 0
    reason_ok = reason_n = 0
    by_cat: dict[str, list[bool]] = defaultdict(list)
    by_field: dict[str, list[bool]] = defaultdict(list)
    cost, seconds, po_docs = 0.0, 0.0, 0

    for r in records:
        k = keys[r["doc_id"]]
        exp, got, codes = k["expected_route"], r["route"], set(r["reason_codes"])
        acceptable_review = set(k.get("acceptable_review_codes") or [])
        verdict = "ok"
        if got == exp:
            route_ok += 1
        elif exp == "auto" and got == "review" and codes and codes <= acceptable_review:
            careful += 1
            verdict = "careful_review"
        elif exp == "auto" and got == "review":
            false_review += 1
            verdict = "false_review"
        elif got == "auto":
            false_auto += 1
            verdict = "false_auto"
        else:
            verdict = "wrong_route"

        if exp == "review" and got == "review":
            reason_n += 1
            want = set(k.get("expected_reason_codes") or [])
            allowed = want | set(k.get("acceptable_extra_codes") or [])
            ok = want <= codes and codes <= allowed
            reason_ok += ok
            if not ok:
                verdict = "wrong_reason"

        wrong = written = 0
        details: list[dict] = []
        if r.get("csv_file"):
            wrong, written, details = wrong_values_in_csv(run_dir / "erp_import" / r["csv_file"], k)
        wrong_total += wrong
        written_total += written

        reads = field_reads(r, k, md)
        for name, ok in reads:
            by_field[name].append(ok)
            by_cat[k["category"]].append(ok)

        calls = r.get("calls") or []
        if k["is_po"]:
            po_docs += 1
        cost += sum(c.get("cost_usd") or 0 for c in calls)
        seconds += sum(c.get("seconds") or 0 for c in calls)

        row = {"doc_id": r["doc_id"], "category": k["category"], "trap": k.get("trap"),
               "expected_route": exp, "route": got, "expected_codes": k.get("expected_reason_codes") or [],
               "codes": sorted(codes), "verdict": verdict, "wrong_values_written": wrong,
               "fields_read": len(reads), "fields_read_right": sum(ok for _, ok in reads)}
        per_doc.append(row)
        if verdict not in ("ok",) or wrong:
            failures.append({**row, "wrong_value_details": details[:20],
                             "findings": [f"{f['code']} {f['scope']} {f['field']}: {f['note']}" for f in r.get("findings", [])][:12]})

    n = len(records)
    pct = lambda a, b: round(100 * a / b, 1) if b else None  # noqa: E731
    return {
        "run": run_dir.name,
        "split": "+".join(sorted(splits)),
        "scored_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "documents": n,
        "model": run_meta.get("models"),
        "headline": {
            "wrong_values_written": wrong_total,
            "values_written": written_total,
            # orders that should have gone to review (trap, injection, non-PO) but were written
            "review_orders_auto_approved": false_auto,
            # orders that were written with at least one wrong value, out of all written orders
            "auto_orders_with_wrong_values": sum(1 for x in per_doc if x["wrong_values_written"]),
            "auto_orders": sum(x["route"] == "auto" for x in per_doc),
            "auto_approved": sum(x["route"] == "auto" for x in per_doc),
            "sent_to_review": sum(x["route"] == "review" for x in per_doc),
            "ignored": sum(x["route"] == "ignored" for x in per_doc),
        },
        "routing": {
            "correct_route_pct": pct(route_ok, n),
            "careful_review": careful,
            "false_review": false_review,
            "reason_code_accuracy_pct": pct(reason_ok, reason_n),
            "reason_code_cases": reason_n,
        },
        "field_read_accuracy_pct": {
            "overall": pct(sum(sum(v) for v in by_field.values()), sum(len(v) for v in by_field.values())),
            "by_category": {c: pct(sum(v), len(v)) for c, v in sorted(by_cat.items())},
            "by_field": {f: pct(sum(v), len(v)) for f, v in sorted(by_field.items())},
        },
        "cost_and_time": {
            "api_equivalent_cost_usd_total": round(cost, 4),
            "api_equivalent_cost_usd_per_po": round(cost / po_docs, 4) if po_docs else None,
            "model_seconds_per_po": round(seconds / po_docs, 1) if po_docs else None,
            "note": "claude -p on a subscription: no money is charged per call; cost is what the CLI reports as API-equivalent.",
        },
        "per_document": per_doc,
        "failures": failures,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", type=Path, required=True)
    ap.add_argument("--master", type=Path, default=ROOT / "test-set" / "master-data")
    ap.add_argument("--publish", action="store_true", help="merge a held-out score into results.json")
    a = ap.parse_args()
    s = score(a.run, a.master)
    (a.run / "score.json").write_text(json.dumps(s, indent=2), encoding="utf-8")
    print(json.dumps({k: s[k] for k in ("run", "split", "documents", "headline", "routing", "field_read_accuracy_pct", "cost_and_time")}, indent=2))
    if a.publish:
        if s["split"] != "heldout":
            print("refused: only held-out runs are published", file=sys.stderr)
            return 2
        target = ROOT / "results.json"
        results = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {
            "what": "Live runs of the PO-to-ERP agent on the held-out synthetic test set. Produced by measure.py. Do not edit by hand.",
            "runs": {}}
        results["runs"][s["run"]] = {k: v for k, v in s.items() if k != "per_document"}
        results["runs"][s["run"]]["per_document"] = s["per_document"]
        target.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"published {s['run']} to results.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
