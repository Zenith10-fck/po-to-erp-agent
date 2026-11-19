"""Parsing and normalising printed values. Pure functions, no I/O.

Every parser returns None when the text is not clearly a value of that type.
The gates treat None as "not proven", never as zero.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

_WS = re.compile(r"\s+")
_NUM = re.compile(r"^\d+(\.\d+)?$")
_COMPANY_SUFFIX = {
    "inc", "incorporated", "llc", "ltd", "limited", "corp", "corporation", "co", "company", "lp", "plc",
}
_DATE_FORMATS = (
    "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%Y-%m-%d", "%Y/%m/%d",
    "%d-%b-%Y", "%d-%B-%Y", "%d %b %Y", "%d %B %Y",
    "%b %d, %Y", "%B %d, %Y", "%b %d %Y", "%B %d %Y", "%b. %d, %Y",
)


def squash(text: str | None) -> str:
    """Collapse all whitespace to single spaces and trim."""
    return _WS.sub(" ", text or "").strip()


def parse_number(text: str | None) -> Decimal | None:
    """'1,234.50', '$1,234.50', 'USD 86.40', '5' -> Decimal. Anything unclear -> None."""
    if text is None:
        return None
    t = squash(text)
    t = re.sub(r"(?i)^(usd|us\$|\$)\s*", "", t)
    t = re.sub(r"(?i)\s*(usd)$", "", t)
    if re.search(r",\d{3}(\D|$)", t):
        t = t.replace(",", "")
    if not _NUM.match(t):
        return None
    try:
        return Decimal(t)
    except InvalidOperation:
        return None


def parse_date(text: str | None) -> date | None:
    """Parse the date formats the test set (and most US POs) use. Slash dates are month first."""
    if text is None:
        return None
    t = squash(text).replace("Sept ", "Sep ").replace("Sept.", "Sep.")
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            continue
    return None


# Cyrillic and Greek letters that look like Latin ones. Folded so "РО-48213" (Cyrillic)
# and "PO-48213" count as the same PO in the duplicate check.
_LOOKALIKE = str.maketrans(
    "АВЕКМНОРСТУХаеорсухіјѕԁԛԝΑΒΕΖΗΙΚΜΝΟΡΤΥΧοιν",
    "ABEKMHOPCTYXaeopcyxijsdqwABEZHIKMNOPTYXoiv",
)


def norm_code(text: str | None) -> str:
    """Part numbers, PO numbers, account numbers: fold width and look-alike letters, drop
    spaces and dashes, upper case."""
    t = unicodedata.normalize("NFKC", text or "").translate(_LOOKALIKE)
    return re.sub(r"[\s\-_./‐-―]", "", t).upper()


def norm_tokens(text: str | None) -> list[str]:
    """Lower-case alphanumeric tokens."""
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def norm_name(text: str | None) -> str:
    """Company or site name for matching: tokens without legal suffixes."""
    toks = [t for t in norm_tokens(text) if t not in _COMPANY_SUFFIX]
    return " ".join(toks)


def norm_address(text: str | None) -> str:
    return " ".join(norm_tokens(text))


def norm_currency(text: str | None) -> str | None:
    t = squash(text).upper()
    if t in ("$", "USD", "US$", "US DOLLARS", "US DOLLAR", "U.S. DOLLARS", "DOLLARS"):
        return "USD"
    return t or None


def fmt_decimal(value: Decimal, places: int) -> str:
    q = Decimal(1).scaleb(-places)
    return str(value.quantize(q))


def fmt_qty(value: Decimal) -> str:
    """Quantity without useless zeros: 5 not 5.00, 2.5 stays 2.5."""
    if value == value.to_integral_value():
        return str(int(value))
    return format(value.normalize(), "f")
