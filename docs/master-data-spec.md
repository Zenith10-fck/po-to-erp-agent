# Master data spec (fixed at CP0)

The ERP reference data the gates check against. All synthetic, made by
`test-set/generator/` with a fixed seed. Plain CSV files in `test-set/master-data/`, UTF-8,
header row, comma separated. In a client build these files are an export from the real ERP.

Company in the story: a made-up US industrial supplier. No real company, person or address.

## Files

### `customers.csv` (about 25 rows)
| Column | Notes |
|---|---|
| `customer_id` | `C0001` ... |
| `name` | Legal name |
| `aliases` | Other names seen on POs, separated by `;` (trading name, short name) |
| `bill_to_id` | `B0001` ... one per customer |
| `bill_to_address` | One line |
| `currency` | `USD` for all in this build |
| `price_list_id` | `PL-A`, `PL-B` ... |
| `active` | `Y` / `N` |

Must include on purpose: two pairs of near-identical names (for R02 ambiguity).

### `ship_tos.csv` (about 60 rows)
| Column | Notes |
|---|---|
| `ship_to_id` | `S0001` ... |
| `customer_id` | Owner. A ship-to matches only inside its customer |
| `name` | Site name |
| `address` | One line: street, city, state, ZIP |

Must include: customers with 1 ship-to, customers with 4+, and ship-tos that differ from the bill-to.

### `items.csv` (about 300 rows)
| Column | Notes |
|---|---|
| `item_id` | `IT-10001` ... our item number |
| `description` | Short product text |
| `base_uom` | `EA`, `FT`, `LB` ... |
| `legacy_item_no` | Old number still used by some customers. May be empty |
| `active` | `Y` / `N` (an inactive match raises R04) |

### `customer_parts.csv`
| Column | Notes |
|---|---|
| `customer_id` | |
| `customer_part_no` | The customer's own number |
| `item_id` | Our item |

The same `customer_part_no` may point to different items for different customers. That is why
the item match always runs inside the matched customer.

### `uom_conversions.csv`
| Column | Notes |
|---|---|
| `item_id` | |
| `from_uom` | `CS`, `BX`, `PK`, `RL` ... |
| `factor` | How many base units in one `from_uom` (CS = 12 EA gives 12) |

The base unit itself needs no row. No row for an ordered unit raises R05.

### `uom_aliases.csv`
| Column | Notes |
|---|---|
| `alias` | Text seen on POs: `each`, `ea.`, `case`, `cs`, `ctn`, `box` ... |
| `uom` | Normalised code |

### `price_lists.csv`
| Column | Notes |
|---|---|
| `price_list_id` | |
| `item_id` | |
| `uom` | The unit the price is for |
| `unit_price` | 4 decimals max |

The price check converts to the ordered unit with `uom_conversions` before comparing.

### `carrier_accounts.csv`
| Column | Notes |
|---|---|
| `customer_id` | |
| `carrier` | `UPS`, `FedEx` ... |
| `account_no` | The customer's own account for collect / third-party shipping |

An account number on a PO that is not in this file for that customer raises R12.

## Matching order (used by the master-data gate)

1. Customer: exact match on name or alias, then fuzzy (thresholds in `reason-codes.md`).
2. Ship-to: only among that customer's ship-tos. Name and address are both compared.
3. Item, in this order: `item_id`, then `customer_part_no` for that customer, then
   `legacy_item_no`. Exact only. Two different items from two numbers on one line raises R04.
4. UoM: alias to code, then a conversion to the base unit must exist.
5. Price: the customer's price list, converted to the ordered unit, within tolerance.
6. Carrier account: only if the PO prints one.

## Processed-orders ledger

`state/processed.csv` (`customer_id`, `customer_po_number`, `run_id`, `result`). The duplicate
gate reads it. It is written by the pipeline, not part of the master data, and is reset at the
start of each measured run so runs A and B are comparable.

## Answer key (made with the test set at CP1)

`test-set/answer-key/<doc_id>.json` per document: is it a PO, the expected route (`auto`,
`review`, `ignored`), the expected reason codes, and for `auto` orders the exact expected CSV
rows. `measure.py` compares live output with these files only.
