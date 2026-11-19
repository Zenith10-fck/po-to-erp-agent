"""Checks for Part A of the test-set generator (master data, scenarios, answer keys, emails).

Fast: nothing is rendered. Some tests run the real master-data and math gates on a perfect
extraction built from the printed strings. That is a consistency test of the data; the answer
key itself is still built from how each scenario was constructed.
"""
from __future__ import annotations

import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "test-set" / "generator"
sys.path.insert(0, str(GEN))
sys.path.insert(0, str(ROOT / "src"))

import cli  # noqa: E402
import emails  # noqa: E402
import master_data  # noqa: E402
import scenarios  # noqa: E402
from po_agent.gates import checks, evidence  # noqa: E402
from po_agent.gates.master_data import check_master_data, match_customer  # noqa: E402
from po_agent.intake import read_eml  # noqa: E402
from po_agent.masterdata import MasterData  # noqa: E402
from po_agent.normalize import norm_code, norm_name, parse_date, parse_number  # noqa: E402
from po_agent.writer import build_rows  # noqa: E402

LINE_FIELDS = ("line_no", "item_no", "customer_part_no", "description", "qty", "uom",
               "unit_price", "line_total", "requested_date")
ROW_FIELDS = ("customer_id", "customer_po_number", "po_date", "bill_to_id", "ship_to_id", "currency",
              "carrier_account_no", "shipping_notes")
LINE_ROW_FIELDS = ("line_no", "item_id", "customer_part_no", "order_qty", "order_uom", "base_qty",
                   "base_uom", "unit_price", "line_total", "requested_date")


@pytest.fixture(scope="module")
def data(tmp_path_factory):
    folder = tmp_path_factory.mktemp("master")
    master_data.write_master(folder)
    tables = master_data.read_master(folder)           # recompute everything from the CSV files
    md = MasterData.load(folder)
    scs = scenarios.build_all(master_data.Master(tables))
    return {"tables": tables, "md": md, "scs": scs, "master": master_data.Master(tables)}


def fld(v):
    return {"value": v, "page": 1 if v is not None else None, "quote": v}


def perfect_extraction(spec: dict) -> dict:
    def join(block):
        return ", ".join(block["address_lines"]) if block else None
    carrier = spec["carrier"] or {}
    return {
        "legibility": "clear", "po_pages": [1], "ignored_pages": [],
        "suspicious_content": {"present": False, "page": None, "quote": None},
        "po_number": fld(spec["po_number"]), "po_date": fld(spec["po_date"]),
        "customer_name": fld(spec["buyer"]["name"]),
        "bill_to_name": fld(spec["bill_to"]["name"] if spec["bill_to"] else None),
        "bill_to_address": fld(join(spec["bill_to"])),
        "ship_to_name": fld(spec["ship_to"]["name"] if spec["ship_to"] else None),
        "ship_to_address": fld(join(spec["ship_to"])),
        "currency": fld(spec["currency"]), "order_total": fld(spec["order_total"]),
        "carrier_name": fld(carrier.get("name")), "carrier_account_no": fld(carrier.get("account_no")),
        "shipping_notes": fld(spec["shipping_notes"]),
        "lines": [{k: fld(line[k]) for k in LINE_FIELDS} for line in spec["lines"]],
    }


def pos(scs):
    return [s for s in scs if s.spec["kind"] == "po"]


def gate_codes(md, spec):
    ex = perfect_extraction(spec)
    matched, findings = check_master_data(md, ex)
    findings += checks.check_math(ex) + evidence.check_required(ex)
    return matched, findings


