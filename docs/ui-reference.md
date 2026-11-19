# UI reference for `run-report.html`

Research date: 2026-11-16. Goal: make the review-queue report look like a shipped operations tool, by following conventions that real live products share. Nothing here copies a logo, name, brand asset or exact look.

Legend for the "How verified" column:
- **SEEN** = I fetched the page today and looked at a real product screenshot on it.
- **TEXT** = I fetched the page today and read the documentation text (no screenshot viewed).
- **SNIPPET** = only a search-result excerpt was read; the page itself was not opened.
- **MEMORY** = general knowledge, not verified today.

## 1. References studied

| # | Product | URL | What was found there | How verified |
|---|---------|-----|----------------------|--------------|
| 1 | Rossum, validation screen redesign note | https://updates.rossum.ai/en/coming-soon-new-validation-screen-for-a-more-intuitive-experience | Three screenshots: a thin blue box with corner handles around the value on the document; a dark popover anchored under it with the value, the field name in small grey text, and two icon actions (delete, confirm tick); a red-outlined input with the error text "expected date in format DD.MM.YY" placed directly under the input; a thin connector line from the sidebar field to the box. Text: error message moved "under the input"; box turns green only after a human validates. | SEEN |
| 2 | Rossum, interactive bounding boxes | https://docs.coupa.com/en/product-documentation/rossum/welcome-to-rossum-knowledge-base/user-guides/interactive-bounding-boxes-in-rossum | Hover a box to see which field holds the value; click a value to jump to its field. Highlight colours: yellow = extracted, not reviewed; green = checked by a user; red = blocks confirmation. | TEXT (the page's screenshots were not viewed; yellow/green highlights are visible in the screenshots of row 1) |
| 3 | Rossum, keyboard shortcuts | https://docs.coupa.com/en/product-documentation/rossum/welcome-to-rossum-knowledge-base/first-steps-with-rossum/keyboard-shortcuts | Tab = next field; Enter = jump to next field that still awaits review (no tick); arrow keys inside the line-item table; Esc closes the search panel. Mentions "the left panel of validation screen" for fields. | TEXT |
| 4 | Rossum, validation screen guide | https://docs.coupa.com/en/product-documentation/rossum/welcome-to-rossum-knowledge-base/user-guides/document-validation-screen-in-rossum | Top bar holds zoom in / zoom out / reset zoom / search; left panel shows document details, potential duplicates and automation blockers. | TEXT (summary extraction only) |
| 5 | Ramp Bill Pay, draft bill | https://support.ramp.com/bill-pay-overview (image: https://assets.ramp.com/help-center/bill-pay-overview/_attachments/bill-pay-draft-overview.png) | Two panes with a drag handle: form on one side, invoice page on a grey canvas on the other, zoom/rotate controls at the bottom of the document pane. White background, 1px grey borders, almost no shadow, small radii. Section headings ("Vendor", "Bill details") each carry a small green "Complete" badge. Tabs: Overview / Activity / Instructions. Sticky footer with one primary button that shows its keyboard shortcut. Tiny field labels above values. | SEEN |
| 6 | Ramp Bill Pay, AP policy review | https://support.ramp.com/ap-agents-available-in-ramp-bill-pay (image: .../_attachments/ap-policy-review-summary.png) | A compact "Needs review" panel at the top of the bill: amber heading, then a plain bullet list of findings written as full sentences with the real numbers in them. Thin border. (It does have a very faint warm wash in one corner; we do not copy that.) | SEEN |
| 7 | Ramp Bill Pay OCR | https://support.ramp.com/ramp-bill-pay-ocr | OCR auto-fills header fields and line items; user is told to review before creating the bill. | SNIPPET |
| 8 | Stripe Radar, review queue | https://docs.stripe.com/radar/reviews | Queue has a list view (risk level, customer, amount, date) and a detailed view; Previous / Next buttons move between items; "risk insights" explain the score; a timeline shows the full history of actions; quick filters on the queue. | TEXT |
| 9 | Stripe Apps, style tokens (matches the Dashboard) | https://docs.stripe.com/stripe-apps/style | Spacing scale 2 / 4 / 8 / 16 / 24 / 32 / 48 px. Two background roles only (surface, container). One neutral border colour for all borders and dividers. Text roles: primary, secondary, disabled, info, success, attention, critical; critical "should be used sparingly". Four type roles: heading, subheading, body, caption. | TEXT |
| 10 | Stripe Apps, badge + empty state | https://docs.stripe.com/stripe-apps/components/badge , https://docs.stripe.com/stripe-apps/patterns/empty-state | Badge tones: neutral, info, positive, negative, warning, urgent; badges are read-only. Empty state: title says what is missing, short, ends with a period ("No successful payments."); description says when data appears; no promotion. | TEXT |
| 11 | IBM Carbon, data table | https://carbondesignsystem.com/components/data-table/style/ and /usage/ | Row heights 24 / 32 / 40 / 48 / 64 px (32 = compact, 40 = default). Row text 14px / 400; column header 14px / 600. 16px cell padding. Row separator is a subtle bottom border; zebra is an optional modifier. Headers: one or two words, sentence case. | TEXT |
| 12 | GitHub Primer, colour + type primitives | https://primer.style/product/primitives/color/ , https://primer.style/product/primitives/typography/ , https://primer.style/product/components/label/ | Light hex values (bg #ffffff, muted bg #f6f8fa, text #1f2328, muted text #59636e, border #d1d9e0, accent #0969da, success #1a7f37, attention #9a6700, danger #d1242f, with tinted backgrounds). Type: 12 / 14 / 16 / 20 / 32 px, weights 400 / 500 / 600, mono stack ui-monospace, SFMono-Regular, Menlo, Consolas. Label variants: default, accent, success, attention, severe, danger, done. | TEXT (light values read from the page; dark values were NOT on the page) |
| 13 | Shopify Polaris, badge | https://shopify.dev/docs/api/app-home/polaris-web-components/feedback-and-status-indicators/badge | Tones neutral / info / success / caution / warning / critical. "Keep labels to 1-2 words". Past tense for status. In tables, put badges in their own column. | TEXT |
| 14 | Linear, list keyboard model | https://shortcuts.design/tools/toolspage-linear/ | Esc = back; Enter or O = open focused item; ? = shortcut help. | SNIPPET (third-party list; Linear's own page returned 404; J/K is MEMORY) |
| 15 | Esker order management | https://www.esker.com/sites/default/files/resources_files/022_Esker_DeliveryWare_SolSum_OMforERP-AU.pdf | Brochure lists "side-by-side view of original and captured data", controlled exception handling, process history and audit trail. | SNIPPET |
| 16 | Conexiom | https://help.conexiom.com/knowledge-base/verifying-test-documents | Help centre asks for an email before showing content. Not viewed. | BLOCKED |
| 17 | Stripe Dashboard payments list, Mercury, Brex, Vercel, Hyperscience, Nanonets, Docsumo, Airbase | none | Not fetched. Nothing in this spec depends on them. | NOT STUDIED |

