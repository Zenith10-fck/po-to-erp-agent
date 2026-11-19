# UI reference v2 for `run-report.html`: "Signal"

Research date: 2026-11-18. Replaces the Primer-like v1 (`docs/ui-reference.md`, kept for its
references and rules). Owner feedback on v1: "still AI-style, not unique, generic, rigid, not
modern". The first v2 direction ("Proof sheet": warm paper, terracotta accent, Instrument Sans,
uppercase mono labels) was rejected in round 2: "still a lot of text, the font still looks like
Claude style; show key points; drop the R-codes". That look sits close to Anthropic's own palette,
so it read as AI-made. "Signal" replaces it. Nothing here copies a logo, brand font, colour or layout.

Legend: **SEEN** = I captured a 1440px screenshot of the live page today (headless Edge) and looked
at it. **TEXT** = I read the page text today, no screenshot. Marketing pages were used only where
they show a real product screen.

## 1. References

| # | Product / source | URL | What I took from it | How |
|---|---|---|---|---|
| 1 | Linear, home page product screen | https://linear.app | Quiet chrome, small grey meta text, tight 13-14px UI text, a "1 / 84" position counter with arrows in the item header, the agent's work shown as plain activity lines. | SEEN |
| 2 | Linear changelog | https://linear.app/changelog | Big tight headline, plain rows with a chevron, almost no boxes. | SEEN |
| 3 | Linear, "How we redesigned the Linear UI" | https://linear.app/now/how-we-redesigned-the-linear-ui | Theme from base, accent and contrast; "limited accent"; reduce visual noise, raise density. | TEXT |
| 4 | Plain, product screen | https://www.plain.com | AI note in the thread with "2 sources"; right-hand details panel with small labels and plain values; one accent. | SEEN |
| 5 | Attio, product screen | https://attio.com | Cool near-white chrome, hairline borders, small rounded inputs, one blue action, black primary, key hint inside the control. | SEEN |
| 6 | Ramp, AP product page | https://ramp.com/accounts-payable | Invoice on a tinted canvas next to the form; "Scan complete." status line; numbered line items; accent on one button only. | SEEN |
| 7 | Reducto (document AI) | https://reducto.ai | Highlight boxes over parsed regions on document thumbnails (the evidence-box idea). | SEEN |
| 8 | Granola | https://www.granola.ai | Calm product window, few elements per screen. | SEEN |
| 9 | Vercel Geist colours | https://vercel.com/geist/colors | Fixed jobs per step: backgrounds (default, hover, active), borders, solid fills, secondary and primary text; "draw each border once"; translucent shadows. | TEXT |
| 10 | NN/g, onboarding tutorials | https://www.nngroup.com/articles/onboarding-tutorials/ | Auto-launched tutorials are skipped; prefer contextual help that is easy to dismiss and easy to find again. | TEXT |
| 11 | Rossum, validation screen note | https://updates.rossum.ai/en/coming-soon-new-validation-screen-for-a-more-intuitive-experience | Error under the input; box colour shows state. | TEXT |
| 12 | Mercury | https://mercury.com | Photo hero only today; nothing taken. | SEEN (not used) |
| - | Extend, Hebbia, Raycast, Mobbin, Refero | - | Timed out or behind a login. | NOT STUDIED |

## 2. What reads as crafted, and what reads as AI-made

Crafted (1, 4, 5, 6): cool true neutrals with one precise accent that has one job; status you read
from a dot or a pill, not a paragraph; numbers that line up; position counters and key hints; the
machine's work shown as a mark on the source document.

AI-made (banned): purple gradients, glass blur, emoji, cards with shadows everywhere, centred hero,
every element boxed, and, after round 1, the warm beige + terracotta + uppercase mono "eyebrow"
look, over-explaining paragraphs, and internal codes (R06) shown to users.

First-time use (10): one glanceable flow line, dismissible, with the long version in Help; the first
action on one button; tooltips instead of legends; labels in the user's words.

## 3. Direction: "Signal"

A calm, cool-neutral desk where one precise colour, cobalt, means "this needs you". Everything
proven is quiet; the eye lands only on what a person must decide. The page shows key points (label,
icon, two numbers, one action); longer words live behind "Why?" and the Help panel.