# ---------------------------------------------------------------------------
# master data
# ---------------------------------------------------------------------------
def test_master_data_sizes(data):
    t = data["tables"]
    assert len(t["customers"]) == 25
    assert 50 <= len(t["ship_tos"]) <= 70
    assert len(t["items"]) == 300
    legacy = sum(1 for i in t["items"] if i["legacy_item_no"])
    assert 0.33 <= legacy / 300 <= 0.47
    assert 3 <= sum(1 for i in t["items"] if i["active"] == "N") <= 15
    ship_count = Counter(s["customer_id"] for s in t["ship_tos"])
    assert any(n == 1 for n in ship_count.values()) and any(n >= 4 for n in ship_count.values())
    assert len({p["customer_id"] for p in t["customer_parts"]}) >= 10
    assert len({a["customer_id"] for a in t["carrier_accounts"]}) >= 10
    assert {p["price_list_id"] for p in t["price_lists"]} == {"PL-A", "PL-B", "PL-C"}
    have = {a["alias"] for a in t["uom_aliases"]}
    for a in ["each", "ea", "ea.", "pcs", "pc", "case", "cs", "ctn", "box", "bx", "pack", "pk",
              "roll", "rl", "ft", "lb"]:
        assert a in have
    assert "pallet" not in have and "plt" not in have


def test_master_referential_integrity(data):
    t = data["tables"]
    cust = {c["customer_id"]: c for c in t["customers"]}
    items = {i["item_id"]: i for i in t["items"]}
    assert len(cust) == len(t["customers"]) and len(items) == len(t["items"])
    assert len({c["bill_to_id"] for c in t["customers"]}) == len(cust)
    assert len({s["ship_to_id"] for s in t["ship_tos"]}) == len(t["ship_tos"])
    assert all(s["customer_id"] in cust for s in t["ship_tos"])
    assert all(p["customer_id"] in cust and p["item_id"] in items for p in t["customer_parts"])
    assert all(a["customer_id"] in cust for a in t["carrier_accounts"])
    codes = {a["uom"] for a in t["uom_aliases"]}
    assert {i["base_uom"] for i in t["items"]} <= codes
    for c in t["uom_conversions"]:
        assert c["item_id"] in items and c["from_uom"] in codes
        assert int(c["factor"]) > 1 and c["from_uom"] != items[c["item_id"]]["base_uom"]
    # every active item is on every list, in its base unit, 2 decimals; inactive items on none
    priced = {(p["price_list_id"], p["item_id"]): p for p in t["price_lists"]}
    for plist in ("PL-A", "PL-B", "PL-C"):
        for iid, it in items.items():
            if it["active"] == "Y":
                p = priced[(plist, iid)]
                assert p["uom"] == it["base_uom"]
                assert Decimal(p["unit_price"]) == Decimal(p["unit_price"]).quantize(Decimal("0.01")) > 0
            else:
                assert (plist, iid) not in priced
    # legacy numbers unique and never equal to another kind of number
    legacy = [norm_code(i["legacy_item_no"]) for i in t["items"] if i["legacy_item_no"]]
    assert len(legacy) == len(set(legacy))
    assert not set(legacy) & {norm_code(i) for i in items}
    assert not set(legacy) & {norm_code(p["customer_part_no"]) for p in t["customer_parts"]}
    # a customer never has one part number for two items
    seen = Counter((p["customer_id"], norm_code(p["customer_part_no"])) for p in t["customer_parts"])
    assert max(seen.values()) == 1


def test_shared_customer_part_number(data):
    rows = data["tables"]["customer_parts"]
    by_no: dict[str, set[tuple[str, str]]] = {}
    for p in rows:
        by_no.setdefault(norm_code(p["customer_part_no"]), set()).add((p["customer_id"], p["item_id"]))
    shared = [v for v in by_no.values()
              if len({c for c, _ in v}) >= 2 and len({i for _, i in v}) >= 2]
    assert len(shared) >= 1


def test_every_name_matches_its_own_customer(data):
    md = data["md"]
    for c in data["tables"]["customers"]:
        for n in [c["name"]] + [a for a in c["aliases"].split(";") if a]:
            assert match_customer(md, n) == (c["customer_id"], "ok"), n