## 2. Patterns shared by the live products

- **Split view, document next to fields, resizable.** Ramp (5), Rossum (1, 3), Esker (15). The document sits on a slightly grey canvas so the white page reads as paper. Rossum puts fields left, Ramp puts the document right; the side is a product choice, the split is the constant.
- **List first, then detail, with Previous / Next.** Stripe Radar (8). The reviewer never has to go back to the list to continue.
- **The reason is written as a sentence with the real numbers.** Ramp (6): "Invoice total of $13k increased significantly above prior monthly usage of $1.9k". Rossum (1): "expected date in format DD.MM.YY". No generic "Validation failed".
- **The problem is shown at the field, not only in a banner.** Rossum (1): red outline plus message directly under the input.
- **Source location = thin outlined box on the page, linked to the field.** Rossum (1, 2). Colour of the box carries state: yellow unreviewed, green confirmed, red blocking. Hover and click link field and box in both directions.
- **Section-level status badge.** Ramp (5): "Complete" beside each section heading, so the eye skips sections with no problem.
- **Neutral base, colour only for meaning.** Stripe (9) defines two backgrounds and one border colour; Ramp (5) is white with grey hairlines. Colour appears on badges, links and the single primary button.
- **Small, quiet badges.** Tinted background, darker text of the same hue, 1-2 words (10, 12, 13). Semantic tones are a fixed short list.
- **Dense tables with hairline row borders.** Carbon (11): 32-40px rows, 14px text, bold header, bottom border; zebra is optional, not default.
- **Audit history as a plain timeline.** Stripe Radar (8), Ramp "Activity" tab (5), Esker (15).
- **Keyboard first.** Rossum (3): Enter jumps to the next field that needs attention. Linear (14): Enter opens, Esc goes back, ? lists shortcuts. Ramp (5) prints the shortcut on the primary button.
- **Empty state is one factual line.** Stripe (10). No illustration, no celebration.
- **Light/dark.** Not verified for the AP products. Primer (12) publishes both themes as the same token names with different values; we use that method.

