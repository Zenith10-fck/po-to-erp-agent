"""Shared types for the gates."""
from __future__ import annotations

from dataclasses import asdict, dataclass

REASONS = {
    "R01": "PO number missing",
    "R02": "Customer not matched",
    "R03": "Ship-to not matched",
    "R04": "Item not matched",
    "R05": "Unit of measure problem",
    "R06": "Price problem",
    "R07": "Math mismatch",
    "R08": "Value not proven",
    "R09": "Dual-read disagreement",
    "R10": "Duplicate PO",
    "R11": "Low legibility",
    "R12": "Carrier account problem",
    "R13": "Suspicious content",
    "R14": "Model output unusable",
}


@dataclass
class Finding:
    """One failed check. `scope` is 'order' or 'line N'."""
    code: str
    scope: str
    field: str
    read: str | None = None       # what the model read
    expected: str | None = None   # what the gate expected (list price, computed total ...)
    page: int | None = None
    note: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["name"] = REASONS[self.code]
        return d


def val(field: dict | None) -> str | None:
    """The printed value of an extracted field, or None when empty."""
    if not field:
        return None
    v = field.get("value")
    if v is None:
        return None
    v = str(v).strip()
    return v or None