def test_ambiguity_pairs_are_ambiguous(data):
    md = data["md"]
    cust = {c["customer_id"]: c for c in data["tables"]["customers"]}
    for a, b in master_data.NEAR_IDENTICAL_PAIRS:
        assert match_customer(md, cust[a]["name"]) == (a, "ok")
        assert match_customer(md, cust[b]["name"]) == (b, "ok")
    assert match_customer(md, "Kessler Machine") == (None, "ambiguous")
    assert match_customer(md, "Brightwater Tool") == (None, "ambiguous")
    trap = [s for s in data["scs"] if s.trap == "ambiguous_customer"]
    assert trap
    for s in trap:
        assert match_customer(md, s.spec["buyer"]["name"]) == (None, "ambiguous")
        assert match_customer(md, s.spec["bill_to"]["name"]) == (None, "ambiguous")


# ---------------------------------------------------------------------------
# scenarios: shape and split rules
# ---------------------------------------------------------------------------
def test_twenty_per_split_and_ids(data):
    scs = data["scs"]
    split = Counter(s.split for s in scs)
    assert split == {"dev": 20, "heldout": 20}
    ids = [s.doc_id for s in scs]
    assert len(ids) == len(set(ids))
    for s in scs:
        assert s.spec["doc_id"] == s.key["doc_id"] == s.doc_id
        assert s.spec["split"] == s.key["split"] == s.split
        assert s.spec["seed"] == s.seed
        if s.split == "dev":
            assert s.doc_id.startswith("dev-") and 1001 <= s.seed <= 1020
        else:
            assert s.doc_id.startswith("held-") and 5001 <= s.seed <= 5020


def test_category_mix_per_split(data):
    want = {"clean": 3, "layout": 1, "scan": 4, "handwritten": 1, "multipage": 2, "trap": 5,
            "injection": 1, "non_po": 3}
    traps = {}
    for split in ("dev", "heldout"):
        part = [s for s in data["scs"] if s.split == split]
        assert Counter(s.category for s in part) == want
        traps[split] = {c for s in part if s.category == "trap" for c in s.key["expected_reason_codes"]}
        assert {"R06", "R10"} <= traps[split]
        assert any(s.category == "injection" and "R13" in s.key["expected_reason_codes"] for s in part)
        assert {s.key["doc_type"] for s in part if s.category == "non_po"} == {"invoice", "quote_request", "newsletter"}
        assert sorted(s.spec["degradations"] for s in part if s.category == "scan") == sorted(
            [["scan"], ["scan", "rotate90"], ["skew", "noise"], ["fax", "rotate180"]])
        assert sum(len(s.spec["lines"]) >= 25 for s in part) == 1
        assert sum(s.spec["extra_pages"] == ["cover", "terms"] for s in part) == 1
        assert sum(s.spec["handwritten"] for s in part) == 1
    assert traps["dev"] | traps["heldout"] == {"R01", "R02", "R04", "R05", "R06", "R07", "R10", "R12"}


def test_each_trap_is_one_planted_problem(data):
    for s in data["scs"]:
        if s.category == "trap":
            assert s.key["expected_route"] == "review" and len(s.key["expected_reason_codes"]) == 1
            assert not s.spec["degradations"] and not s.spec["handwritten"]


def test_expected_routes(data):
    for s in data["scs"]:
        k = s.key
        if s.category == "non_po":
            assert k["expected_route"] == "ignored" and not k["is_po"] and k["truth"] is None
        elif s.trap is None:
            assert k["expected_route"] == "auto" and k["expected_reason_codes"] == []
            degraded = bool(s.spec["degradations"]) or s.spec["handwritten"]
            assert k["acceptable_review_codes"] == (["R09", "R11"] if degraded else [])
        else:
            assert k["expected_route"] == "review" and k["expected_reason_codes"]


def test_known_layout_and_degradation_ids(data):
    for s in data["scs"]:
        assert s.spec["layout"] in cli.LAYOUTS
        assert set(s.spec["degradations"]) <= set(cli.DEGRADATIONS)
        assert s.spec["kind"] in ("po", "invoice", "quote_request", "newsletter")
        assert s.spec["injection_style"] in (None, "visible_note", "small_footer", "white_text")
        if s.spec["injection_style"] == "white_text":
            assert not s.spec["degradations"] and not s.spec["handwritten"]
    dev_layouts = {s.spec["layout"] for s in pos(data["scs"]) if s.split == "dev"}
    assert len(dev_layouts) == 8