## 3. Chosen references

- **Primary product reference: Rossum validation screen.** It is the closest live product to this job: a human checks machine-extracted fields against the source document, each field has a state, and the evidence location is drawn on the page. It was seen in real screenshots today (row 1) and its behaviour is documented (rows 2-4). Ramp's draft bill (row 5) is the secondary reference for the overall page chrome (white, hairlines, tabs, section badges), because Rossum's own chrome was only seen in close-up.
- **Design system for tokens: GitHub Primer primitives**, with Carbon for table sizes and Stripe's spacing scale. Reason: Primer publishes exact hex and type values in public docs, has a full light and dark neutral scale, a ready set of semantic tones (success / attention / danger / accent / neutral), uses a system-font stack, and is the visual language of a dense list-plus-detail tool that most reviewers already know. The values below are our own tokens; every text pair was contrast-checked here.

## 4. Design spec for `run-report.html`

### 4.1 Fonts (system only, no downloads)

```
--font-ui:   -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", Helvetica, Arial, sans-serif;
--font-mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;
```
All numbers (amounts, quantities, counts, dates, times, IDs): `font-variant-numeric: tabular-nums`. IDs, SKUs, PO numbers, reason codes and evidence quotes use `--font-mono`.

### 4.2 Type scale

| Role | Size / line-height | Weight | Use |
|------|-------------------|--------|-----|
| Page title | 20px / 28px | 600 | "Run 2026-11-16 09:12", order number in detail |
| Section title | 14px / 20px | 600 | "Header", "Line items", "Audit trail" |
| Body | 14px / 20px | 400 | table cells, field values |
| Body strong | 14px / 20px | 600 | table header, counts |
| Small | 12px / 16px | 400 | field labels, chip text, timestamps, help text |
| Summary number | 24px / 32px | 600 | the 5-6 run counters only |
| Mono | 13px / 20px | 400 | IDs, evidence quotes, codes |

No other sizes. No weight above 600. No letter-spacing tricks. No all-caps anywhere (table headers are sentence case).

### 4.3 Spacing, radii, borders

- Spacing scale: 2, 4, 8, 12, 16, 24, 32 px. Page gutter 24px (16px under 768px).
- Radii: 3px chips and inputs, 6px panels and the popover. Nothing larger. No pills except the 8px status dot.
- Borders: 1px solid `--border` for every panel, table and divider. `--border-strong` only for focus-less form outlines and the splitter handle.
- Shadows: none, except the evidence popover: `0 1px 3px rgba(0,0,0,.12), 0 8px 24px rgba(0,0,0,.12)` (light) / `0 8px 24px rgba(0,0,0,.5)` (dark).
- Focus ring: `outline: 2px solid var(--accent); outline-offset: -2px` on rows, `2px` offset on buttons.

