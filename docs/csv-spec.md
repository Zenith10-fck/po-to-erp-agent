# ERP import CSV spec (fixed at CP0)

One CSV file per approved order, written into `erp_import/`. One row per order line. Order-level
values repeat on every row, so each row can be imported on its own.

This is a generic format for the reference build. A real ERP has its own import layout; mapping
this file to it is a small, separate step (see "What I would change for production" in the README).

## File rules

- Name: `<customer_id>_<po_number>.csv`. In the PO number, every character that is not
  `A-Z a-z 0-9 - _` becomes `_`.
- Encoding UTF-8 without BOM. Separator comma. Line end CRLF. Every text value in double quotes,
  inner quotes doubled. Numbers are not quoted.
- Decimal point is a dot. No thousands separator. Dates are `YYYY-MM-DD`.
- The file is written as `<name>.csv.tmp` and then renamed, so a watched folder never sees a
  half-written file.
- A file is never overwritten. If the name exists, the order is a duplicate (R10) and goes to review.
- An order with any reason code writes **no** CSV.

## Columns (fixed order, header row always present)

| # | Column | Type | Source | Notes |
|---|---|---|---|---|
| 1 | `customer_id` | text | master data | Matched customer |
| 2 | `customer_po_number` | text | document | As printed, trimmed |
| 3 | `po_date` | date | document | Empty if the PO has none |
| 4 | `bill_to_id` | text | master data | The customer's bill-to |
| 5 | `ship_to_id` | text | master data | Matched ship-to |
| 6 | `currency` | text | master data | Customer's currency; the PO's currency must agree if printed |
| 7 | `line_no` | integer | pipeline | 1, 2, 3 in document order |
| 8 | `item_id` | text | master data | Our item number, also when the PO gave only a customer or legacy number |
| 9 | `customer_part_no` | text | document | Empty if not printed |
| 10 | `order_qty` | number | document | Quantity as ordered |
| 11 | `order_uom` | text | document | Unit as ordered, normalised code (EA, CS, BX ...) |
| 12 | `base_qty` | number | computed | `order_qty` x conversion factor |
| 13 | `base_uom` | text | master data | The item's base unit |
| 14 | `unit_price` | number | document | Per `order_uom`, 4 decimals max |
| 15 | `line_total` | number | computed | `order_qty` x `unit_price`, 2 decimals; equals the printed total when one is printed |
| 16 | `requested_date` | date | document | Empty if not printed |
| 17 | `carrier_account_no` | text | document | Only if on file for the customer; else empty |
| 18 | `shipping_notes` | text | document | As printed, one line |
| 19 | `source_file` | text | pipeline | PDF file name |
| 20 | `run_id` | text | pipeline | Links the row to the audit log |

## What "proven" means for each source

- **document**: the value passed the evidence gate (found in the text layer, or two reads agree).
- **master data**: the ID comes from a match that passed the master-data gate. IDs are never
  taken from the model.
- **computed**: calculated by code from proven values, and checked against the document when the
  document prints the same number.

## Example

```
"customer_id","customer_po_number","po_date","bill_to_id","ship_to_id","currency","line_no","item_id","customer_part_no","order_qty","order_uom","base_qty","base_uom","unit_price","line_total","requested_date","carrier_account_no","shipping_notes","source_file","run_id"
"C0007","PO-48213","2026-10-02","B0007","S0019","USD",1,"IT-10442","",5,"CS",60,"EA",86.4000,432.00,"2026-10-20","","Dock 3, call before delivery","po_0012.pdf","run-A"
```