def test_heldout_never_repeats_a_dev_layout_trap_combination(data):
    def combos(split):
        return {(s.spec["layout"], s.trap) for s in data["scs"] if s.split == split and s.trap}
    assert not combos("dev") & combos("heldout")
    clean = [s for s in data["scs"] if s.category == "clean"]
    for split in ("dev", "heldout"):
        assert len({s.spec["layout"] for s in clean if s.split == split}) == 3


def _customers(s):
    if s.key["truth"]:
        return {s.key["truth"]["customer_id"]}
    if s.spec["kind"] == "quote_request":
        return {scenarios.PLANS[s.split][int(s.doc_id[-3:]) - 1]["customer"]}
    return set()


def _items(s):
    out = set()
    if s.key["truth"]:
        out |= {ln["item_id"] for ln in s.key["truth"]["lines"] if ln["item_id"]}
    if s.spec["kind"] == "quote_request":
        out |= {ln["item_no"] for ln in s.spec["lines"]}
    return out


def test_no_customer_item_or_po_shared_between_splits(data):
    scs = data["scs"]
    cust = {sp: set().union(*[_customers(s) for s in scs if s.split == sp]) for sp in ("dev", "heldout")}
    items = {sp: set().union(*[_items(s) for s in scs if s.split == sp]) for sp in ("dev", "heldout")}
    pos_ = {sp: {norm_code(s.spec["po_number"]) for s in scs if s.split == sp and s.spec["po_number"]}
            for sp in ("dev", "heldout")}
    assert cust["dev"] and cust["heldout"] and not cust["dev"] & cust["heldout"]
    assert items["dev"] and items["heldout"] and not items["dev"] & items["heldout"]
    assert not pos_["dev"] & pos_["heldout"]


def test_po_numbers_unique_except_the_duplicate(data):
    nums = Counter(norm_code(s.spec["po_number"]) for s in data["scs"] if s.spec["po_number"])
    dups = {n for n, c in nums.items() if c > 1}
    planted = set()
    for s in data["scs"]:
        if s.trap == "duplicate_po":
            orig = next(o for o in data["scs"] if o.doc_id == s.key["trap_detail"]["duplicate_of"])
            assert orig.doc_id < s.doc_id and orig.split == s.split
            assert orig.key["expected_route"] == "auto"
            assert orig.spec["po_number"] == s.spec["po_number"]
            assert orig.key["truth"]["customer_id"] == s.key["truth"]["customer_id"]
            planted.add(norm_code(s.spec["po_number"]))
    assert dups == planted and len(planted) == 2
    assert all(nums[n] == 2 for n in planted)


def test_deterministic(data):
    again = scenarios.build_all(data["master"])
    assert [s.spec for s in again] == [s.spec for s in data["scs"]]
    assert [s.key for s in again] == [s.key for s in data["scs"]]


# ---------------------------------------------------------------------------
# printed values
# ---------------------------------------------------------------------------
def test_all_printed_dates_and_numbers_parse(data):
    for s in data["scs"]:
        sp = s.spec
        assert parse_date(sp["po_date"]) is not None, (s.doc_id, sp["po_date"])
        if sp["order_total"]:
            assert parse_number(sp["order_total"]) is not None
        for ln in sp["lines"]:
            assert parse_number(ln["qty"]) is not None
            for f in ("unit_price", "line_total"):
                if ln[f] is not None:
                    assert parse_number(ln[f]) is not None, (s.doc_id, ln[f])
            if ln["requested_date"]:
                assert parse_date(ln["requested_date"]) is not None
        if s.key["truth"]:
            assert parse_date(sp["po_date"]).isoformat() == s.key["truth"]["po_date"]


