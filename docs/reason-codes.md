# Reason codes (final list, fixed at CP0)

An order is written to `erp_import/` only if it has **zero** reason codes. Any code sends the
whole order to `review/`. An order can carry many codes. Each code is raised by code, never by
the model's opinion. Each raised code is saved with: code, scope (`order` or `line N`), field,
what was read, what was expected, and the page.

| Code | Name | Raised when | Raised by |
|---|---|---|---|
| R01 | PO number missing | No PO number was extracted | evidence gate |
| R02 | Customer not matched | Customer name matches no master customer, or two customers match almost equally | master-data gate |
| R03 | Ship-to not matched | Ship-to matches no ship-to of that customer, or is ambiguous | master-data gate |
| R04 | Item not matched | A line matches no item by own, customer or legacy part number; or it matches an inactive item; or two items | master-data gate |
| R05 | Unit of measure problem | The UoM is unknown, or the item has no conversion from it to the base unit | master-data gate |
| R06 | Price problem | The unit price is missing, or differs from the customer price list by more than the tolerance | master-data gate |
| R07 | Math mismatch | qty x unit price is not the line total, or the lines do not sum to the order total | math gate |
| R08 | Value not proven | A required value is missing, or cannot be found in the document text at the page the model gave | evidence gate |
| R09 | Dual-read disagreement | Scan only: two independent reads gave different values for a field | evidence gate |
| R10 | Duplicate PO | Same customer + PO number was already processed | duplicate gate |
| R11 | Low legibility | The model reported `partly_unclear` or `unreadable`, or the page render is below the quality floor | evidence gate |
| R12 | Carrier account problem | A carrier account number is on the PO but is not on file for that customer, or two are given | master-data gate |
| R13 | Suspicious content | The model reported instruction-like text, or the code's own pattern scan of the text layer found it | injection gate |
| R14 | Model output unusable | Refusal, time-out, broken JSON, schema error, or no order lines | model client |

## Rules

- **Required values** (R08 if missing or not proven): PO number (R01 instead), customer name,
  ship-to name or address, and per line: qty, UoM, and at least one of item number or customer
  part number. Unit price is required too, but a missing price raises R06.
- **Optional values**: PO date, requested date, order total, line total, carrier, shipping notes.
  If one is present it must still pass its gate (evidence, math). If absent, no code.
- **Text PDF vs scan**: a page with a usable text layer is checked against that text (R08). A page
  without one is read twice and compared (R09). The two paths never mix on one page.
- **R13 never depends on the model alone.** If the model obeys an injected instruction and stays
  silent, the changed value still fails R06, R07 or R08, because the gates compare with the
  document and the master data, not with what the model says is fine.
- **Non-PO documents** get no reason code. They are logged as `ignored` with the classifier's
  `doc_type` and never reach `review/` or `erp_import/`.
- Codes are never renumbered. A new case gets a new code.

## Fixed thresholds (starting values)

These may be tuned on the DEV set only, and are frozen before the held-out run A.

| Setting | Value |
|---|---|
| Name match (customer, ship-to) | rapidfuzz `token_set_ratio` >= 92 after normalising case, punctuation and company suffixes |
| Ambiguity margin | best score must beat the second best by >= 5 points, else "ambiguous" |
| Part numbers | exact match after removing spaces, dashes and case. No fuzzy match on part numbers |
| Price tolerance | absolute difference <= 0.01 per unit, or <= 0.5 % of the list price |
| Line math tolerance | 0.01 |
| Order total tolerance | 0.01 x number of lines |
