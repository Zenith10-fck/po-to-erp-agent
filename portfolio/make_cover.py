"""Draws portfolio/cover.png from results.json, in the same "Proof sheet" design as the report.

    uv run python portfolio/make_cover.py

Every number on the cover is read from results.json (held-out runs A and B). Nothing is typed in.
The cover is a small HTML page (report fonts embedded) that headless Edge or Chrome turns into a
PNG. If no browser is found, the HTML is still written next to this file.
"""
from __future__ import annotations

import base64
import html
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))

from po_agent.report import _font_css  # noqa: E402

BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    shutil.which("chromium") or "", shutil.which("google-chrome") or "",
]


def cell(label: str, value: str, sub: str, mark: bool = False) -> str:
    cls = "v mark" if mark else "v"
    return (f'<div class="cell"><div class="eyebrow">{html.escape(label)}</div>'
            f'<div class="{cls}">{html.escape(value)}</div><div class="sub">{html.escape(sub)}</div></div>')


def build_html() -> str:
    runs = json.loads((ROOT / "results.json").read_text(encoding="utf-8"))["runs"]
    a, b = runs["A"], runs["B"]
    ha, hb = a["headline"], b["headline"]
    same = (ha["wrong_values_written"], ha["auto_orders_with_wrong_values"]) == \
           (hb["wrong_values_written"], hb["auto_orders_with_wrong_values"])
    cells = "".join([
        cell("Wrong values written", f"{ha['wrong_values_written']} / {ha['values_written']:,}",
             f"in {ha['auto_orders_with_wrong_values']} of {ha['auto_orders']} written orders", mark=True),
        cell("Trap orders written", str(ha["review_orders_auto_approved"]),
             f"run B: {hb['review_orders_auto_approved']} · traps and injection PDFs"),
        cell("Right reason code", f"{a['routing']['reason_code_cases']} / {a['routing']['reason_code_cases']}"
             if a["routing"]["reason_code_accuracy_pct"] == 100 else f"{a['routing']['reason_code_accuracy_pct']}%",
             "on every trap and injection order"),
        cell("Values read right", f"{a['field_read_accuracy_pct']['overall']}%",
             f"run B: {b['field_read_accuracy_pct']['overall']}%"),
        cell("API-equivalent cost", f"${a['cost_and_time']['api_equivalent_cost_usd_per_po']:.2f}",
             "per PO, on a subscription"),
    ])
    note = ("Held-out set: 20 synthetic documents never used for tuning, frozen build. Run A shown"
            + ("; run B gave the same wrong-value count." if same else "; run B in the small print.")
            + " Numbers from results.json. Screenshot: dev run 2.")
    shot = base64.b64encode((HERE / "report-detail-price-light.png").read_bytes()).decode("ascii")
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
{_font_css()}
:root{{--bg:#f7f8fa;--surface:#ffffff;--text:#17181c;--text-2:#5b606b;--line:#e4e6eb;--accent:#2453d6;--accent-bg:#ecf1fe}}
*{{box-sizing:border-box;margin:0}}
body{{width:1600px;height:1000px;overflow:hidden;background:var(--bg);color:var(--text);
  font-family:"Hanken Grotesk",sans-serif;font-variant-numeric:tabular-nums;-webkit-font-smoothing:antialiased;padding:56px 64px 0}}
.eyebrow{{display:inline-block;font-size:14px;font-weight:600;color:var(--accent);background:var(--accent-bg);padding:4px 10px;border-radius:999px}}
h1{{font-size:56px;line-height:62px;font-weight:700;letter-spacing:-.025em;margin-top:18px}}
h1 em{{font-style:normal;color:var(--accent)}}
.lead{{font-size:22px;line-height:32px;color:var(--text-2);margin-top:12px;max-width:1080px}}
.strip{{display:grid;grid-template-columns:repeat(5,1fr);margin-top:34px;background:var(--surface);border:1px solid var(--line);border-radius:12px}}
.cell{{padding:18px 22px}}
.cell+.cell{{border-left:1px solid var(--line)}}
.cell .eyebrow{{display:block;background:none;padding:0;color:var(--text-2);font-weight:500;font-size:15px}}
.v{{font-weight:650;font-size:38px;line-height:46px;margin-top:6px;letter-spacing:-.01em}}
.v.mark{{color:var(--accent)}}
.sub{{font-size:15px;line-height:20px;color:var(--text-2);margin-top:2px}}
.note{{font-size:14px;color:var(--text-2);margin-top:16px}}
.shot{{margin-top:24px;border:1px solid var(--line);border-bottom:0;border-radius:12px 12px 0 0;overflow:hidden;
  height:560px;background:var(--surface);box-shadow:0 1px 2px rgba(16,18,24,.06),0 12px 32px rgba(16,18,24,.14)}}
.shot img{{width:100%;display:block}}
</style></head><body>
<div class="eyebrow">Reference build · synthetic purchase orders</div>
<h1>PO-to-ERP intake agent. <em>Claude reads, code proves.</em></h1>
<p class="lead">Emailed PDF purchase orders in any layout become ERP import files. Every value is checked against the PDF and the master data; anything doubtful waits for a person, with the reason marked on the page.</p>
<div class="strip">{cells}</div>
<p class="note">{html.escape(note)}</p>
<div class="shot"><img src="data:image/png;base64,{shot}" alt=""></div>
</body></html>"""


def main() -> None:
    page = HERE / "cover.html"
    page.write_text(build_html(), encoding="utf-8")
    browser = next((b for b in BROWSERS if b and os.path.exists(b)), None)
    if not browser:
        print(f"no browser found; open {page} and take a 1600x1000 screenshot")
        return
    out = HERE / "cover.png"
    subprocess.run([browser, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                    "--force-device-scale-factor=1", "--window-size=1600,1000",
                    "--virtual-time-budget=3000", f"--screenshot={out}", page.as_uri()],
                   check=True, capture_output=True, timeout=120)
    page.unlink()
    print(out)


if __name__ == "__main__":
    main()
