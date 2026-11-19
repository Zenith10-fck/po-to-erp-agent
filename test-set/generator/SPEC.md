# Test-set generator contract

Two parts, two owners, one JSON contract between them.

- **Part A (data):** `master_data.py`, `scenarios.py`, `answer_key.py`, `emails.py`, `cli.py`.
  Makes master data, one *render spec* per document, the answer key and the `.eml` files.
- **Part B (rendering):** `render.py`, `layouts/*.py`, `degrade.py`.
  Turns one render spec into one PDF. Knows nothing about master data or the answer key.

Part A calls exactly one function from Part B:

```python
# test-set/generator/render.py
def render_document(spec: dict, out_pdf: pathlib.Path, fonts_dir: pathlib.Path) -> None: ...
LAYOUTS: list[str]        # all layout ids for kind == "po"
DEGRADATIONS: list[str]   # all degradation ids
```

Everything is deterministic: same spec -> same PDF bytes as far as the libraries allow. Any
randomness (noise, skew angle) uses `random.Random(spec["seed"])` or a numpy generator seeded
from it. No network access at generation time.

## Output tree (written by `cli.py`)

```
test-set/master-data/*.csv            see docs/master-data-spec.md
test-set/specs/<doc_id>.json          render spec (below)
test-set/<split>/<doc_id>.eml         email with the PDF attached (split = dev | heldout)
test-set/<split>/<doc_id>.pdf         the same PDF, loose, for viewing
test-set/answer-key/<doc_id>.json     answer key (below)
test-set/CASES.md                     one line per document: id, category, trap, expected route
```

`doc_id` = `dev-001` ... / `held-001` ... CLI: `uv run python test-set/generator/cli.py --all`
(also `--master-only`, `--split dev`, `--doc dev-007`).

## Render spec (`specs/<doc_id>.json`)

Everything in it is **what is printed**, as strings, exactly as it should appear on the page.

```json
{
  "doc_id": "dev-007",
  "split": "dev",
  "seed": 1007,
  "kind": "po",
  "layout": "classic_table",
  "degradations": ["scan", "rotate90"],
  "handwritten": false,
  "extra_pages": ["cover", "terms"],
  "buyer": {
    "name": "Harlow Fastener Supply Inc.",
    "address_lines": ["410 Mill Road", "Dayton, OH 45402"],
    "contact": "Purchasing: J. Ortega, 555-0142",
    "logo_text": "HARLOW"
  },
  "supplier": {
    "name": "Northfield Industrial Supply",
    "address_lines": ["1200 Commerce Pkwy", "Columbus, OH 43215"]
  },
  "po_number": "PO-48213",
  "po_number_label": "Purchase Order No.",
  "po_date": "10/02/2026",
  "bill_to": { "name": "Harlow Fastener Supply Inc.", "address_lines": ["410 Mill Road", "Dayton, OH 45402"] },
  "ship_to": { "name": "Harlow Plant 2", "address_lines": ["88 Foundry St", "Springfield, OH 45503"] },
  "currency": "USD",
  "carrier": { "name": "UPS", "account_no": "A1B2C3", "label": "Ship collect, UPS acct" },
  "shipping_notes": "Dock 3, call before delivery",
  "lines": [
    {
      "line_no": "1",
      "item_no": "IT-10442",
      "customer_part_no": "HF-2291",
      "description": "Hex bolt M8 x 40 zinc",
      "qty": "5",
      "uom": "CS",
      "unit_price": "86.40",
      "line_total": "432.00",
      "requested_date": "10/20/2026"
    }
  ],
  "order_total": "432.00",
  "order_total_label": "Total",
  "payment_terms": "Net 30",
  "injection_text": null,
  "injection_style": null
}
```

Rules:
- Any printed value may be `null` (or `""`): the layout then leaves it out (no label with an
  empty value, no placeholder like "N/A"). `carrier` may be `null`. `lines[].item_no`,
  `customer_part_no`, `unit_price`, `line_total`, `requested_date` may be `null`; a column that
  is `null` on every line is not drawn.
- `kind`: `po`, `invoice`, `quote_request`, `newsletter`. Non-PO kinds reuse the same fields
  where they make sense (an invoice has an invoice number in `po_number` with
  `po_number_label: "Invoice No."`); `newsletter` uses `"body_paragraphs": [...]` and a
  `"title"`. Non-PO kinds ignore `layout` and have their own simple layouts.
- `layout`: one of `render.LAYOUTS` (at least 8). Layouts must differ in real ways: where the PO
  number sits, table vs free-text lines, side-by-side address blocks, column order and column
  names (`Qty`/`Quantity`/`Ordered`, `U/M`/`Unit`, `Part #`/`Your Item`/`Our Ref`), date
  format is already decided in the spec strings.
- `extra_pages`: any of `cover` (fax-style cover sheet before the PO), `terms` (a dense terms and
  conditions page after it). Long orders flow onto more pages on their own.
- `degradations` (applied in order, any mix): `scan` (rasterise at ~150 dpi to an image-only
  PDF with light noise: **no text layer**), `rotate90`, `rotate180`, `skew` (1-3 degrees),
  `noise` (heavier speckle + slight blur), `fax` (low-res ~100 dpi, 1-bit look). Every
  degradation except none implies an image-only PDF. With `[]` the PDF keeps its text layer.
- `handwritten: true`: the *values* (not the form labels) are drawn in the handwriting font from
  `fonts_dir`, like a filled-in order form, and the result is always rasterised (image-only).
- `injection_text`: text printed inside the document. `injection_style`: `visible_note`
  (a normal-looking note line), `small_footer` (tiny grey footer text), `white_text`
  (white on white: invisible to the eye but in the text layer; only for non-degraded docs).

## Answer key (`answer-key/<doc_id>.json`)

Built from how the scenario was **constructed** (the generator knows which trap it planted), not
by running any gate code.

```json
{
  "doc_id": "dev-007",
  "split": "dev",
  "category": "scan",
  "is_po": true,
  "trap": "price_off_5pct",
  "expected_route": "review",
  "expected_reason_codes": ["R06"],
  "acceptable_extra_codes": ["R11"],
  "truth": {
    "customer_id": "C0007",
    "customer_po_number": "PO-48213",
    "po_date": "2026-10-02",
    "bill_to_id": "B0007",
    "ship_to_id": "S0019",
    "currency": "USD",
    "lines": [
      {"line_no": 1, "item_id": "IT-10442", "customer_part_no": "HF-2291", "order_qty": "5",
       "order_uom": "CS", "base_qty": "60", "base_uom": "EA", "unit_price": "86.4000",
       "line_total": "432.00", "requested_date": "2026-10-20"}
    ],
    "carrier_account_no": "A1B2C3",
    "shipping_notes": "Dock 3, call before delivery"
  }
}
```

- `category`: `clean`, `layout`, `scan`, `handwritten`, `multipage`, `trap`, `injection`, `non_po`.
- `expected_route`: `auto`, `review`, `ignored`.
- `truth` holds the correct values in CSV form (see `docs/csv-spec.md`) for every PO, also for
  review cases where the truth is known (then it describes what the document really says).
  `null` where there is no truth (unknown customer has `customer_id: null`).
- `acceptable_extra_codes`: codes that are also fine for this document (a hard scan may raise
  R09 or R11 on top). A review document that gets only acceptable extras and none of the
  expected codes is still a wrong reason.
- Scans and handwritten documents with **no trap** have `expected_route: "auto"` and
  `acceptable_review_codes: ["R09", "R11"]`: going to review with only those codes is counted
  as a "careful review", not as an error.
