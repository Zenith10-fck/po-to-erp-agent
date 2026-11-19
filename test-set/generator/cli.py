"""Test-set generator CLI (see SPEC.md).

    uv run python test-set/generator/cli.py --all
    uv run python test-set/generator/cli.py --master-only
    uv run python test-set/generator/cli.py --split dev
    uv run python test-set/generator/cli.py --doc dev-007

Writes master data, render specs, PDFs, .eml files, answer keys and test-set/CASES.md.
The output only prints counts, never held-out details (hold-out discipline).
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from collections import Counter

HERE = pathlib.Path(__file__).resolve().parent
TEST_SET = HERE.parent
sys.path.insert(0, str(HERE))

import answer_key as ak  # noqa: E402
import emails  # noqa: E402
import master_data  # noqa: E402
import scenarios  # noqa: E402

try:
    from render import DEGRADATIONS, LAYOUTS, render_document  # noqa: E402
    RENDERER = "real"
except ImportError:  # Part B not there yet: a plain text dump, good enough to test the plumbing
    RENDERER = "stub"
    LAYOUTS = ["classic_table", "modern_blocks", "free_text", "side_by_side", "compact_grid",
               "letter_style", "erp_export", "form_boxes"]
    DEGRADATIONS = ["scan", "rotate90", "rotate180", "skew", "noise", "fax"]

    def render_document(spec: dict, out_pdf: pathlib.Path, fonts_dir: pathlib.Path) -> None:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas

        out_pdf.parent.mkdir(parents=True, exist_ok=True)
        c = canvas.Canvas(str(out_pdf), pagesize=letter, invariant=1)
        c.setFont("Helvetica", 8)
        y = 760
        text = json.dumps(spec, indent=1, ensure_ascii=False).splitlines()
        for row in ["STUB RENDER (Part B render.py missing)"] + text:
            if y < 40:
                c.showPage()
                c.setFont("Helvetica", 8)
                y = 760
            c.drawString(40, y, row[:120])
            y -= 10
        c.save()

SPLIT_DIR = {"dev": "dev", "heldout": "heldout"}
GEN_PREFIXES = ("dev-", "held-")


def clean_outputs() -> None:
    """Remove files from an earlier run (only generator-made names)."""
    for folder, exts in ((TEST_SET / "specs", (".json",)), (TEST_SET / "answer-key", (".json",)),
                         (TEST_SET / "dev", (".pdf", ".eml")), (TEST_SET / "heldout", (".pdf", ".eml"))):
        if not folder.exists():
            continue
        for p in folder.iterdir():
            if p.is_file() and p.name.startswith(GEN_PREFIXES) and p.suffix in exts:
                p.unlink()


def write_scenario(sc: scenarios.Scenario) -> None:
    split_dir = TEST_SET / SPLIT_DIR[sc.split]
    split_dir.mkdir(parents=True, exist_ok=True)
    spec_path = TEST_SET / "specs" / f"{sc.doc_id}.json"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(json.dumps(sc.spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    pdf = split_dir / f"{sc.doc_id}.pdf"
    render_document(sc.spec, pdf, TEST_SET / "fonts")
    emails.write_eml(split_dir / f"{sc.doc_id}.eml", sc.email, sc.doc_id, pdf.read_bytes())
    ak.write_key(TEST_SET / "answer-key" / f"{sc.doc_id}.json", sc.key)


def _row(sc: scenarios.Scenario) -> str:
    k = sc.key
    codes = ", ".join(k["expected_reason_codes"]) or "-"
    ok = ", ".join(k["acceptable_review_codes"]) or "-"
    layout = sc.spec["layout"] if sc.spec["kind"] == "po" else sc.spec["kind"]
    deg = "+".join(sc.spec["degradations"]) or ("handwritten" if sc.spec["handwritten"] else "text")
    return (f"| {sc.doc_id} | {sc.category} | {k['trap'] or '-'} | {k['expected_route']} | {codes} | {ok} "
            f"| {layout} | {deg} | {sc.note} |")


HEADER = ("| doc_id | category | trap | expected route | expected codes | careful-review codes "
          "| layout | render | note |\n|---|---|---|---|---|---|---|---|---|")


def write_cases(all_sc: list[scenarios.Scenario]) -> None:
    dev = [s for s in all_sc if s.split == "dev"]
    held = [s for s in all_sc if s.split == "heldout"]
    counts = Counter(s.category for s in held)
    lines = [
        "# Test-set cases",
        "",
        "Written by `test-set/generator/cli.py`. All documents are synthetic.",
        "",
        "Expected route `auto` with careful-review codes R09/R11: a scan that goes to review with only",
        "those codes counts as a careful review, not an error.",
        "",
        f"## Dev ({len(dev)} documents, seeds 1001-1020)",
        "",
        HEADER,
        *[_row(s) for s in dev],
        "",
        f"## Held-out ({len(held)} documents, seeds 5001-5020)",
        "",
        "Hold-out discipline: only the counts are shown here. The per-document list is in",
        "`test-set/answer-key/CASES-heldout.md`. Do not open it (or the held-out answer keys,",
        "specs or documents) before held-out run B is finished.",
        "",
        "| category | documents |",
        "|---|---|",
        *[f"| {c} | {counts[c]} |" for c in ak.CATEGORIES if counts[c]],
        "",
    ]
    (TEST_SET / "CASES.md").write_text("\n".join(lines), encoding="utf-8")
    held_lines = ["# Held-out cases (do not open before run B)", "", HEADER, *[_row(s) for s in held], ""]
    (TEST_SET / "answer-key").mkdir(parents=True, exist_ok=True)
    (TEST_SET / "answer-key" / "CASES-heldout.md").write_text("\n".join(held_lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the synthetic PO test set.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--all", action="store_true", help="master data + every document")
    g.add_argument("--master-only", action="store_true", help="only the master data CSVs")
    g.add_argument("--split", choices=["dev", "heldout"], help="one split")
    g.add_argument("--doc", help="one document, e.g. dev-007")
    args = ap.parse_args(argv)

    tables = master_data.write_master(TEST_SET / "master-data")
    print("master data:", {k: len(v) for k, v in tables.items()})
    if args.master_only:
        return 0

    all_sc = scenarios.build_all(master_data.Master(tables))
    if args.all:
        chosen = all_sc
        clean_outputs()
    elif args.split:
        chosen = [s for s in all_sc if s.split == args.split]
    else:
        chosen = [s for s in all_sc if s.doc_id == args.doc]
        if not chosen:
            print(f"unknown doc id: {args.doc}")
            return 2
    for sc in chosen:
        write_scenario(sc)
    write_cases(all_sc)
    by_split = Counter(s.split for s in chosen)
    print(f"renderer: {RENDERER}; documents written: {dict(by_split)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
