"""Command line: `python -m po_agent.cli run --inbox <folder> --out <folder>`."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .intake import read_inbox
from .masterdata import MasterData
from .model_client import ClaudeCliClient
from .pipeline import ROOT, run


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="po-agent", description="Emailed PDF purchase orders -> ERP import CSV")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="process every .eml in a folder")
    r.add_argument("--inbox", type=Path, required=True)
    r.add_argument("--out", type=Path, required=True)
    r.add_argument("--master", type=Path, default=ROOT / "test-set" / "master-data")
    r.add_argument("--run-id", default=None)
    r.add_argument("--model", default="sonnet")
    r.add_argument("--workers", type=int, default=4)
    r.add_argument("--limit", type=int, default=0, help="only the first N emails")
    r.add_argument("--replay", action="store_true",
                   help="no model calls: run the gates again on the saved reads in <out>/raw")
    a = ap.parse_args(argv)

    mails = read_inbox(a.inbox)
    if a.limit:
        mails = mails[:a.limit]
    if not mails:
        print(f"no .eml files in {a.inbox}", file=sys.stderr)
        return 1
    md = MasterData.load(a.master)

    def progress(raw):
        kinds = ", ".join(f"{c['kind']} {c['seconds']}s" for c in raw["calls"])
        print(f"  read {raw['doc_id']} [{raw['mode']}] {kinds}", flush=True)

    summary = run(mails, a.out, md, ClaudeCliClient(model=a.model), a.run_id or a.out.name,
                  workers=a.workers, replay=a.replay, progress=progress)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