def test_printed_formats_vary(data):
    scs = pos(data["scs"])
    styles = set()
    for s in scs:
        d = s.spec["po_date"]
        styles.add("slash" if "/" in d else "iso" if d[:4].isdigit() else "dmy" if d[:2].isdigit() else "month")
    assert styles == {"slash", "iso", "dmy", "month"}
    assert any(s.spec["order_total"].startswith("$") for s in scs)
    assert any("," in s.spec["order_total"] and not s.spec["order_total"].startswith("$") for s in scs)
    uoms = {ln["uom"] for s in scs for ln in s.spec["lines"]}
    assert {"EA", "each"} <= uoms or {"ea", "each"} <= uoms
    assert len(uoms) >= 10


def test_math_is_right_except_r07(data):
    for s in data["scs"]:
        lines = [ln for ln in s.spec["lines"] if ln["unit_price"] is not None]
        if not lines:
            continue
        errors = 0
        total = Decimal(0)
        for ln in lines:
            lt = parse_number(ln["line_total"])
            total += lt
            if parse_number(ln["qty"]) * parse_number(ln["unit_price"]) != lt:
                errors += 1
        assert total == parse_number(s.spec["order_total"]), s.doc_id
        assert errors == (1 if s.trap == "math_mismatch" else 0), s.doc_id


def test_pack_units_print_the_pack_price(data):
    m = data["master"]
    found = 0
    for s in pos(data["scs"]):
        if s.trap in ("unknown_uom", "unknown_item", "price_off_5pct", "injection_hidden_text"):
            continue
        for ln in s.key["truth"]["lines"]:
            if ln["order_uom"] != ln["base_uom"]:
                found += 1
                f = m.factor(ln["item_id"], ln["order_uom"])
                assert Decimal(ln["base_qty"]) == Decimal(ln["order_qty"]) * f
                assert Decimal(ln["unit_price"]) == m.list_price(s.key["truth"]["customer_id"], ln["item_id"], ln["order_uom"])
    assert found >= 6


def test_names_and_ship_to_addresses_match_master(data):
    m = data["master"]
    for s in pos(data["scs"]):
        t = s.key["truth"]
        cust = m.customers[t["customer_id"]]
        names = {norm_name(n) for n in [cust["name"]] + cust["aliases"].split(";") if n}
        if s.trap != "ambiguous_customer":
            assert norm_name(s.spec["buyer"]["name"]) in names
            assert norm_name(s.spec["bill_to"]["name"]) in names
        ship = next(x for x in m.ship_tos[t["customer_id"]] if x["ship_to_id"] == t["ship_to_id"])
        assert ", ".join(s.spec["ship_to"]["address_lines"]) == ship["address"]
        assert ", ".join(s.spec["bill_to"]["address_lines"]) == cust["bill_to_address"]


def test_no_instruction_like_text_outside_injection_docs(data):
    def strings(obj):
        if isinstance(obj, str):
            yield obj
        elif isinstance(obj, dict):
            for v in obj.values():
                yield from strings(v)
        elif isinstance(obj, list):
            for v in obj:
                yield from strings(v)
    for s in data["scs"]:
        texts = list(strings(s.spec)) + [s.email["subject"], s.email["body"]]
        hits = [t for t in texts for rx in checks._INJECTION_RE if rx.search(t)]
        if s.category == "injection":
            assert s.spec["injection_text"] in hits
        else:
            assert hits == [], (s.doc_id, hits)


