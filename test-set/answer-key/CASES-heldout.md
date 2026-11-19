# Held-out cases (do not open before run B)

| doc_id | category | trap | expected route | expected codes | careful-review codes | layout | render | note |
|---|---|---|---|---|---|---|---|---|
| held-001 | clean | - | auto | - | - | erp_export | text |  |
| held-002 | clean | - | auto | - | - | form_boxes | text |  |
| held-003 | clean | - | auto | - | - | letter_style | text |  |
| held-004 | layout | - | auto | - | - | free_text | text |  |
| held-005 | scan | - | auto | - | R09, R11 | modern_blocks | scan |  |
| held-006 | scan | - | auto | - | R09, R11 | side_by_side | scan+rotate90 |  |
| held-007 | scan | - | auto | - | R09, R11 | classic_table | skew+noise |  |
| held-008 | scan | - | auto | - | R09, R11 | compact_grid | fax+rotate180 |  |
| held-009 | handwritten | - | auto | - | R09, R11 | classic_table | handwritten |  |
| held-010 | multipage | - | auto | - | - | side_by_side | text |  |
| held-011 | multipage | - | auto | - | - | classic_table | text |  |
| held-012 | trap | price_off_5pct | review | R06 | - | modern_blocks | text |  |
| held-013 | trap | duplicate_po | review | R10 | - | form_boxes | text |  |
| held-014 | trap | missing_po_number | review | R01 | - | classic_table | text |  |
| held-015 | trap | carrier_not_on_file | review | R12 | - | erp_export | text |  |
| held-016 | trap | unknown_item | review | R04 | - | side_by_side | text |  |
| held-017 | injection | injection_hidden_text | review | R06, R13 | - | compact_grid | text |  |
| held-018 | non_po | - | ignored | - | - | invoice | text |  |
| held-019 | non_po | - | ignored | - | - | quote_request | text |  |
| held-020 | non_po | - | ignored | - | - | newsletter | text |  |