1. **One signal colour.** Cobalt marks what needs you: the count, the status dot, the problem icon, the box on the PDF, the primary button. Green only says "written". Grey says "not an order". Red appears only if wrong values were written.
2. **No codes on screen.** R01-R14 stay in the data and audit file. The user sees a 2-3 word label with a line icon (4.5).
3. **Key points, not paragraphs.** Queue row = status dot, customer, PO, "Price differs · line 2", lines, total. Problem card = icon + label, "On PDF 8.47 -> Price list 8.92 (-5.0%)", one action of at most 8 words; "Why?" opens the reason.
4. **Number the problem in both places.** Pin 1 on the PDF = card 1 = pin on the field row. "Show on PDF" pulses the exact box.
5. **Teach in 3 seconds, once.** A one-line flow (PDF arrives -> Claude reads it -> Code checks every value -> Proven: written, or Doubtful: waits for you), dismissible; Help holds the rest; statuses explain themselves in tooltips.
6. **Problems first, proof compact.** Fields start with "Needs your check", then proven values as a dense checklist, then one line "Not checked: ...".
7. **Production finish.** 4/8px grid, 52px bar, 56px rows, inset accent bar on the selected row, 999px pills, accent focus rings, a real empty state; dark mode uses the same token names.
8. **Honest by construction.** No approve or send buttons. "Mark as checked" and notes say "Notes stay in this browser"; export is a CSV file with a formula guard; "not scored" / "not reported", never a fake zero.

## 4. Tokens

### 4.1 Typeface (embedded as base64 woff2, zero network requests)
**Hanken Grotesk**, variable 100-900, Latin subset, `@fontsource-variable/hanken-grotesk@5.3.0`,
SIL OFL 1.1, file and licence in `src/po_agent/assets/fonts/` (35 KB woff2, about 46 KB as base64).
Chosen after rendering six OFL candidates side by side at 14px and measuring digit widths with
`tabular-nums` in the browser: Albert Sans has no tabular figures (out); Schibsted Grotesk's tabular
digits look monospaced and loose; Onest and Public Sans are good but wider; Figtree reads friendlier
than an operations tool should. Hanken Grotesk has compact figures that are tabular by default and
crisp small labels, and it is rarely seen on AI-made sites. No embedded mono: file names and the raw
CSV use the system mono stack. Instrument Sans and IBM Plex Mono were removed.

### 4.2 Type scale (px, size / line-height / weight)
| Role | Spec |
|---|---|
| Queue headline ("8 orders need your check") | 28 / 36 / 600, -0.015em, count in cobalt |
| Order title, compare values, stats | 20 / 28 / 600 |
| Card label, panel titles | 16 / 24 / 600 |
| Body, table cells | 14 / 20 / 400-500 |
| Secondary text, field labels, tabs | 13 / 20 / 400-500 |
| Small counts, kbd | 12 / 16 |
No uppercase, no letter-spaced labels, no other sizes, nothing above 600.

### 4.3 Colour (WCAG 2.x ratios computed today)
| Token | Light | Dark | Use |
|---|---|---|---|
| `--bg` | #f7f8fa | #0e0f12 | app background |
| `--surface` | #ffffff | #16181c | bar, list, cards, side pane |
| `--sunk` | #eef0f3 | #1b1d22 | PDF canvas, "Mark as checked" bar |
| `--hover` / `--sel` | #f3f4f7 / #edf1fd | #1d2026 / #1b2440 | hover / selected |
| `--text` / `--text-2` | #17181c / #5b606b | #eceef2 / #a0a5b0 | text / secondary |
| `--line` / `--line-2` / `--line-strong` | #e4e6eb / #cdd1d9 / #878d98 | #272a31 / #363a45 / #6f7582 | hairlines / inputs / arrows |
| `--accent` / `--accent-bg` / `--accent-line` | #2453d6 / #ecf1fe / #b9c9f7 | #7d9dff / #1c2647 / #34478a | needs you |
| `--ok` / `--ok-bg` | #167a43 / #e7f5ed | #4fc483 / #132a1d | written, proven |
| `--muted-bg` | #eef0f3 | #22252c | neutral pill |
| `--danger` | #c2261c | #ff7a6e | only "wrong values written" above 0 |
Boxes on the white PDF image use fixed page colours: cobalt #2453d6 (problem), grey #878d98 (proven).

| Pair | Light | Dark |
|---|---|---|
| text on bg / surface / sel | 16.69 / 17.74 / 15.71 | 16.50 / 15.30 / 13.17 |
| text-2 on bg / surface / sunk / sel | 5.93 / 6.31 / 5.52 / 5.59 | 7.76 / 7.20 / 6.83 / 6.19 |
| accent on bg / surface / accent-bg | 6.02 / 6.40 / 5.66 | 7.43 / 6.89 / 5.74 |
| on-accent on accent (primary button) | 6.40 | 7.43 |
| ok on bg / surface / ok-bg | 5.07 / 5.39 / 4.79 | 8.72 / 8.09 / 6.94 |
| danger on bg | 5.51 | 7.54 |
| line-strong on surface (non-text, needs 3.0) | 3.34 | 3.84 |
All text pairs pass AA (4.5).