# ---------------------------------------------------------------------------
# answer key against the master data and the real gates
# ---------------------------------------------------------------------------
def test_auto_truth_lines_exist_with_list_price(data):
    t = data["tables"]
    items = {i["item_id"]: i for i in t["items"]}
    price = {(p["price_list_id"], p["item_id"]): Decimal(p["unit_price"]) for p in t["price_lists"]}
    conv = {(c["item_id"], c["from_uom"]): int(c["factor"]) for c in t["uom_conversions"]}
    cust = {c["customer_id"]: c for c in t["customers"]}
    ships = {s["ship_to_id"]: s for s in t["ship_tos"]}
    parts = {(p["customer_id"], p["customer_part_no"]): p["item_id"] for p in t["customer_parts"]}
    for s in data["scs"]:
        k = s.key
        if k["expected_route"] != "auto":
            continue
        tr = k["truth"]
        c = cust[tr["customer_id"]]
        assert tr["bill_to_id"] == c["bill_to_id"] and tr["currency"] == c["currency"] == "USD"
        assert ships[tr["ship_to_id"]]["customer_id"] == tr["customer_id"]
        assert tr["customer_po_number"] == s.spec["po_number"]
        for n, ln in enumerate(tr["lines"], start=1):
            assert ln["line_no"] == n
            it = items[ln["item_id"]]
            assert it["active"] == "Y" and ln["base_uom"] == it["base_uom"]
            f = 1 if ln["order_uom"] == it["base_uom"] else conv[(ln["item_id"], ln["order_uom"])]
            assert Decimal(ln["unit_price"]) == price[(c["price_list_id"], ln["item_id"])] * f
            assert Decimal(ln["base_qty"]) == Decimal(ln["order_qty"]) * f
            assert Decimal(ln["line_total"]) == (Decimal(ln["order_qty"]) * Decimal(ln["unit_price"])).quantize(Decimal("0.01"))
            if ln["customer_part_no"]:
                assert parts[(tr["customer_id"], ln["customer_part_no"])] == ln["item_id"]


def test_real_gates_agree_on_every_expected_auto_document(data):
    md = data["md"]
    checked = 0
    for s in data["scs"]:
        if s.key["expected_route"] != "auto":
            continue
        matched, findings = gate_codes(md, s.spec)
        assert findings == [], (s.doc_id, [f.to_dict() for f in findings])
        tr = s.key["truth"]
        rows = build_rows(matched, s.key["source_file"], "run-test")
        assert len(rows) == len(tr["lines"])
        for row, ln in zip(rows, tr["lines"]):
            for f in ROW_FIELDS:
                assert row[f] == tr[f], (s.doc_id, f, row[f], tr[f])
            for f in LINE_ROW_FIELDS:
                assert str(row[f]) == str(ln[f]), (s.doc_id, f, row[f], ln[f])
        checked += 1
    assert checked == 22   # 11 per split


def test_real_gates_raise_exactly_the_planted_code(data):
    md = data["md"]
    for s in data["scs"]:
        if s.trap is None or s.trap == "duplicate_po":
            continue
        _, findings = gate_codes(md, s.spec)
        want = set(s.key["expected_reason_codes"]) - {"R13"}   # R13 comes from the page scan
        assert {f.code for f in findings} == want, (s.doc_id, [f.to_dict() for f in findings])
    for s in data["scs"]:
        if s.trap == "duplicate_po":
            assert gate_codes(md, s.spec)[1] == []   # a valid order; only the ledger makes it R10


def test_truth_of_trap_documents(data):
    for s in data["scs"]:
        tr = s.key["truth"]
        if s.trap == "missing_po_number":
            assert s.spec["po_number"] is None and tr["customer_po_number"] is None
        if s.trap == "carrier_not_on_file":
            assert s.spec["carrier"]["account_no"] and tr["carrier_account_no"] == ""
        if s.trap == "unknown_uom":
            assert any(ln["order_uom"] is None for ln in tr["lines"])
        if s.trap == "unknown_item":
            assert any(ln["item_id"] is None for ln in tr["lines"])


# ---------------------------------------------------------------------------
# emails
# ---------------------------------------------------------------------------
def test_emails_round_trip(data, tmp_path):
    for s in data["scs"]:
        frm = s.email["from"]
        assert frm.split("@")[1].rstrip(">").endswith(".example")
        assert s.email["to"].rstrip(">").endswith(".example")
        path = emails.write_eml(tmp_path / f"{s.doc_id}.eml", s.email, s.doc_id, b"%PDF-1.4 test")
        mail = read_eml(path)
        assert mail.doc_id == s.doc_id
        assert mail.attachments == [(s.email["attachment"], b"%PDF-1.4 test")]
        assert mail.subject == s.email["subject"] and mail.body
        if s.trap == "missing_po_number":
            assert not any(ch.isdigit() for ch in s.email["subject"] + s.email["attachment"])
