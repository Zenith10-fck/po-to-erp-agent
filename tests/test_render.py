"""Tests for Part B of the test-set generator (render spec -> PDF).

They render the hand-written sample specs in every layout and check the PDF itself: the text
layer, the evidence gate's row rule, null handling, page flow, extra pages, injections,
degradations and determinism. They prove the renderer, not any model.
"""
from __future__ import annotations

import copy
import importlib
import re
import sys
from pathlib import Path

import pymupdf
import pytest

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "test-set" / "generator"
FONTS = ROOT / "test-set" / "fonts"
sys.path.insert(0, str(GEN))
sys.path.insert(0, str(ROOT / "src"))

from po_agent.document import load_document  # noqa: E402
from po_agent.gates.evidence import check_text_pdf, in_text, occurrences, tokens_in_text  # noqa: E402
from po_agent.normalize import squash  # noqa: E402
from render import DEGRADATIONS, LAYOUTS, build_pdf_bytes, render_document  # noqa: E402
from sample_specs import non_po_samples, po_samples, stress_samples  # noqa: E402

TYPED = [s for s in po_samples() if not s.get("handwritten")] + stress_samples()
CASES = [(s["doc_id"], layout) for s in TYPED for layout in LAYOUTS]
BY_ID = {s["doc_id"]: s for s in TYPED}


def has(v) -> bool:
    return v is not None and str(v).strip() != ""


def spec_for(doc_id: str, layout: str) -> dict:
    s = copy.deepcopy(BY_ID[doc_id])
    s["layout"] = layout
    return s


def render(tmp_path: Path, spec: dict, name: str = "doc") -> Path:
    out = tmp_path / f"{name}.pdf"
    render_document(spec, out, FONTS)
    return out


def page_texts(pdf: Path) -> list[str]:
    with pymupdf.open(pdf) as d:
        return [squash(p.get_text()) for p in d]


def printed_values(spec: dict, layout: str) -> list[str]:
    """Every string of the spec that the layout must print."""
    vals = []
    b = spec.get("buyer") or {}
    vals += [b.get("name"), b.get("contact")]
    if layout != "erp_export":          # a system printout has no logo
        vals.append(b.get("logo_text"))
    vals += b.get("address_lines") or []
    for key in ("supplier", "bill_to", "ship_to"):
        p = spec.get(key) or {}
        vals += [p.get("name")] + list(p.get("address_lines") or [])
    car = spec.get("carrier") or {}
    vals += [car.get("name"), car.get("account_no"), car.get("label")]
    for key in ("po_number", "po_number_label", "po_date", "currency", "shipping_notes",
                "order_total", "order_total_label", "payment_terms"):
        vals.append(spec.get(key))
    if spec.get("injection_style") in ("visible_note", "white_text"):
        vals.append(spec.get("injection_text"))
    for ln in spec.get("lines") or []:
        vals += [ln.get(k) for k in ("line_no", "item_no", "customer_part_no", "description", "qty",
                                     "uom", "unit_price", "line_total", "requested_date")]
    return [squash(str(v)) for v in vals if has(v)]


def fld(value, page):
    if not has(value):
        return {"value": None, "page": None, "quote": None}
    return {"value": str(value), "page": page, "quote": str(value)}


