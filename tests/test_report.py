"""The report page, built from the demo run (fake model). Proves the page, not the model."""
from __future__ import annotations

import json
import re
import shutil

import pytest
from fixtures.demo_run import RUN_ID, build

from po_agent.gates.base import REASONS
from po_agent.report import FONT_DIR, FONTS, REASON_UI, build_report, finding_sentence

TOKEN_HEX = {  # docs/ui-reference-v2.md section 4.3 ("Signal"), light and dark
    "#f7f8fa", "#ffffff", "#eef0f3", "#f3f4f7", "#edf1fd", "#17181c", "#5b606b", "#e4e6eb", "#cdd1d9",
    "#878d98", "#2453d6", "#ecf1fe", "#b9c9f7", "#167a43", "#e7f5ed", "#c2261c",
    "#0e0f12", "#16181c", "#1b1d22", "#1d2026", "#1b2440", "#eceef2", "#a0a5b0", "#272a31", "#363a45",
    "#6f7582", "#7d9dff", "#1c2647", "#34478a", "#4fc483", "#132a1d", "#22252c", "#ff7a6e",
}
TYPE_SCALE = {"12px", "13px", "14px", "16px", "20px", "28px"}   # section 4.2
CODE_RE = re.compile(r"\bR\d\d\b")
DATA_RE = re.compile(r'<script type="application/json" id="data">(.*?)</script>', re.S)
FONT_RE = re.compile(r"@font-face\{[^}]*\}")


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    run_dir = build(tmp_path_factory.mktemp("demo") / "run")
    html_path = build_report(run_dir)
    html = html_path.read_text(encoding="utf-8")
    data = json.loads(DATA_RE.search(html).group(1))
    return run_dir, html_path, html, data


def _page(html):
    """The page code alone: no data block, no embedded font files."""
    return FONT_RE.sub("", DATA_RE.sub("", html))