### 4.4 Colour tokens and contrast

Contrast ratios computed with the WCAG 2.x formula on 2026-11-16. AA needs 4.5:1 for text.

| Token | Light | Dark | Use |
|-------|-------|------|-----|
| `--bg` | #ffffff | #0d1117 | page, table, panels |
| `--bg-subtle` | #f6f8fa | #151b23 | table header, row hover, document canvas |
| `--bg-neutral` | #eff2f5 | #212830 | neutral chip |
| `--bg-selected` | #ddf4ff | #121d2f | selected row, linked field |
| `--text` | #1f2328 | #f0f6fc | primary text |
| `--text-muted` | #59636e | #9198a1 | labels, secondary text |
| `--border` | #d1d9e0 | #3d444d | all hairlines |
| `--border-strong` | #818b98 | #656c76 | splitter, input outline |
| `--accent` | #0969da | #4493f8 | links, focus, active filter |
| `--ok` / `--ok-bg` | #1a7f37 / #dafbe1 | #3fb950 / #12261e | proven, auto-approved |
| `--warn` / `--warn-bg` | #9a6700 / #fff8c5 | #d29922 / #272115 | sent to review |
| `--bad` / `--bad-bg` | #a40e26 / #ffebe9 | #ff7b72 / #25171c | failed check, wrong value written |

| Pair (text on background) | Light | Dark |
|---------------------------|-------|------|
| text on bg | 15.80 | 17.39 |
| text on bg-subtle | 14.84 | 15.91 |
| text on bg-selected | 13.89 | 15.53 |
| text-muted on bg | 6.11 | 6.50 |
| text-muted on bg-subtle | 5.74 | 5.94 |
| text-muted on bg-neutral (neutral chip) | 5.44 | 5.11 |
| accent on bg | 5.19 | 6.11 |
| accent on bg-selected | 4.56 | 5.45 |
| ok on bg | 5.08 | 7.45 |
| ok on ok-bg (chip) | 4.56 | 6.25 |
| warn on bg | 4.87 | 7.50 |
| warn on warn-bg (chip) | 4.52 | 6.33 |
| bad on bg | 7.87 | 7.51 |
| bad on bad-bg (chip) | 6.86 | 6.84 |
| border-strong on bg (non-text, needs 3.0) | 3.45 | 3.57 |

`--border` on `--bg` is 1.43 / 1.92: it is decoration only and must never be the only carrier of meaning. The three light chip pairs at 4.52-4.56 pass AA with a small margin; do not lighten those text colours or darken those backgrounds.

Theme switch: `@media (prefers-color-scheme: dark)` sets the dark values on `:root`; an optional `data-theme="light|dark"` on `<html>` overrides it. The PDF page image stays white in both themes, inside a 1px `--border` frame.

Colour budget rule: on the queue list, colour may appear only in (a) status dot + label, (b) reason chips, (c) links, (d) the focus ring. Everything else is neutral.

### 4.5 Table (queue list and line items)

