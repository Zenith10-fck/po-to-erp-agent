"""Shared drawing helpers for all layouts.

Rules that every layout follows (see SPEC.md):
- a printed value is always drawn with ONE draw call (or one call per wrapped line, wrapped
  by whole words), never letter-spaced and never case-changed, so it can be found again in the
  PDF text layer;
- null / "" values are left out together with their label;
- a table column that is null on every line is not drawn.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable

from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase.pdfmetrics import stringWidth

PAGE_W, PAGE_H = letter

BLACK = (0, 0, 0)
GREY = (0.45, 0.45, 0.45)
LIGHT = (0.90, 0.90, 0.90)
WHITE = (1, 1, 1)


def has(v) -> bool:
    """True when a spec value should be printed."""
    return v is not None and str(v).strip() != ""


def block_lines(party: dict | None) -> list[str]:
    """Name + address lines of a party, without empty entries."""
    if not party:
        return []
    out = []
    if has(party.get("name")):
        out.append(str(party["name"]))
    for ln in party.get("address_lines") or []:
        if has(ln):
            out.append(str(ln))
    return out


def pairs(*items) -> list[tuple[str, str]]:
    """Keep only the (label, value) pairs that have a value."""
    return [(lab, str(val)) for lab, val in items if has(val)]


def carrier_pairs(spec: dict, via_label: str, acct_label: str) -> list[tuple[str, str]]:
    """(label, value) pairs for the carrier: name and account number."""
    car = spec.get("carrier") or {}
    acct_lab = car.get("label") if has(car.get("label")) else acct_label
    return pairs((via_label, car.get("name")), (acct_lab, car.get("account_no")))


def po_label(spec: dict, default: str) -> str:
    return str(spec["po_number_label"]) if has(spec.get("po_number_label")) else default


def total_label(spec: dict, default: str = "Total") -> str:
    return str(spec["order_total_label"]) if has(spec.get("order_total_label")) else default


class Ctx:
    """Drawing context: canvas + spec + page counter + handwriting state."""

    def __init__(self, c, spec: dict, total_pages: int, hand_font: str | None = None):
        self.c = c
        self.spec = spec
        self.total_pages = total_pages
        self.page_no = 1
        self.hand_font = hand_font
        self.rng = random.Random(int(spec.get("seed") or 0) * 7919 + 13)
        # dark blue or near-black pen, fixed per document
        self.ink = self.rng.choice([(0.07, 0.11, 0.42), (0.10, 0.10, 0.14), (0.05, 0.08, 0.33)])
        self.page_end_hook: Callable[["Ctx"], None] | None = None

    # ---- printed text -------------------------------------------------
    def text(self, x, y, txt, font="Helvetica", size=9.0, align="l", color=BLACK, width=None):
        """Draw one string with one draw call. `width` shrinks the font so it fits."""
        txt = str(txt)
        if width:
            while size > 4.5 and stringWidth(txt, font, size) > width:
                size -= 0.25
        c = self.c
        c.setFont(font, size)
        c.setFillColorRGB(*color)
        if align == "r":
            c.drawRightString(x, y, txt)
        elif align == "c":
            c.drawCentredString(x, y, txt)
        else:
            c.drawString(x, y, txt)
        return size

    # ---- values (handwritten when the document is handwritten) --------
    def vfont(self, font: str) -> str:
        return self.hand_font or font

    def vsize(self, size: float) -> float:
        return max(size * 1.3, 11.5) if self.hand_font else size

    def value(self, x, y, txt, font="Helvetica", size=9.0, align="l", color=BLACK, width=None):
        """Like text(), but in handwriting with jitter when the document is handwritten."""
        if not self.hand_font:
            return self.text(x, y, txt, font, size, align, color, width)
        txt = str(txt)
        font = self.hand_font
        size = self.vsize(size) * self.rng.uniform(0.94, 1.07)
        if width:
            while size > 6 and stringWidth(txt, font, size) > width:
                size -= 0.25
        dy = self.rng.uniform(-1.3, 1.3)
        dx = self.rng.uniform(-0.5, 2.5) if align == "l" else self.rng.uniform(-2.0, 0.5)
        ang = self.rng.uniform(-1.3, 1.3)
        c = self.c
        c.saveState()
        c.translate(x + dx, y + dy - 1.5)
        c.rotate(ang)
        c.setFont(font, size)
        c.setFillColorRGB(*self.ink)
        if align == "r":
            c.drawRightString(0, 0, txt)
        elif align == "c":
            c.drawCentredString(0, 0, txt)
        else:
            c.drawString(0, 0, txt)
        c.restoreState()
        return size

    # ---- wrapping ------------------------------------------------------
    @staticmethod
    def wrap(txt, font, size, width) -> list[str]:
        """Wrap by whole words. A single over-long word is kept whole."""
        return simpleSplit(str(txt), font, size, width) or [""]

    def para(self, x, y, txt, font="Helvetica", size=9.0, width=400.0, leading=None,
             color=BLACK, value=False) -> float:
        """Draw a wrapped paragraph, one draw call per line. Returns y under the last line."""
        leading = leading or size * 1.25
        f = self.vfont(font) if value else font
        sz = self.vsize(size) if value else size
        for ln in self.wrap(txt, f, sz, width):
            if value:
                self.value(x, y, ln, font, size, color=color, width=width)
            else:
                self.text(x, y, ln, font, size, color=color)
            y -= leading
        return y

    # ---- shapes --------------------------------------------------------
    def line(self, x1, y1, x2, y2, w=0.5, color=BLACK, dash=None):
        c = self.c
        c.setStrokeColorRGB(*color)
        c.setLineWidth(w)
        c.setDash(dash or [])
        c.line(x1, y1, x2, y2)
        c.setDash([])

    def rect(self, x, y, w, h, stroke=BLACK, fill=None, lw=0.5):
        """Rectangle with lower-left corner (x, y)."""
        c = self.c
        c.setLineWidth(lw)
        if stroke:
            c.setStrokeColorRGB(*stroke)
        if fill:
            c.setFillColorRGB(*fill)
        c.rect(x, y, w, h, stroke=1 if stroke else 0, fill=1 if fill else 0)

    # ---- pages ---------------------------------------------------------
    def end_page(self):
        if self.page_end_hook:
            self.page_end_hook(self)

    def new_page(self):
        self.end_page()
        self.c.showPage()
        self.page_no += 1

    def page_label(self) -> str:
        return f"Page {self.page_no} of {self.total_pages}"

    @property
    def visible_note(self) -> str | None:
        sp = self.spec
        if has(sp.get("injection_text")) and sp.get("injection_style") == "visible_note":
            return str(sp["injection_text"])
        return None


# ----------------------------------------------------------------------
# Line-item table
# ----------------------------------------------------------------------
@dataclass
class Col:
    key: str            # key in the line dict
    label: str          # header text
    width: float
    align: str = "l"    # l | r | c
    flex: bool = False  # the flex column wraps and takes the width of dropped columns
    prefix: str = ""    # e.g. "$", drawn in the same call as the value


@dataclass
class TableStyle:
    font: str = "Helvetica"
    bold: str = "Helvetica-Bold"
    size: float = 8.5
    head_size: float = 8.0
    leading: float = 10.5
    pad_x: float = 4.0
    pad_y: float = 4.0
    head_h: float = 18.0
    head_fill: tuple | None = None
    head_color: tuple = BLACK
    grid: str = "full"       # full | rows | zebra | head | none | dashes
    zebra: tuple = (0.94, 0.95, 0.97)
    line_color: tuple = BLACK
    line_w: float = 0.5
    min_row_h: float = 0.0
    extend: str = "none"     # none | lines (run column rules to the bottom) | rows (blank rows)
    head_rule_w: float = 0.8
    bands: bool = False      # zebra bands on top of any grid (green-bar paper)


def active_cols(cols: list[Col], lines: list[dict]) -> list[Col]:
    """Drop columns that are empty on every line; give their width to the flex column."""
    keep, freed = [], 0.0
    for col in cols:
        if any(has(ln.get(col.key)) for ln in lines):
            keep.append(Col(col.key, col.label, col.width, col.align, col.flex, col.prefix))
        else:
            freed += col.width
    flex = [k for k in keep if k.flex] or keep[-1:]
    for k in flex:
        k.width += freed / len(flex)
    return keep


def draw_table(ctx: Ctx, cols: list[Col], lines: list[dict], x: float, y: float, bottom: float,
               st: TableStyle, new_page: Callable[[], tuple[float, float]]) -> float:
    """Draw the line items. Flows onto new pages through `new_page()`, which must start the
    next page, draw its header and return (table_top_y, table_bottom_y). Returns the y of the
    bottom edge of the table on the last page."""
    c = ctx.c
    cols = active_cols(cols, lines)
    width = sum(col.width for col in cols)
    xs = [x]
    for col in cols:
        xs.append(xs[-1] + col.width)
    vfont, vsize = ctx.vfont(st.font), ctx.vsize(st.size)
    lead = max(st.leading, vsize * 1.15)

    def cell_x(i):
        col = cols[i]
        if col.align == "r":
            return xs[i + 1] - st.pad_x
        if col.align == "c":
            return (xs[i] + xs[i + 1]) / 2
        return xs[i] + st.pad_x

    def dash_rule(yy):
        n = int(width / stringWidth("-", st.font, st.size))
        ctx.text(x, yy, "-" * n, st.font, st.size)

    def header(top):
        if st.grid == "dashes":
            dash_rule(top - st.size)
            base = top - st.size - lead
            for i, col in enumerate(cols):
                ctx.text(cell_x(i), base, col.label, st.bold, st.head_size, col.align)
            dash_rule(base - lead)
            return base - lead - 4
        if st.head_fill:
            ctx.rect(x, top - st.head_h, width, st.head_h, stroke=None, fill=st.head_fill)
        base = top - st.head_h / 2 - st.head_size * 0.35
        for i, col in enumerate(cols):
            ctx.text(cell_x(i), base, col.label, st.bold, st.head_size, col.align,
                     color=st.head_color, width=col.width - 2 * st.pad_x)
        if st.grid in ("full", "rows", "zebra", "head"):
            if st.grid != "full":
                ctx.line(x, top, x + width, top, st.head_rule_w, st.line_color)
            ctx.line(x, top - st.head_h, x + width, top - st.head_h, st.head_rule_w, st.line_color)
        return top - st.head_h

    def close(top, yy, limit):
        """Finish one page segment of the table."""
        if st.extend == "rows" and st.min_row_h:
            while yy - st.min_row_h >= limit - 0.01:
                yy -= st.min_row_h
                ctx.line(x, yy, x + width, yy, st.line_w, st.line_color)
        elif st.extend == "lines":
            yy = min(yy, limit)
        if st.grid == "full":
            for xv in xs:
                ctx.line(xv, top, xv, yy, st.line_w, st.line_color)
            ctx.line(x, top, x + width, top, st.line_w, st.line_color)
            ctx.line(x, yy, x + width, yy, st.line_w, st.line_color)
        elif st.grid == "dashes":
            dash_rule(yy - st.size + 2)
            yy -= st.size
        return yy

    seg_top = y
    y = header(y)
    row_on_page = 0
    for ln in lines:
        wrapped = {}
        n = 1
        for i, col in enumerate(cols):
            if col.flex and has(ln.get(col.key)):
                wrapped[i] = ctx.wrap(col.prefix + str(ln[col.key]), vfont, vsize,
                                      col.width - 2 * st.pad_x)
                n = max(n, len(wrapped[i]))
        h = max(st.min_row_h, n * lead + 2 * st.pad_y - (lead - vsize))
        if y - h < bottom and row_on_page > 0:
            close(seg_top, y, bottom)
            y, bottom = new_page()
            seg_top = y
            y = header(y)
            row_on_page = 0
        if (st.grid == "zebra" or st.bands) and row_on_page % 2 == 1:
            ctx.rect(x, y - h, width, h, stroke=None, fill=st.zebra)
        base = y - st.pad_y - vsize * 0.78
        if st.min_row_h and n == 1:
            base = y - h / 2 - vsize * 0.3
        # single-line cells first, wrapped cells last: keeps a wrapped value contiguous
        # in the text layer
        for i, col in enumerate(cols):
            if i in wrapped or not has(ln.get(col.key)):
                continue
            ctx.value(cell_x(i), base, col.prefix + str(ln[col.key]), st.font, st.size, col.align,
                      width=col.width - 2 * st.pad_x)
        for i, parts in wrapped.items():
            yy = base
            for part in parts:
                ctx.value(cell_x(i), yy, part, st.font, st.size, cols[i].align,
                          width=cols[i].width - 2 * st.pad_x)
                yy -= lead
        y -= h
        if st.grid in ("full", "rows"):
            ctx.line(x, y, x + width, y, st.line_w if st.grid == "full" else 0.3, st.line_color)
        row_on_page += 1
    if st.grid in ("zebra", "head"):
        ctx.line(x, y, x + width, y, st.head_rule_w, st.line_color)
    return close(seg_top, y, bottom)


def labelled_box(ctx: Ctx, x, top, w, h, title, lines, title_font="Helvetica-Bold",
                 font="Helvetica", size=9.0, title_fill=LIGHT, title_h=14.0, lead=11.5,
                 bold_first=None):
    """A box with a shaded title strip and text lines inside."""
    if title_fill:
        ctx.rect(x, top - title_h, w, title_h, stroke=None, fill=title_fill)
    ctx.rect(x, top - h, w, h)
    ctx.line(x, top - title_h, x + w, top - title_h)
    ctx.text(x + 5, top - title_h + 4, title, title_font, 7.5)
    yy = top - title_h - size - 3
    for i, ln in enumerate(lines):
        f = bold_first if (i == 0 and bold_first) else font
        ctx.text(x + 6, yy, ln, f, size, width=w - 12)
        yy -= lead


class Flow:
    """Running text that breaks onto new pages. `on_new_page()` must start the next page,
    draw its header and return the y where the text continues."""

    def __init__(self, ctx: Ctx, x, y, width, bottom, font, size, leading, on_new_page):
        self.ctx, self.x, self.y, self.width, self.bottom = ctx, x, y, width, bottom
        self.font, self.size, self.leading = font, size, leading
        self.on_new_page = on_new_page

    def need(self, h):
        if self.y - h < self.bottom:
            self.y = self.on_new_page()

    def space(self, h):
        self.y -= h

    def p(self, txt, font=None, size=None, indent=0.0, hang=0.0, after=None, align="l",
          keep=1):
        """One paragraph. `hang` indents the lines after the first one."""
        font, size = font or self.font, size or self.size
        lead = self.leading * size / self.size
        lines = self.ctx.wrap(txt, font, size, self.width - indent - hang)
        self.need(lead * min(len(lines), max(keep, 2)))
        for i, ln in enumerate(lines):
            self.need(lead)
            x = self.x + indent + (hang if i else 0)
            if align == "r":
                x = self.x + self.width
            self.ctx.text(x, self.y, ln, font, size, align)
            self.y -= lead
        self.y -= self.leading * 0.5 if after is None else after