def _records(run_dir):
    return [json.loads(x) for x in (run_dir / "audit.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]


def _order(data, doc_id):
    return next(o for o in data["orders"] if o["id"] == doc_id)


def test_report_builds_from_demo_run(demo):
    run_dir, path, html, data = demo
    assert path == run_dir / "run-report.html"
    assert data["documents"] == 8 and (data["auto"], data["review"], data["ignored"]) == (1, 6, 1)
    assert path.stat().st_size < 3_000_000          # 8 pages as base64 JPEG, plus about 80 KB of fonts
    for o in data["orders"]:
        assert o["pages"], o["id"]
        assert all(p["src"].startswith("data:image/jpeg;base64,") for p in o["pages"])


def test_demo_marker_present(demo):
    _, _, html, data = demo
    assert data["run_id"] == RUN_ID and data["demo"] is True
    assert "Demo data, fake model" in html
    assert "(demo data)" in html.split("</title>")[0]


def test_output_is_self_contained(demo):
    _, _, html, _ = demo
    assert not re.search(r"https?://", html)
    assert "<link" not in html and "@import" not in html
    assert not re.search(r"""\bsrc=["'](?!data:)""", html)    # no static src that is not inline
    urls = re.findall(r"url\(([^)]{0,40})", html)
    assert urls and all(u.startswith("data:font/woff2;base64,") for u in urls)   # only the embedded fonts


def test_fonts_are_embedded_and_licensed(demo):
    _, _, html, _ = demo
    faces = FONT_RE.findall(html)
    assert len(faces) == len(FONTS) == 1
    assert re.search(r'font-family:"([^"]+)"', faces[0]).group(1) == "Hanken Grotesk"
    assert (FONT_DIR / FONTS[0][2]).read_bytes()[:4] == b"wOF2"
    assert "SIL Open Font License" in (FONT_DIR / "OFL-hanken-grotesk.txt").read_text(encoding="utf-8")
    assert sorted(p.name for p in FONT_DIR.iterdir()) == sorted(["OFL-hanken-grotesk.txt", FONTS[0][2]])
    page = _page(html)
    families = {f.strip().strip('"') for v in re.findall(r"--(?:sans|mono):([^;]+);", page) for f in v.split(",")}
    assert families <= {"Hanken Grotesk", "ui-sans-serif", "system-ui", "Segoe UI", "sans-serif",
                        "ui-monospace", "Cascadia Mono", "Consolas", "monospace"}
    for banned in ("Inter", "Geist", "Instrument Sans", "IBM Plex", "DM Sans", "Space Grotesk", "Poppins", "Manrope"):
        assert banned not in page, banned
    assert "font-family:" not in page.replace("font-family:var(--sans)", "").replace("font-family:var(--mono)", "")
    assert page.count("var(--mono)") <= 3              # monospace only for file names and the raw CSV file


def test_anti_slop_rules(demo):
    """docs/ui-reference-v2.md section 6, checked mechanically on the page code."""
    _, _, html, _ = demo
    page = _page(html)
    assert "gradient" not in page
    assert "backdrop-filter" not in page and not re.search(r"blur\(\s*\d", page)   # (e.target.blur() is JS)
    shadows = re.findall(r"box-shadow:([^;}]+)", page)
    assert sorted(shadows) == ["inset 3px 0 0 var(--accent)", "var(--lift)", "var(--lift)"]   # row, popover, help
    for v in re.findall(r"border-radius:([^;}]+)", page):
        assert all(x in ("50%", "999px", "0") or int(x.rstrip("px")) <= 8 for x in v.split()), v
    assert set(re.findall(r"font-size:\s*([^;}]+)", page)) <= TYPE_SCALE
    assert all(int(w) <= 600 for w in re.findall(r"font-weight:\s*(\d+)", page))
    assert set(h.lower() for h in re.findall(r"#[0-9a-fA-F]{6}\b", page)) <= TOKEN_HEX
    assert not re.search(r"#[0-9a-fA-F]{3}\b(?![0-9a-fA-F])", page)
    assert not re.findall(r"rgba?\((?!0,0,0,|16,18,24,)", page)             # shadows only
    assert "text-transform" not in page                                     # no uppercase "eyebrow" labels
    assert set(re.findall(r"letter-spacing:\s*([^;}]+)", page)) <= {"-.015em"}   # headline only
    assert not [c for c in html if ord(c) >= 0x1F000 or 0x2600 <= ord(c) <= 0x27BF]
    assert set(re.findall(r"animation:\s*([^;}]+)", page)) <= {"locate 700ms ease-out 2", "none !important"}
    assert re.findall(r"@keyframes\s+(\w+)", page) == ["locate"]
    assert set(re.findall(r"transition:\s*([^;}]+)", page)) <= {"background-color 120ms", "none !important"}
    assert "text-align:center" not in page.replace(" ", "")
    assert "prefers-reduced-motion" in page and "prefers-color-scheme:dark" in page and "@media print" in page


def test_no_reason_codes_in_the_interface(demo):
    """Codes stay in the data; the user sees labels and icons only."""
    _, _, html, data = demo
    assert not CODE_RE.findall(_page(html))
    ui = [json.dumps(list(data["reason_help"].values()))]
    for o in data["orders"]:
        ui += [o["summary_line"] or ""] + [a["step"] + " " + a["text"] for a in o["audit"]]
        ui += [f[k] or "" for f in o["findings"] for k in ("plain", "note", "label", "where", "subject")]
        ui += [r for x in o["checks"] + o["header"] + o["lines"] for r in x["reasons"]]
    hits = [u for u in ui if CODE_RE.search(u)]
    assert not hits, hits[:3]
    for code, (label, icon, todo, why) in REASON_UI.items():
        assert 2 <= len(label.replace("'", "").split()) <= 4 and len(todo.split()) <= 8 and why.endswith("."), code
        assert f'data-g="{icon}"' in html, icon


def test_untrusted_text_is_never_html(demo):
    _, _, html, _ = demo
    page = _page(html)
    for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"):
        assert sink not in page
    assert page.count("localStorage") == 2                                  # only in load() and save()
    assert re.search(r"function load\(k, dflt\)\{ try \{", page) and re.search(r"function save\(k, v\)\{ try \{", page)


def test_first_run_guidance_and_plain_labels(demo):
    _, _, html, data = demo
    page = _page(html)
    for words in ("PDF arrives", "Claude reads it", "Code checks every value", "Proven: written",
                  "Doubtful: waits for you", "Review first order", "Needs check", "Written to ERP", "Not an order",
                  "problem", "Show on PDF", "Why?", "Mark as checked", "Notes stay in this browser"):
        assert words in page, words
    for jargon in ('"Auto-approved"', '"Ignored"', '"Review"', "reason code"):     # old labels, not shown any more
        assert jargon not in page
    assert set(data["reason_help"]) == set(REASONS) == set(REASON_UI)


def test_ui_text_has_no_filler(demo):
    _, _, html, data = demo
    text = json.dumps({k: v for k, v in data.items() if k != "orders"})
    for o in data["orders"]:
        text += " ".join([o["summary_line"] or ""] + [f["sentence"] for f in o["findings"]]
                         + [a["text"] for a in o["audit"]])
    page = _page(html)
    for bad in ("!", "Welcome", "Powered by", "Seamless", "Something went wrong", "Validation failed"):
        assert bad not in text
    for bad in ("Welcome", "Powered by", "Seamless", "magic", "Something went wrong", "Validation failed", "AI-powered"):
        assert bad not in page
    assert not re.search(r'text:"[^"]*!"', page)                                # no exclamation in UI strings


def test_not_scored_without_score_json(demo):
    run_dir, _, html, data = demo
    assert not (run_dir / "score.json").exists()
    assert data["scored"] is False and data["wrong_values"] is None
    assert '"not scored"' in html and '"not reported"' in html


def test_score_json_is_used_when_present(demo, tmp_path):
    run_dir, _, _, _ = demo
    copy = tmp_path / "run"
    shutil.copytree(run_dir, copy)
    (copy / "score.json").write_text(json.dumps({"headline": {"wrong_values_written": 0, "values_written": 40},
                                                 "cost_and_time": {"note": "test note"}}), encoding="utf-8")
    data = json.loads(DATA_RE.search(build_report(copy).read_text(encoding="utf-8")).group(1))
    assert data["scored"] is True and data["wrong_values"] == 0 and data["values_written"] == 40
    assert data["cost_note_full"] == "test note"


def test_every_finding_appears_as_a_sentence(demo):
    run_dir, _, _, data = demo
    records = _records(run_dir)
    assert sum(len(r["findings"]) for r in records) >= 8
    for r in records:
        shown = _order(data, r["doc_id"])["findings"]
        assert len(shown) == len(r["findings"])
        for f in r["findings"]:
            s = finding_sentence(f)
            assert s in [x["sentence"] for x in shown]
            assert s.startswith(f["code"] + " ") and s.endswith(".")
            if f.get("read"):
                assert f["read"] in s
            if f.get("expected"):
                assert f["expected"] in s
        for x in shown:                         # what was read vs what was expected, for the compare box
            assert x["targets"][0] == x["target"] and x["where"]
            assert "read" in x and "expected" in x


def test_sentences_carry_the_real_numbers(demo):
    _, _, _, data = demo
    d02 = _order(data, "d02")["findings"][0]
    assert d02["sentence"] == "R06 Line 2 unit price 0.14 differs from the list price per EA 0.1100."
    assert (d02["read"], d02["expected"], d02["where"]) == ("0.14", "0.1100", "Line 2")
    assert "l2:unit_price" in d02["targets"]
    assert "R07 Line 1 line total 423.00 is not qty x unit price (432.00)." in \
        [f["sentence"] for f in _order(data, "d03")["findings"]]
    assert _order(data, "d07")["findings"][0]["sentence"] == "R09 Line 1 qty: first read 5, second read 6."


def test_field_results(demo):
    _, _, _, data = demo
    d01 = _order(data, "d01")
    assert d01["counts"]["failed"] == 0 and d01["summary_line"].startswith(f"All {d01['proven']} checks proven.")
    d02 = _order(data, "d02")
    line2 = d02["lines"][1]
    assert line2["result"] == "failed" and line2["cells"]["unit_price"]["result"] == "failed"
    assert line2["cells"]["description"]["result"] == "not_checked"
    d06 = _order(data, "d06")                                        # unknown item: no price check
    assert d06["lines"][1]["cells"]["item"]["result"] == "failed"
    assert d06["lines"][1]["cells"]["unit_price"]["result"] == "not_checked"
    d07 = _order(data, "d07")                                        # scan: bill-to is not compared
    bill = next(f for f in d07["header"] if f["key"] == "h:bill_to_name")
    assert bill["result"] == "not_checked"
    d08 = _order(data, "d08")
    assert d08["route"] == "ignored" and d08["classify"]["doc_type"] == "invoice" and not d08["header"]


def test_evidence_boxes(demo):
    _, _, _, data = demo
    d02 = _order(data, "d02")
    box = [b for b in d02["boxes"] if b["k"] == "l2:unit_price"]
    assert len(box) == 1 and box[0]["st"] == "failed" and box[0]["p"] == 1
    assert all(0 <= b["x"] < 1 and 0 <= b["y"] < 1 and 0 < b["w"] < 1 and 0 < b["h"] < 1 for b in d02["boxes"])
    # ship-to address and bill-to address print the same text: each gets its own place on the page
    bill = next(b for b in d02["boxes"] if b["k"] == "h:bill_to_address")
    ship = next(b for b in d02["boxes"] if b["k"] == "h:ship_to_address")
    assert (bill["x"], bill["y"]) != (ship["x"], ship["y"])
    assert any(b["k"] == "c:suspicious" for b in _order(data, "d05")["boxes"])
    assert _order(data, "d07")["boxes"] == []                       # scan: no coordinates


def test_csv_tab_only_for_auto(demo):
    _, _, _, data = demo
    d01 = _order(data, "d01")
    assert d01["csv"]["file"] == "C0001_PO-48213.csv" and len(d01["csv"]["rows"]) == 2
    assert d01["csv"]["head"][0] == "customer_id"
    assert all(o["csv"] is None for o in data["orders"] if o["route"] != "auto")


def test_reviewer_notes_are_honest(demo):
    """The page has no backend: no control may pretend to approve, send or write to the ERP."""
    _, _, html, _ = demo
    page = _page(html)
    for fake in ("Approve", "Send to ERP", "Submit", "Push to", "Sync"):
        assert fake not in page, fake
    assert "fetch(" not in page and "XMLHttpRequest" not in page and "sendBeacon" not in page
    assert "Download notes (CSV)" in page
    assert re.search(r"/\^\[=\+\\-@\\t\\r\]/", page)                            # CSV formula guard on export


def test_untrusted_text_cannot_break_the_page(demo, tmp_path):
    run_dir, _, _, _ = demo
    copy = tmp_path / "run"
    shutil.copytree(run_dir, copy)
    records = _records(copy)
    records[0]["subject"] = '</script><img src=x onerror="alert(1)"> https://evil.example'
    (copy / "audit.jsonl").write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    html = build_report(copy).read_text(encoding="utf-8")
    assert "</script><img" not in html and "<img src=x" not in html
    assert not re.search(r"https?://", html)
    data = json.loads(DATA_RE.search(html).group(1))
    assert data["orders"][0]["subject"].startswith("</script>")      # kept as data, shown as text