- Row height 36px (between Carbon's 32 and 40), header row 32px, cell padding 0 12px.
- Header: 12px / 600, `--text-muted`, `--bg-subtle`, sentence case, 1-2 words, sticky on scroll.
- Separation: 1px `--border` bottom border per row. No zebra. No vertical lines.
- Hover: `--bg-subtle`. Selected / keyboard-focused: `--bg-selected` plus a 2px `--accent` bar on the left edge.
- Alignment: text left; amounts, quantities, counts right with tabular numerals; currency code in its own muted column or as a muted suffix; dates as `2026-11-16`, times as `09:12:41`.
- Long text truncates with an ellipsis and a `title` attribute; IDs never truncate.
- Sort: click a header; the active header shows a small arrow glyph drawn in CSS or inline SVG.

### 4.6 Chip anatomy

```
[ R07 Price mismatch ]     height 20px, padding 0 6px, radius 3px, 12px/16px text, weight 500
  ^code (mono) ^1-2 words  background tint + same-hue text, no border, no icon, no shadow
```
- Route status (one per order): 8px round dot + plain label text, not a filled chip: `● Auto-approved` (ok), `● Review` (warn), `● Ignored` (muted). The label always carries the meaning; the dot is redundant colour.
- Reason chips R01-R14: all use the warn tint, except codes that mean a hard failure (bad tint). Do not give each code its own colour. Max 3 chips in a row, then `+2` as a neutral chip with the full list in `title`.
- Field check result: `Proven` (ok text + check glyph), `Failed` (bad text + cross glyph), `Not checked` (muted + dash). Glyphs are inline SVG, 12px, `currentColor`.

### 4.7 Layout (a): summary + queue list

```
+----------------------------------------------------------------------------------+
| PO intake  /  Run 2026-11-16 09:12          model, version, duration   [? keys]  |  48px bar, border-bottom
+----------------------------------------------------------------------------------+
| Orders   Auto-approved   Sent to review   Ignored   Wrong values written   Cost  |  one bordered strip,
|   42          31               9             2               0             $0.84 |  cells split by 1px lines,
|              73.8%           21.4%          4.8%       of 588 checked    2m 14s  |  label 12px muted on top
+----------------------------------------------------------------------------------+
| [All 42] [Review 9] [Auto-approved 31] [Ignored 2]   Reason: [Any v]   [Search ] |  filter row, 32px controls
+----------------------------------------------------------------------------------+
| Status          Order      Customer         Lines     Total   Reasons       Time |
|-----------------------------------------------------------------------------------|
| ● Review        PO-88213   Acme Tools GmbH      6  4,218.50   R07 R11      09:12 |
| ● Review        PO-88217   Borealis AS          2    310.00   R03          09:12 |
| ● Auto-approved PO-88209   Kestrel Ltd         14 12,940.00   —            09:12 |
| ● Ignored       (no PO)    newsletter@...       —         —   R01          09:13 |
+----------------------------------------------------------------------------------+
| 42 orders · showing 42                                             j/k move · Enter open |
+----------------------------------------------------------------------------------+
```
- Page is left-aligned, full width, max-width 1440px. No hero, no centred title, no icons in the summary strip.
- "Wrong values written" is the trust number: shown as plain `0` in `--text`; it turns `--bad` only when it is above zero.
- Default sort: Review first, then by time. Segmented filter counts always visible.

### 4.8 Layout (b): order detail

```
+----------------------------------------------------------------------------------+
| < Queue   PO-88213 · Acme Tools GmbH   ● Review  [R07][R11]      3 of 9  [<] [>] |  48px bar
+----------------------------------------------------------------------------------+
| Needs review                                                                     |  bordered panel, warn heading,
|  - R07 Line 3 unit price 41.20 differs from price list 39.80 (+3.5%)             |  one sentence per reason,
|  - R11 Ship-to "Hall 4, Dock B" not found in customer master                     |  click = jump to field
+------------------------------------------+---------------------------------------+
| Page 1 of 2   [-] 100% [+] [Fit]         || [Fields] [Audit trail] [CSV row]     |
|  .--------------------------------.      ||  Header                    6/6 proven|
|  |  PURCHASE ORDER                |      ||  PO number   PO-88213      ✓ Proven  |
|  |  [PO-88213]  <- outlined box   |      ||  Order date  2026-11-12    ✓ Proven  |
|  |                                |      ||  Ship-to     Hall 4, Dock B ✗ Failed |
|  |  ..........................    |      ||    R11 Not found in customer master. |
|  |  3  Drill bit   [41.20] <- red |      ||    Evidence p.1: "Ship to: Hall 4,…" |
|  |                                |      ||  Line items               5/6 proven |
|  '--------------------------------'      ||  # SKU     Qty    Unit    Total   Chk|
|  grey canvas, white page, 1px frame      ||  3 DB-114   10   41.20   412.00   ✗  |
+------------------------------------------+---------------------------------------+
   document 55%          6px splitter ^         fields 45%, own scroll
```
- Document left, fields right. Both panes scroll on their own; the top bar and "Needs review" panel stay fixed.
- A field row is a 3-column grid: label (12px muted, 120px) / value (14px, mono for IDs and numbers) / result (right-aligned, 12px). A failed field gets a 2px `--bad` left bar, and under the value: the reason sentence in `--bad`, then the evidence quote in mono on `--bg-subtle` with its page number. A proven field shows the evidence only on hover or focus.
- Section heading right side: `6/6 proven` in ok, or `5/6 proven` in warn. Sections with all fields proven can start collapsed in Review orders.
- Evidence box on the page image: absolutely positioned, 1.5px outline, no fill at rest. Outline colour by state: ok (proven), bad (failed), warn (found but not verified). The active box gets a fill of the same hue at 15% opacity. If no coordinates exist for a value, show no box, and the field says "Evidence p.1 (location not available)".
- Audit trail tab: plain two-column list, time (mono, muted, tabular) + event sentence, newest last, 1px left rule; no avatars, no coloured bubbles.
- All clear state for an auto-approved order: the top panel is replaced by one line, "All 24 checks proven. Written to CSV row 17." No illustration.
- Empty queue filter: "No orders match this filter." plus a "Clear filter" link. Empty run: "No orders in this run."

### 4.9 Interaction rules

| Action | Result |
|--------|--------|
| Click a queue row, or Enter / O on the focused row | Open detail (URL hash `#order=PO-88213`, so Back works) |
| J or Down, K or Up | Move row focus in the list; in detail, move to next / previous field |
| N / P, or the [<] [>] buttons | Next / previous order in the current filtered list |
| Enter in detail | Jump to the next field that failed |
| Esc | Close popover if open, else go back to the queue, keeping scroll and focus |
| Click a filter segment or pick a reason code | Filter list; counts update; state kept in the hash |
| / | Focus search |
| ? | Show the shortcut list in a plain panel |
| Hover or focus a field | Its evidence box on the page gets the fill; the page scrolls it into view if hidden; evidence quote appears |
| Hover or click a box on the page | The matching field row gets `--bg-selected` and scrolls into view |
| Click a reason in "Needs review" | Scroll to and focus the field it refers to |
| +/- or Ctrl+wheel in the document pane | Zoom the page image; "Fit" resets |

Shortcuts are ignored while a text input has focus. Every mouse action has a keyboard path. Rows are real `<tr tabindex="0">` or buttons; state is exposed with `aria-selected` / `aria-current`. Transitions: 100ms on background colour only; none when `prefers-reduced-motion` is set.

### 4.10 Responsive rule

- >= 1100px: split view as drawn.
- 768-1099px: the split stacks; a two-tab switch "Document | Fields" replaces the splitter; field hover still sets the active box so it is ready when switching.
- < 768px: the summary strip wraps to a 2-column grid; the queue table keeps Status, Order, Total, Reasons and hides Customer, Lines, Time (shown in detail); minimum touch target 40px; no horizontal page scroll (line-item table scrolls inside its own container).

### 4.11 Print rule

`@media print`: force the light tokens; hide top-bar buttons, filters, shortcuts hint and the splitter; print the summary strip and the full queue table with repeating header (`thead { display: table-header-group }`); in detail, page image first, then fields with every reason sentence and evidence quote expanded, then the audit trail; `break-inside: avoid` on field rows; chips print as bordered text (`border: 1px solid currentColor; background: none`) so they survive without background printing; show the full URL hash and run ID in a footer line.

## 5. Anti-slop checklist

| # | The page must not... | How a reviewer checks |
|---|----------------------|-----------------------|
| 1 | use any gradient | Search the file for `gradient`. Zero hits. |
| 2 | use purple / violet / indigo as accent | Every hex in the file is in the token table of 4.4. |
| 3 | use emoji as icons or bullets | Search for characters above U+1F000 and for U+2705, U+274C, U+26A0, U+2728. Zero hits. Glyphs are inline SVG. |
| 4 | use glass effects | Search for `backdrop-filter` and `blur(`. Zero hits. |
| 5 | use big rounded cards with drop shadows | Search `border-radius`: no value above 6px (except the 50% status dot). Search `box-shadow`: one rule only (popover). |
| 6 | have a centred hero or marketing headline | First screen shows the summary strip and at least 8 queue rows at 1366x768. No `text-align: center` on headings. |
| 7 | load anything from the network | Search for `http://`, `https://`, `@import`, `<link`, `src=` pointing outside the file. Open with the network tab: zero requests (page images embedded or local). |
| 8 | use more than the allowed type sizes | Search `font-size`: only 12, 13, 14, 20, 24px. No weight above 600. |
| 9 | spread colour everywhere | Grey-scale screenshot of the queue: still fully readable. Colour screenshot: colour only on dots, chips, links, focus. |
| 10 | show status by colour alone | Every dot and chip has text; field results have a glyph plus a word. |
| 11 | use vague messages | Every failed field shows a sentence with the two compared values and the reason code. No "Something went wrong", no "Validation failed". |
| 12 | use filler copy or exclamation marks | No "Welcome", "Powered by AI", "Seamless", sparkle icons, or "!" in UI text. Empty states are one factual sentence. |
| 13 | mis-align numbers | Amount and quantity columns are right-aligned with `tabular-nums`; decimals line up down the column. |
| 14 | animate for decoration | Search `animation` and `transition`: only a 100ms background-colour transition. |
| 15 | break without a mouse | Complete a full pass (open, next failed field, next order, back) with keyboard only; focus ring always visible. |
| 16 | fail contrast | Spot-check 5 text pairs per theme with a contrast tool against the table in 4.4. |
| 17 | break in dark theme or in print | Toggle OS dark mode: no white panels except the PDF page. Print preview: table header repeats, chips legible. |
| 18 | look like a known product | No third-party logo, product name, brand font or brand colour anywhere. |

## 6. Open questions / not verified

- **No full-screen screenshot of the Rossum validation screen was viewed.** Only close-ups from the 2024 redesign note. The overall chrome (exact pane sides, sidebar grouping) comes from text ("left panel") and from the Ramp screenshot. The Coupa-hosted Rossum doc screenshots were not opened.
- **Conexiom** help centre is behind an email gate; **Esker** was only a brochure search excerpt. The closest-domain products (sales order automation) are therefore the least verified.
- **Stripe Dashboard itself** (payments list, Radar queue visuals) was not seen; only its public docs text and the Stripe Apps tokens. Row height and badge look in the real Dashboard are not confirmed.
- **Linear**: its own shortcuts page returned 404; Esc / Enter / ? come from a third-party list excerpt; J/K is from memory.
- **Primer dark hex values** were not on the fetched page. The dark tokens in 4.4 are our own values (close to Primer's dark theme from memory); the contrast ratios for them were computed today and are correct for the values as written.
- Light/dark behaviour of Rossum and Ramp was not checked.
- Does the pipeline store **evidence coordinates** (page + bounding box) or only the quote text and page number? If only the quote, the box overlay in 4.8 cannot be drawn and the fallback line applies. This decides the main visual feature.
- Are PDF pages embedded as base64 images (large file) or referenced as local files next to the HTML? "One self-contained file" suggests base64; check file size with a 40-order run.
- Which of R01-R14 count as hard failure (bad tint) versus review (warn tint)? Needs a column in `docs/reason-codes.md`.
- Row height 36px and the 55/45 split are our choices inside the ranges the references show, not values copied from one product.
