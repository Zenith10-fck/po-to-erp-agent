"""Source files must not hide control characters. A raw backspace once sat inside a regex in the
report's JavaScript (meant as the word boundary \\b) and printed 'PO PO-72531'."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTROL = re.compile(rb"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def test_no_control_bytes_in_source():
    files = [*ROOT.glob("src/**/*.py"), *ROOT.glob("tests/**/*.py"), *ROOT.glob("prompts/*.md"),
             ROOT / "measure.py", *ROOT.glob("portfolio/*.py")]
    bad = [str(p.relative_to(ROOT)) for p in files if CONTROL.search(p.read_bytes())]
    assert bad == []


def test_po_prefix_rule_in_page_code():
    src = (ROOT / "src" / "po_agent" / "report.py").read_text(encoding="utf-8")
    assert 'function poText(po){ return /^P\\.?O\\b/i.test(po)' in src
