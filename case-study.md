# Case study: PO-to-ERP intake agent

*Reference build on synthetic purchase orders. Numbers from `results.json` (held-out runs A and B).*

## The problem

A distributor gets purchase orders by email from many customers. Every customer has its own
layout. Some send scans, faxes or handwritten forms; some attach a cover sheet and terms pages.
Today a person retypes each order into the ERP. Template-based tools need one template per
customer and break when a layout changes. Plain "AI extraction" is fast but nobody can tell which
of its values are wrong.

## The approach

Let the model do what it is good at, reading messy documents, and let code do the rest. Claude
copies every value exactly as printed, with the page and a short quote. Code then proves each
value: it must be in the PDF's own text on the right row (or, for scans, two separate reads must
agree), the arithmetic must hold, and the customer, ship-to, item, unit and price must match the
ERP's master data. An order is written to the import folder only if every check passes.
Everything else goes to a review page that shows the document next to the fields, with the exact
reason.

## How it was tested

40 synthetic documents in 8 layouts, with scans, a handwritten form, multi-page orders, eight
kinds of planted traps, two prompt-injection PDFs and three non-orders. Half were used to tune;
the other half (held-out) were not opened while building. The build was frozen and the held-out
set was run twice. The main number is wrong values written to the CSV, counted field by field
against an answer key.

## Results (held-out)

- **9 wrong values out of 1,206 written, in both runs.** All 9 are in two orders and in two
  low-risk columns: an empty customer part number (the item itself was matched right) and a
  printed pickup line written as a shipping note where the answer key has none. No ID, quantity, unit, price, date or total
  was wrong.
- **2 of 10 written orders had a wrong value**: the two orders above.
- **0 trap, injection or non-PO documents written as an order**, in both runs.
- **6 of 6** trap and injection orders got exactly the right reason code, including a PDF with
  hidden white text.
- **19 of 20** documents routed right per run; the miss was a fine scanned order sent to review.
- **After the runs**, an independent review attacked the gates with hostile PDFs and found
  several ways to get a wrong quantity written (a value borrowed from another row, light-grey or
  covered text, a blank page, a decoy table). They are fixed and tested offline; the held-out
  numbers above are for the build before those fixes.
- **99.8% / 99.6%** of values read right by the model.
- **About 80 seconds and $0.16 API-equivalent per order** (Claude Sonnet 5 through the Claude Code
  CLI on a subscription, so not billed per call).

## What I learned

- **The dual read earns its cost.** On dev scans, one of the two reads pasted the label
  "Delivery instructions:" into the note, and on a fax one read saw "2025" where the other saw
  "2026". Both orders went to review (R09) instead of being written. In the date case the read
  that would have been used was the right one, so that review cost time but prevented nothing;
  the label case would have written a wrong note.
- **A gate can be too strict, and that is fixable without loosening safety:** a "$" glued to a
  price failed the evidence check until the check learned that a bare symbol is still on the page.
- **Read every number of every re-score.** After the "$" fix I re-ran the gates on the first dev
  run's saved reads and checked only the routing. That re-score already showed 3 empty customer
  part numbers. I saw it only after the held-out runs, where the same gap came back.
- **Held-out numbers are humbling and useful.** The last dev run ended at 0 wrong values. The
  held-out set found two real gaps (which number is the customer's, and where a pickup note
  belongs). They are reported as measured, and claiming a fix would need a new held-out set.

## What a client gets

A pipeline that runs in their own environment, a review page their team can use from day one,
a reason code and audit line for every decision, and numbers they can re-run themselves.