def perfect_extraction(spec: dict, pdf: Path) -> dict:
    """What a perfect model would return, with page = the page where the value is printed."""
    doc = load_document(pdf)

    def where(value, tokens=False):
        if not has(value):
            return None
        for p in doc.pages:
            if (tokens_in_text(p, str(value)) if tokens else in_text(p, str(value))):
                return p.number
        return 1     # not found: the gate must then complain

    def addr(party):
        lines = (party or {}).get("address_lines") or []
        return ", ".join(str(x) for x in lines if has(x)) or None

    b, bill, ship = spec.get("buyer") or {}, spec.get("bill_to") or {}, spec.get("ship_to") or {}
    car = spec.get("carrier") or {}
    ex = {"legibility": "clear"}
    for name, v in (("po_number", spec.get("po_number")), ("po_date", spec.get("po_date")),
                    ("order_total", spec.get("order_total")), ("currency", spec.get("currency")),
                    ("carrier_account_no", car.get("account_no"))):
        ex[name] = fld(v, where(v))
    for name, v in (("customer_name", b.get("name")), ("bill_to_name", bill.get("name")),
                    ("bill_to_address", addr(bill)), ("ship_to_name", ship.get("name")),
                    ("ship_to_address", addr(ship)), ("carrier_name", car.get("name")),
                    ("shipping_notes", spec.get("shipping_notes"))):
        ex[name] = fld(v, where(v, tokens=True))
    lines = []
    for ln in spec.get("lines") or []:
        anchor = ln.get("item_no") if has(ln.get("item_no")) else ln.get("customer_part_no")
        page = next((p.number for p in doc.pages if occurrences(p, str(anchor))), 1)
        lines.append({k: fld(ln.get(k), page) for k in
                      ("item_no", "customer_part_no", "qty", "uom", "unit_price", "line_total",
                       "requested_date")})
    ex["lines"] = lines
    return ex


# ---- every layout ----------------------------------------------------------------------------

@pytest.mark.parametrize("doc_id,layout", CASES)
def test_every_value_is_in_the_text_layer(tmp_path, doc_id, layout):
    spec = spec_for(doc_id, layout)
    pdf = render(tmp_path, spec)
    text = " ".join(page_texts(pdf))
    missing = [v for v in printed_values(spec, layout) if v not in text]
    assert not missing, f"not in text layer: {missing}"
    for bad in ("None", "null", "N/A"):
        assert not re.search(rf"\b{re.escape(bad)}\b", text), f"placeholder {bad!r} printed"


@pytest.mark.parametrize("doc_id,layout", CASES)
def test_evidence_gate_accepts_a_perfect_extraction(tmp_path, doc_id, layout):
    spec = spec_for(doc_id, layout)
    pdf = render(tmp_path, spec)
    doc = load_document(pdf)
    assert doc.is_text_pdf
    findings = check_text_pdf(doc, perfect_extraction(spec, pdf))
    assert not findings, [(f.scope, f.field, f.read, f.note) for f in findings]


@pytest.mark.parametrize("doc_id,layout", CASES)
def test_no_overlap_and_nothing_off_the_page(tmp_path, doc_id, layout):
    pdf = render(tmp_path, spec_for(doc_id, layout))
    problems = []
    with pymupdf.open(pdf) as d:
        for pn, p in enumerate(d, start=1):
            W, H = p.rect.width, p.rect.height
            spans = []
            for blk in p.get_text("dict")["blocks"]:
                for line in blk.get("lines", []):
                    for s in line["spans"]:
                        if s["text"].strip() and s["color"] != 0xFFFFFF:
                            spans.append((pymupdf.Rect(s["bbox"]), s["text"]))
            for r, t in spans:
                if r.x0 < 18 or r.x1 > W - 18 or r.y0 < 8 or r.y1 > H - 8:
                    problems.append(f"p{pn} off page: {t!r}")
            for i in range(len(spans)):
                for j in range(i + 1, len(spans)):
                    a, b = spans[i][0], spans[j][0]
                    inter = a & b
                    if not inter.is_empty and inter.width > 1.0 and \
                            inter.height > 0.45 * min(a.height, b.height):
                        problems.append(f"p{pn} overlap: {spans[i][1]!r} / {spans[j][1]!r}")
    assert not problems, problems[:10]


def test_layout_list():
    assert len(LAYOUTS) == 8 and len(set(LAYOUTS)) == 8
    assert set(DEGRADATIONS) == {"scan", "rotate90", "rotate180", "skew", "noise", "fax"}


