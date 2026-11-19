"""Master-data gate. Matches the printed order to ERP records and checks unit and price.

The IDs that end up in the CSV come from here, never from the model.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from rapidfuzz import fuzz

from ..masterdata import MasterData
from ..normalize import norm_address, norm_code, norm_currency, norm_name, parse_date, parse_number, squash
from .base import Finding, val

NAME_MIN = 92            # token_set_ratio needed for a name or address match
MARGIN = 5               # the best match must beat the second best by this much
PRICE_ABS = Decimal("0.01")
PRICE_REL = Decimal("0.005")


@dataclass
class MatchedLine:
    line_no: int
    item_id: str | None = None
    customer_part_no: str = ""
    order_qty: Decimal | None = None
    order_uom: str | None = None
    base_qty: Decimal | None = None
    base_uom: str | None = None
    unit_price: Decimal | None = None
    list_price: Decimal | None = None
    line_total_printed: Decimal | None = None
    requested_date: str = ""


@dataclass
class Matched:
    customer_id: str | None = None
    customer_name: str | None = None      # the master-data name, not the printed one
    bill_to_id: str | None = None
    ship_to_id: str | None = None
    currency: str | None = None
    po_number: str = ""
    po_date: str = ""
    carrier_account_no: str = ""
    shipping_notes: str = ""
    order_total_printed: Decimal | None = None
    lines: list[MatchedLine] = field(default_factory=list)


def _best(scores: dict[str, float]) -> tuple[str | None, str]:
    """Pick the winner from {id: score}. Returns (id or None, 'ok' | 'none' | 'ambiguous')."""
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    if not ranked or ranked[0][1] < NAME_MIN:
        return None, "none"
    if len(ranked) > 1 and ranked[0][1] - ranked[1][1] < MARGIN:
        return None, "ambiguous"
    return ranked[0][0], "ok"


def match_customer(md: MasterData, printed: str | None) -> tuple[str | None, str]:
    name = norm_name(printed)
    if not name:
        return None, "none"
    exact = {cid for n, cid in md.customer_names if n == name}
    if len(exact) == 1:
        return exact.pop(), "ok"
    if len(exact) > 1:
        return None, "ambiguous"
    scores: dict[str, float] = {}
    for n, cid in md.customer_names:
        scores[cid] = max(scores.get(cid, 0), fuzz.token_set_ratio(name, n))
    return _best(scores)


def match_ship_to(md: MasterData, customer_id: str, name: str | None, address: str | None) -> tuple[str | None, str]:
    rows = md.ship_tos.get(customer_id, [])
    n, a = norm_name(name), norm_address(address)
    scores: dict[str, float] = {}
    for r in rows:
        if a:
            # the address decides; the printed block may include the site name, so use token_set
            scores[r["ship_to_id"]] = fuzz.token_set_ratio(a, norm_address(r["address"]))
        elif n:
            scores[r["ship_to_id"]] = fuzz.token_set_ratio(n, norm_name(r["name"]))
    return _best(scores)


def match_item(md: MasterData, customer_id: str, numbers: list[str]) -> tuple[str | None, str]:
    """Every printed number is tried as our item number, the customer's part number and a legacy
    number. Exactly one item must come out."""
    found: set[str] = set()
    for raw in numbers:
        code = norm_code(raw)
        if not code:
            continue
        if code in md.item_by_code:
            found.add(md.item_by_code[code])
        found.update(md.customer_parts.get((customer_id, code), []))
        found.update(md.legacy_by_code.get(code, []))
    if not found:
        return None, "none"
    if len(found) > 1:
        return None, "ambiguous"
    item_id = found.pop()
    if md.items[item_id].get("active", "Y").upper() == "N":
        return None, "inactive"
    return item_id, "ok"


def check_master_data(md: MasterData, ex: dict) -> tuple[Matched, list[Finding]]:
    out = Matched()
    findings: list[Finding] = []

    def add(code, scope, name, read=None, expected=None, note="", f=None):
        findings.append(Finding(code, scope, name, read=read, expected=expected,
                                page=(f or {}).get("page"), note=note))

    out.po_number = squash(val(ex.get("po_number")) or "")
    po_date_raw = val(ex.get("po_date"))
    if po_date_raw:
        d = parse_date(po_date_raw)
        if d is None:
            add("R08", "order", "po_date", read=po_date_raw, note="date format not understood", f=ex.get("po_date"))
        else:
            out.po_date = d.isoformat()
    out.shipping_notes = squash(val(ex.get("shipping_notes")) or "")
    total_raw = val(ex.get("order_total"))
    if total_raw:
        out.order_total_printed = parse_number(total_raw)
        if out.order_total_printed is None:
            add("R08", "order", "order_total", read=total_raw, note="number format not understood", f=ex.get("order_total"))

    # 1 customer
    cust_raw = val(ex.get("customer_name"))
    cid, how = match_customer(md, cust_raw)
    if cid is None:
        if cust_raw:
            add("R02", "order", "customer_name", read=cust_raw,
                note="two customers match equally well" if how == "ambiguous" else "no customer with this name",
                f=ex.get("customer_name"))
        return out, findings     # nothing else can be matched without a customer
    cust = md.customers[cid]
    out.customer_id, out.bill_to_id, out.currency = cid, cust["bill_to_id"], cust["currency"]
    out.customer_name = cust["name"]

    cur_raw = val(ex.get("currency"))
    if cur_raw and norm_currency(cur_raw) != cust["currency"]:
        add("R06", "order", "currency", read=cur_raw, expected=cust["currency"],
            note="currency differs from the customer's", f=ex.get("currency"))

    # 2 ship-to
    st_name, st_addr = val(ex.get("ship_to_name")), val(ex.get("ship_to_address"))
    if st_name or st_addr:
        sid, how = match_ship_to(md, cid, st_name, st_addr)
        if sid is None:
            add("R03", "order", "ship_to", read=squash(f"{st_name or ''} {st_addr or ''}"),
                note="two ship-tos match equally well" if how == "ambiguous" else "not a ship-to of this customer",
                f=ex.get("ship_to_address") or ex.get("ship_to_name"))
        out.ship_to_id = sid

    # 6 carrier account (only if printed)
    acct_raw = val(ex.get("carrier_account_no"))
    if acct_raw:
        if norm_code(acct_raw) in md.carrier_accounts.get(cid, set()):
            out.carrier_account_no = squash(acct_raw)
        else:
            add("R12", "order", "carrier_account_no", read=acct_raw,
                note="account number is not on file for this customer", f=ex.get("carrier_account_no"))

    # 3-5 lines
    for n, line in enumerate(ex.get("lines") or [], start=1):
        scope = f"line {n}"
        ml = MatchedLine(line_no=n, customer_part_no=squash(val(line.get("customer_part_no")) or ""))
        out.lines.append(ml)

        ml.order_qty = parse_number(val(line.get("qty")))
        if val(line.get("qty")) and (ml.order_qty is None or ml.order_qty <= 0):
            add("R08", scope, "qty", read=val(line.get("qty")), note="not a positive number", f=line.get("qty"))
            ml.order_qty = None
        ml.line_total_printed = parse_number(val(line.get("line_total")))
        if val(line.get("line_total")) and ml.line_total_printed is None:
            add("R08", scope, "line_total", read=val(line.get("line_total")), note="number format not understood", f=line.get("line_total"))
        req_raw = val(line.get("requested_date"))
        if req_raw:
            d = parse_date(req_raw)
            if d is None:
                add("R08", scope, "requested_date", read=req_raw, note="date format not understood", f=line.get("requested_date"))
            else:
                ml.requested_date = d.isoformat()

        numbers = [v for v in (val(line.get("item_no")), val(line.get("customer_part_no"))) if v]
        item_id, how = match_item(md, cid, numbers)
        if item_id is None:
            if numbers:
                note = {"none": "no item with this number", "ambiguous": "the numbers point to different items",
                        "inactive": "the item is inactive"}[how]
                add("R04", scope, "item", read=" / ".join(numbers), note=note,
                    f=line.get("item_no") if val(line.get("item_no")) else line.get("customer_part_no"))
            continue
        ml.item_id = item_id
        item = md.items[item_id]
        ml.base_uom = item["base_uom"].upper()

        uom_raw = val(line.get("uom"))
        uom = md.uom_code(uom_raw)
        factor = md.factor(item_id, uom) if uom else None
        if uom_raw and factor is None:
            add("R05", scope, "uom", read=uom_raw, expected=ml.base_uom,
                note="unknown unit" if uom is None else "no conversion from this unit for this item", f=line.get("uom"))
        if factor is not None:
            ml.order_uom = uom
            if ml.order_qty is not None:
                ml.base_qty = ml.order_qty * factor

        price_raw = val(line.get("unit_price"))
        price = parse_number(price_raw)
        listed = md.prices.get((cust["price_list_id"], item_id))
        if price_raw is None:
            add("R06", scope, "unit_price", note="no unit price on the PO")
        elif price is None:
            add("R06", scope, "unit_price", read=price_raw, note="number format not understood", f=line.get("unit_price"))
        elif listed is None:
            add("R06", scope, "unit_price", read=price_raw, note="item is not on the customer's price list", f=line.get("unit_price"))
        elif factor is not None:
            list_uom, list_price = listed
            list_factor = md.factor(item_id, list_uom)
            if list_factor is None:
                add("R06", scope, "unit_price", read=price_raw, note="price list unit cannot be converted", f=line.get("unit_price"))
            else:
                expected = list_price * factor / list_factor
                ml.list_price = expected
                diff = abs(price - expected)
                if diff > PRICE_ABS and diff > expected * PRICE_REL:
                    add("R06", scope, "unit_price", read=price_raw, expected=f"{expected:.4f}",
                        note=f"differs from the list price per {uom}", f=line.get("unit_price"))
                else:
                    ml.unit_price = price
    return out, findings