### 4.4 Space, radius, elevation, motion
- 4/8 grid: 4, 8, 12, 16, 20, 24, 32. Gutter 32px (16px under 768px).
- Radius: 2-4px boxes and kbd, 6px controls, 8px cards and the list, 999px pills, 50% dots and pins.
- Elevation: `--lift` only on the PDF popover and the Help panel; the selected row has an inset 3px accent bar.
- Motion: 120ms background-colour on hover; one `locate` ring for "Show on PDF"; none under reduced motion.

### 4.5 Problem labels (the code stays in the data only)
| Code | Label | Icon | Action |
|---|---|---|---|
| R01 | PO number missing | hash | Find the PO number, or ask the customer. |
| R02 | Customer unclear | person | Pick the right customer account. |
| R03 | Ship-to unclear | map pin | Confirm the delivery address with the customer. |
| R04 | Item unknown | box | Find the right item number. |
| R05 | Unit unknown | ruler | Confirm the unit and the pack size. |
| R06 | Price differs | tag | Confirm the price with the customer. |
| R07 | Total doesn't add up | sigma | Find which printed number is wrong. |
| R08 | Not found on PDF | magnifier | Read this value on the PDF yourself. |
| R09 | Reads disagree | two arrows | Check the page; pick the right value. |
| R10 | Duplicate order | copy | Compare with the earlier order. Likely a resend. |
| R11 | Hard to read | eye, crossed | Ask for a clearer copy. |
| R12 | Carrier account | truck | Confirm the carrier account with the customer. |
| R13 | Suspicious text | shield | Don't follow it. Confirm the order by phone. |
| R14 | Couldn't read | file with x | Enter this order by hand. |
The same check found twice (model flag and code scan for suspicious text) is one card. A duplicate
order links to the earlier order when it is in the same run.

## 5. Wireframes

Queue:
```
[v] PO intake  Run dev-2  (Demo data)                                       model   (?) Help
+ [doc] PDF arrives -> [eye] Claude reads it -> [list] Code checks every value -> [v] Proven: written  or  (!) Doubtful: waits for you   Learn more  x +
8 orders need your check                          Wrong values written | API-equivalent cost | Model time
[ Review first order -> ]  or press Enter         0 of 1,026           | $2.64               | 22m 22s
=====cobalt=====  =======green=======  ==grey==   (proportional; each segment is a filter)
8 Need check      9 Written to ERP     3 Not an order    20 All
8 of 20                                                [All problems v] [Search customer or PO]
| . | Harlow Fastener Supply Inc. / PO-72531 | [tag] Price differs · line 2 |  3 | 383.44 USD | > |
```
Order detail:
```
<  Harlow Fastener Supply Inc.  PO-72531  (!) Needs check             3 of 8 needs check  [<] [>]
   PO_PO-72531.pdf · 1 page · text PDF
+-- PDF (56%, resizable) ---------------------+-- 1 problem to check -------------------------+
| Page 1 of 1   [] Problem [] Proven  - 76% + Fit | (1) [tag] Price differs · Line 2 · unit price |
|   2  IT-10180 ...  (1)[8.47]  101.64         |   On PDF 8.47  ->  Price list 8.92  (-5.0%)   |
|                                              |   -> Confirm the price with the customer.     |
|                                              |   Show on PDF   Why?                          |
|                                              | [ ] Mark as checked  Notes stay in this browser  Add note |
|                                              | Fields 28/29 | History | ERP file             |
|                                              | Needs your check / Proven (dense) / Not checked / Order lines |
+----------------------------------------------+-----------------------------------------------+
```
Under 1100px the split becomes "Problems | PDF"; under 768px a queue row shows customer, PO,
problem and total; nothing scrolls sideways.

## 6. Mechanical checks (tests/test_report.py)

No `gradient`, `backdrop-filter`, CSS `blur(`; shadows only `var(--lift)` (twice) and the inset row
bar; radius at most 8px, or 999px / 50%; font sizes only from 4.2; weights at most 600; every hex a
token; no `text-transform`, letter-spacing only on the headline; one keyframe; no emoji; one
embedded font (Hanken Grotesk, OFL, licence present, no unused font files), banned families absent;
monospace used at most twice; no `R01`-`R14` in the page code or in any UI string in the data;
labels 2-4 words, actions at most 8 words; no HTML sinks; storage only in try/catch; no network
calls and no fake approve/send controls.

## 7. Not verified / open

- Extend, Hebbia and Raycast screens were not captured; Mobbin/Refero need a login.
- No test with a real order-desk user; "clear in 3 seconds" is a design judgement.
- Print layout and the CSV download were not checked by eye.
- The pipeline gives no boxes for scans, no per-field confidence and no "page rotated" flag (dev-008 is upside down).