def test_layouts_really_differ(tmp_path):
    """Same spec, eight layouts: no two pages share the same words in the same order, and the
    PO number sits in different places."""
    spec = BY_ID["sample-harlow"]
    texts, po_y = {}, {}
    for layout in LAYOUTS:
        pdf = render(tmp_path, spec_for(spec["doc_id"], layout), layout)
        doc = load_document(pdf)
        texts[layout] = doc.pages[0].text
        po_y[layout] = round(occurrences(doc.pages[0], spec["po_number"])[0] / 20)
    assert len(set(texts.values())) == 8
    assert len(set(po_y.values())) >= 4


# ---- null handling --------------------------------------------------------------------------

@pytest.mark.parametrize("layout", [x for x in LAYOUTS if x != "free_text"])
def test_null_columns_are_not_drawn(tmp_path, layout):
    spec = spec_for("sample-kessler", layout)       # no customer_part_no, no requested_date
    cols = importlib.import_module(f"layouts.{layout}").COLS
    text = " ".join(page_texts(render(tmp_path, spec)))
    for col in cols:
        if not any(has(ln.get(col.key)) for ln in spec["lines"]):
            assert not re.search(rf"(?<!\w){re.escape(col.label)}(?!\w)", text), \
                f"empty column {col.label!r} drawn"


@pytest.mark.parametrize("layout", LAYOUTS)
def test_null_values_leave_no_label(tmp_path, layout):
    spec = spec_for("sample-sparse", layout)        # no prices, total, terms, currency, supplier
    text = " ".join(page_texts(render(tmp_path, spec)))
    for label in ("Unit Price", "Payment Terms", "Currency", "CURRENCY", "TERMS:", "Terms:",
                  "Northfield", "Total:", "TOTAL"):
        assert label not in text, f"label {label!r} printed without a value"


# ---- multi-page, extra pages, other kinds ---------------------------------------------------

@pytest.mark.parametrize("layout", LAYOUTS)
def test_long_order_flows_onto_more_pages(tmp_path, layout):
    spec = spec_for("stress-60-lines", layout)
    pdf = render(tmp_path, spec)
    texts = page_texts(pdf)
    n = len(texts)
    assert n >= 2
    for i, t in enumerate(texts, start=1):
        assert f"Page {i} of {n}" in t
    assert spec["order_total"] in texts[-1]
    assert all(spec["order_total"] not in t for t in texts[:-1])


def test_extra_pages_order_and_count(tmp_path):
    spec = copy.deepcopy(BY_ID["sample-harlow"])
    base = len(page_texts(render(tmp_path, spec, "plain")))
    spec["extra_pages"] = ["cover", "terms"]
    texts = page_texts(render(tmp_path, spec, "extra"))
    assert len(texts) == base + 2
    cover, terms = texts[0], texts[-1]
    assert "FAX" in cover and f"{base + 2} (including this cover)" in cover
    assert not any(ln["item_no"] in cover for ln in spec["lines"])
    assert "TERMS AND CONDITIONS" in terms and len(terms.split()) >= 600
    assert re.search(r"\d{2}/\d{2}/\d{4}", terms)
    assert spec["lines"][0]["item_no"] in texts[1]


@pytest.mark.parametrize("spec", non_po_samples(), ids=lambda s: s["kind"])
def test_non_po_kinds(tmp_path, spec):
    text = " ".join(page_texts(render(tmp_path, spec)))
    assert "PURCHASE ORDER" not in text           # no PO title (case-sensitive)
    if spec["kind"] == "newsletter":
        assert spec["title"] in text
        assert all(squash(p) in text for p in spec["body_paragraphs"])
    else:
        assert spec["po_number"] in text and spec["po_number_label"] in text


# ---- injections ----------------------------------------------------------------------------

