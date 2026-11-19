"""Loads the master data CSVs (see docs/master-data-spec.md) into lookup tables."""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from .normalize import norm_code, norm_name, squash


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return [{k: (v or "").strip() for k, v in r.items()} for r in csv.DictReader(f)]


@dataclass
class MasterData:
    customers: dict[str, dict] = field(default_factory=dict)           # customer_id -> row
    customer_names: list[tuple[str, str]] = field(default_factory=list)  # (normalised name or alias, customer_id)
    ship_tos: dict[str, list[dict]] = field(default_factory=dict)      # customer_id -> rows
    items: dict[str, dict] = field(default_factory=dict)               # item_id -> row
    item_by_code: dict[str, str] = field(default_factory=dict)         # norm item_id -> item_id
    legacy_by_code: dict[str, list[str]] = field(default_factory=dict) # norm legacy no -> item_ids
    customer_parts: dict[tuple[str, str], list[str]] = field(default_factory=dict)  # (customer_id, norm part) -> item_ids
    conversions: dict[tuple[str, str], Decimal] = field(default_factory=dict)       # (item_id, uom) -> factor
    uom_alias: dict[str, str] = field(default_factory=dict)            # lower alias -> code
    prices: dict[tuple[str, str], tuple[str, Decimal]] = field(default_factory=dict)  # (price_list, item) -> (uom, price)
    carrier_accounts: dict[str, set[str]] = field(default_factory=dict)  # customer_id -> norm account numbers

    @classmethod
    def load(cls, folder: Path) -> "MasterData":
        md = cls()
        for r in _rows(folder / "customers.csv"):
            if r.get("active", "Y").upper() == "N":
                continue
            md.customers[r["customer_id"]] = r
            names = [r["name"]] + [a for a in r.get("aliases", "").split(";") if a.strip()]
            for n in names:
                md.customer_names.append((norm_name(n), r["customer_id"]))
        for r in _rows(folder / "ship_tos.csv"):
            md.ship_tos.setdefault(r["customer_id"], []).append(r)
        for r in _rows(folder / "items.csv"):
            md.items[r["item_id"]] = r
            md.item_by_code[norm_code(r["item_id"])] = r["item_id"]
            if r.get("legacy_item_no"):
                md.legacy_by_code.setdefault(norm_code(r["legacy_item_no"]), []).append(r["item_id"])
        for r in _rows(folder / "customer_parts.csv"):
            key = (r["customer_id"], norm_code(r["customer_part_no"]))
            md.customer_parts.setdefault(key, []).append(r["item_id"])
        for r in _rows(folder / "uom_conversions.csv"):
            md.conversions[(r["item_id"], r["from_uom"].upper())] = Decimal(r["factor"])
        for r in _rows(folder / "uom_aliases.csv"):
            md.uom_alias[squash(r["alias"]).lower().rstrip(".")] = r["uom"].upper()
        for r in _rows(folder / "price_lists.csv"):
            md.prices[(r["price_list_id"], r["item_id"])] = (r["uom"].upper(), Decimal(r["unit_price"]))
        for r in _rows(folder / "carrier_accounts.csv"):
            md.carrier_accounts.setdefault(r["customer_id"], set()).add(norm_code(r["account_no"]))
        return md

    def uom_code(self, printed: str | None) -> str | None:
        """'case', 'Cs.', 'EA' -> 'CS', 'CS', 'EA'. Unknown text -> None."""
        t = squash(printed).lower().rstrip(".")
        if not t:
            return None
        if t in self.uom_alias:
            return self.uom_alias[t]
        known = set(self.uom_alias.values()) | {i["base_uom"].upper() for i in self.items.values()}
        return t.upper() if t.upper() in known else None

    def factor(self, item_id: str, uom: str) -> Decimal | None:
        """How many base units are in one `uom` of this item. None = no conversion on file."""
        item = self.items[item_id]
        if uom == item["base_uom"].upper():
            return Decimal(1)
        return self.conversions.get((item_id, uom))