def test_white_text_is_in_the_layer_but_invisible(tmp_path):
    spec = copy.deepcopy(BY_ID["stress-injection-white_text"])
    pdf = render(tmp_path, spec, "white")
    doc = load_document(pdf)
    assert squash(spec["injection_text"]) in " ".join(p.text for p in doc.pages)
    assert any("SYSTEM MESSAGE" in h for h in doc.pages[0].hidden_text)
    clean = copy.deepcopy(spec)
    clean["injection_text"] = clean["injection_style"] = None
    pdf2 = render(tmp_path, clean, "clean")
    with pymupdf.open(pdf) as a, pymupdf.open(pdf2) as b:
        assert a[0].get_pixmap(dpi=100).samples == b[0].get_pixmap(dpi=100).samples


def test_small_footer_is_tiny_grey_text(tmp_path):
    spec = BY_ID["stress-injection-small_footer"]
    with pymupdf.open(render(tmp_path, spec)) as d:
        spans = [s for blk in d[0].get_text("dict")["blocks"] for ln in blk.get("lines", [])
                 for s in ln["spans"] if "SYSTEM MESSAGE" in s["text"]]
    assert spans and all(s["size"] <= 6 and s["color"] != 0 for s in spans)
    assert all(s["bbox"][1] > 792 - 40 for s in spans)


# ---- degradations and handwriting ----------------------------------------------------------

@pytest.mark.parametrize("deg", DEGRADATIONS)
def test_degraded_output_is_image_only(tmp_path, deg):
    spec = copy.deepcopy(BY_ID["sample-long"])
    plain = len(page_texts(render(tmp_path, spec, "plain")))
    spec["degradations"] = [deg]
    pdf = render(tmp_path, spec, deg)
    with pymupdf.open(pdf) as d:
        assert len(d) == plain
        for p in d:
            assert p.get_text().strip() == ""
            assert len(p.get_images()) == 1
            landscape = p.rect.width > p.rect.height
            assert landscape == (deg == "rotate90")


def test_degradation_combo_keeps_pages(tmp_path):
    spec = copy.deepcopy(BY_ID["sample-harlow"])
    spec["degradations"] = ["scan", "rotate90", "skew", "noise", "fax"]
    with pymupdf.open(render(tmp_path, spec)) as d:
        assert len(d) == 1 and d[0].get_text().strip() == ""
        assert d[0].rect.width > d[0].rect.height


def test_handwritten_is_a_rasterised_form(tmp_path):
    spec = next(s for s in po_samples() if s.get("handwritten"))
    raw = build_pdf_bytes(spec, FONTS)
    with pymupdf.open(stream=raw, filetype="pdf") as d:
        fonts = {f[3] for f in d[0].get_fonts()}
        text = squash(d[0].get_text())
    assert any("Kalam" in f for f in fonts)
    assert "PART NO." in text           # form_boxes labels, whatever spec["layout"] says
    with pymupdf.open(render(tmp_path, spec)) as d:
        assert all(p.get_text().strip() == "" for p in d)


# ---- determinism ---------------------------------------------------------------------------

@pytest.mark.parametrize("layout", LAYOUTS)
def test_same_spec_same_output(tmp_path, layout):
    spec = spec_for("sample-orchard", layout)
    a, b = render(tmp_path, spec, "a"), render(tmp_path, spec, "b")
    assert page_texts(a) == page_texts(b)
    assert a.read_bytes() == b.read_bytes()


def test_degraded_output_is_deterministic(tmp_path):
    spec = copy.deepcopy(BY_ID["sample-harlow"])
    spec["degradations"] = ["scan", "skew", "noise"]
    a, b = render(tmp_path, spec, "a"), render(tmp_path, spec, "b")
    assert a.read_bytes() == b.read_bytes()
    spec["seed"] += 1
    c = render(tmp_path, spec, "c")
    assert c.read_bytes() != a.read_bytes()


def test_bad_spec_is_rejected(tmp_path):
    spec = copy.deepcopy(BY_ID["sample-harlow"])
    spec["layout"] = "no_such_layout"
    with pytest.raises(ValueError):
        render(tmp_path, spec)
