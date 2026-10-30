"""Rendering engine for the graduation report.

Content modules produce a flat list of blocks; this module numbers figures,
tables and citations, then renders everything into a python-docx Document whose
cover page is copied from the university template.
"""
from __future__ import annotations

import copy
import re
from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT, WD_SECTION
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor, Emu
from PIL import Image

FONT = "Times New Roman"
MONO = "Consolas"
ACCENT = RGBColor(0x1F, 0x38, 0x64)
HEADER_FILL = "DCE6F0"
PAGE_W, PAGE_H, MARGIN = 8.5, 11.0, 1.0  # US Letter, as in the template
PORTRAIT_W, PORTRAIT_H = PAGE_W - 2 * MARGIN, PAGE_H - 2 * MARGIN
DIAGRAM_DPI = 200


# --------------------------------------------------------------------------
# low-level helpers
# --------------------------------------------------------------------------
def _el(tag, **attrs):
    e = OxmlElement(tag)
    for k, v in attrs.items():
        e.set(qn(k), str(v))
    return e


def add_field(paragraph, instr, placeholder="", bold=None, size=None):
    """Insert a complex field (TOC, PAGE, SEQ ...) with a cached result."""
    def run_with(child):
        r = paragraph.add_run()
        if bold is not None:
            r.bold = bold
        if size:
            r.font.size = Pt(size)
        r._r.append(child)
        return r
    run_with(_el("w:fldChar", **{"w:fldCharType": "begin", "w:dirty": "true"}))
    it = _el("w:instrText")
    it.set(qn("xml:space"), "preserve")
    it.text = f" {instr} "
    run_with(it)
    run_with(_el("w:fldChar", **{"w:fldCharType": "separate"}))
    r = paragraph.add_run(placeholder)
    if bold is not None:
        r.bold = bold
    if size:
        r.font.size = Pt(size)
    run_with(_el("w:fldChar", **{"w:fldCharType": "end"}))


def shade(cell, fill):
    tcPr = cell._tc.get_or_add_tcPr()
    tcPr.append(_el("w:shd", **{"w:val": "clear", "w:color": "auto", "w:fill": fill}))


def set_cell_margins(table, top=50, bottom=50, left=80, right=80):
    tblPr = table._tbl.tblPr
    mar = _el("w:tblCellMar")
    for side, val in (("top", top), ("left", left), ("bottom", bottom), ("right", right)):
        mar.append(_el(f"w:{side}", **{"w:w": val, "w:type": "dxa"}))
    tblPr.append(mar)


def repeat_header(row):
    trPr = row._tr.get_or_add_trPr()
    trPr.append(_el("w:tblHeader", **{"w:val": "true"}))


def cant_split(row):
    trPr = row._tr.get_or_add_trPr()
    trPr.append(_el("w:cantSplit", **{"w:val": "true"}))


def keep_next(p, on=True):
    p.paragraph_format.keep_with_next = on


INLINE = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`|_\{[^}]+\}_)")


def add_rich(paragraph, text, size=None, color=None):
    """Very small inline markup: **bold**, `code`, _{italic}_."""
    for part in INLINE.split(text):
        if not part:
            continue
        if part.startswith("**"):
            r = paragraph.add_run(part[2:-2]); r.bold = True
        elif part.startswith("`"):
            r = paragraph.add_run(part[1:-1]); r.font.name = MONO
            r._r.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), MONO)
            r.font.size = Pt((size or 11) - 1.5)
            if size:
                pass
            continue
        elif part.startswith("_{"):
            r = paragraph.add_run(part[2:-2]); r.italic = True
        else:
            r = paragraph.add_run(part)
        if size:
            r.font.size = Pt(size)
        if color:
            r.font.color.rgb = color


# --------------------------------------------------------------------------
# document setup
# --------------------------------------------------------------------------
def setup_styles(doc):
    st = doc.styles
    normal = st["Normal"]
    normal.font.name = FONT
    normal.font.size = Pt(12)
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    pf = normal.paragraph_format
    pf.space_after = Pt(6)
    pf.line_spacing = 1.3

    for name, size, before, after, color in (
        ("Heading 1", 18, 0, 16, ACCENT),
        ("Heading 2", 14, 16, 6, ACCENT),
        ("Heading 3", 12.5, 12, 4, ACCENT),
    ):
        s = st[name]
        s.font.name = FONT
        s.font.size = Pt(size)
        s.font.bold = True
        s.font.italic = False
        s.font.color.rgb = color
        rpr = s._element.get_or_add_rPr()
        rf = rpr.get_or_add_rFonts()
        for a in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
            rf.set(qn(a), FONT)
        for a in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
            if rf.get(qn(a)) is not None:
                del rf.attrib[qn(a)]
        s.paragraph_format.space_before = Pt(before)
        s.paragraph_format.space_after = Pt(after)
        s.paragraph_format.keep_with_next = True
        s.paragraph_format.keep_together = True
    st["Heading 1"].paragraph_format.page_break_before = False

    cap = st["Caption"]
    cap.font.name = FONT
    cap.font.size = Pt(10.5)
    cap.font.bold = False
    cap.font.italic = False
    cap.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
    cap.paragraph_format.space_after = Pt(10)
    cap.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER

    for name in ("List Bullet", "List Bullet 2", "List Number"):
        s = st[name]
        s.font.name = FONT
        s.font.size = Pt(12)
        s.paragraph_format.space_after = Pt(3)

    code = st.add_style("Code Block", WD_STYLE_TYPE.PARAGRAPH)
    code.base_style = st["Normal"]
    code.font.name = MONO
    code.font.size = Pt(8.5)
    code._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), MONO)
    code.paragraph_format.space_after = Pt(0)
    code.paragraph_format.line_spacing = 1.0

    for i in (1, 2, 3):
        try:
            t = st[f"TOC {i}"]
        except KeyError:
            t = st.add_style(f"TOC {i}", WD_STYLE_TYPE.PARAGRAPH)
            t.base_style = st["Normal"]
        t.paragraph_format.space_after = Pt(2)
        t.paragraph_format.left_indent = Inches(0.25 * (i - 1))


def set_page(section, landscape=False):
    if landscape:
        section.orientation = WD_ORIENT.LANDSCAPE
        section.page_width, section.page_height = Inches(PAGE_H), Inches(PAGE_W)
    else:
        section.orientation = WD_ORIENT.PORTRAIT
        section.page_width, section.page_height = Inches(PAGE_W), Inches(PAGE_H)
    for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(section, side, Inches(MARGIN))
    section.header_distance = Inches(0.45)
    section.footer_distance = Inches(0.45)


def page_number_format(section, fmt=None, start=None):
    sectPr = section._sectPr
    for old in sectPr.findall(qn("w:pgNumType")):
        sectPr.remove(old)
    attrs = {}
    if fmt:
        attrs["w:fmt"] = fmt
    if start is not None:
        attrs["w:start"] = start
    if attrs:
        sectPr.append(_el("w:pgNumType", **attrs))


def write_header_footer(section, header_text, numbered=True):
    section.header.is_linked_to_previous = False
    section.footer.is_linked_to_previous = False
    hp = section.header.paragraphs[0]
    hp.text = ""
    if header_text:
        add_rich(hp, header_text, size=8.5, color=RGBColor(0x59, 0x59, 0x59))
        hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        pPr = hp._p.get_or_add_pPr()
        bdr = _el("w:pBdr")
        bdr.append(_el("w:bottom", **{"w:val": "single", "w:sz": 4, "w:space": 1, "w:color": "A6A6A6"}))
        pPr.append(bdr)
    fp = section.footer.paragraphs[0]
    fp.text = ""
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if numbered:
        add_field(fp, "PAGE", "1", size=9.5)


# --------------------------------------------------------------------------
# block numbering pass
# --------------------------------------------------------------------------
TOKEN = re.compile(r"\{(fig|tab|cite|lst):([A-Za-z0-9_\-,]+)\}")


class Numbering:
    """Figures, tables and listings are numbered per chapter (Figure 3.2);
    citations in order of first appearance (IEEE)."""

    def __init__(self, blocks, references):
        self.fig, self.tab, self.lst, self.cite = {}, {}, {}, {}
        self.references = references
        chap, counts = "0", {"fig": 0, "table": 0, "code": 0}
        for b in blocks:
            kind = b[0]
            if kind == "chap":
                chap, counts = b[1], {"fig": 0, "table": 0, "code": 0}
            elif kind in counts:
                target = {"fig": self.fig, "table": self.tab, "code": self.lst}[kind]
                if b[1] in target:
                    raise KeyError(f"duplicate {kind} key {b[1]}")
                counts[kind] += 1
                target[b[1]] = (chap, counts[kind])
        for b in blocks:
            for text in _texts(b):
                for m in TOKEN.finditer(text):
                    if m.group(1) == "cite":
                        for key in m.group(2).split(","):
                            if key not in references:
                                raise KeyError(f"unknown reference {key}")
                            self.cite.setdefault(key, len(self.cite) + 1)
        unused = set(references) - set(self.cite)
        if unused:
            raise ValueError(f"references never cited: {sorted(unused)}")

    @staticmethod
    def label(entry):
        return f"{entry[0]}.{entry[1]}"

    def sub(self, text):
        def repl(m):
            kind, keys = m.group(1), m.group(2)
            if kind == "fig":
                return f"Figure {self.label(self.fig[keys])}"
            if kind == "tab":
                return f"Table {self.label(self.tab[keys])}"
            if kind == "lst":
                return f"Listing {self.label(self.lst[keys])}"
            nums = sorted(self.cite[k] for k in keys.split(","))
            return "[" + "], [".join(str(n) for n in nums) + "]"
        return TOKEN.sub(repl, text)


def _texts(block):
    out = []
    for item in block[1:]:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, (list, tuple)):
            for x in item:
                if isinstance(x, str):
                    out.append(x)
                elif isinstance(x, (list, tuple)):
                    out.extend(y for y in x if isinstance(y, str))
    return out


# --------------------------------------------------------------------------
# renderer
# --------------------------------------------------------------------------
class Renderer:
    def __init__(self, doc, numbering, header_text):
        self.doc = doc
        self.n = numbering
        self.header_text = header_text
        self.landscape = False

    @property
    def usable(self):
        if self.landscape:
            return PAGE_H - 2 * MARGIN, PAGE_W - 2 * MARGIN
        return PORTRAIT_W, PORTRAIT_H

    def para(self, text, style=None, align=None, size=None, italic=False):
        p = self.doc.add_paragraph(style=style)
        add_rich(p, self.n.sub(text), size=size)
        if italic:
            for r in p.runs:
                r.italic = True
        if align == "j":
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        elif align == "c":
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        return p

    def render(self, blocks):
        for b in blocks:
            getattr(self, "b_" + b[0])(*b[1:])

    # headings ------------------------------------------------------------
    def b_h1(self, text, new_page=True):
        if new_page and not self.landscape:
            self.doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
            # remove the empty paragraph's trailing spacing effect
            self.doc.paragraphs[-1].paragraph_format.space_after = Pt(0)
        self.doc.add_heading(self.n.sub(text), level=1)

    def b_h2(self, text):
        self.doc.add_heading(self.n.sub(text), level=2)

    def b_h3(self, text):
        self.doc.add_heading(self.n.sub(text), level=3)

    # text ----------------------------------------------------------------
    def b_p(self, text):
        self.para(text, align="j")

    def b_lead(self, text):
        p = self.para(text, align="j")
        keep_next(p)

    def b_note(self, text):
        p = self.para(text, align="j", size=10, italic=True)
        p.paragraph_format.left_indent = Inches(0.3)
        p.paragraph_format.right_indent = Inches(0.3)

    def b_bullets(self, items):
        for it in items:
            p = self.para(it, style="List Bullet")
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT

    def b_nums(self, items):
        for i, it in enumerate(items, 1):
            p = self.doc.add_paragraph()
            p.paragraph_format.left_indent = Inches(0.35)
            p.paragraph_format.first_line_indent = Inches(-0.25)
            p.paragraph_format.space_after = Pt(3)
            add_rich(p, f"{i}.  " + self.n.sub(it))

    def b_pagebreak(self):
        self.doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    # tables --------------------------------------------------------------
    def b_table(self, key, caption, header, rows, widths, font=9.5):
        cap = self.doc.add_paragraph(style="Caption")
        cap.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
        cap.paragraph_format.space_after = Pt(3)
        keep_next(cap)
        self._caption_label(cap, "Table", self.n.tab[key])
        r = cap.add_run(": " + self.n.sub(caption)); r.italic = False
        for run in cap.runs:
            run.italic = False
        total = sum(widths)
        maxw = self.usable[0]
        scale = min(1.0, maxw / total)
        widths = [w * scale for w in widths]
        t = self.doc.add_table(rows=1, cols=len(header))
        t.style = self.doc.styles["Table Grid"]
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        t.autofit = False
        set_cell_margins(t)
        hdr = t.rows[0]
        repeat_header(hdr)
        cant_split(hdr)
        for i, h in enumerate(header):
            c = hdr.cells[i]
            c.width = Inches(widths[i])
            shade(c, HEADER_FILL)
            c.paragraphs[0].text = ""
            rr = c.paragraphs[0].add_run(h); rr.bold = True; rr.font.size = Pt(font)
            c.paragraphs[0].paragraph_format.space_after = Pt(0)
            keep_next(c.paragraphs[0])
        for row in rows:
            cells = t.add_row()
            cant_split(cells)
            for i, val in enumerate(row):
                c = cells.cells[i]
                c.width = Inches(widths[i])
                c.paragraphs[0].text = ""
                lines = val.split("\n") if isinstance(val, str) else [str(val)]
                for j, line in enumerate(lines):
                    p = c.paragraphs[0] if j == 0 else c.add_paragraph()
                    add_rich(p, self.n.sub(line), size=font)
                    p.paragraph_format.space_after = Pt(0)
                    p.paragraph_format.line_spacing = 1.0
        # short tables stay on one page: every row keeps with the next
        if len(rows) <= 12:
            for row in t.rows[:-1]:
                for c in row.cells:
                    for para in c.paragraphs:
                        keep_next(para)
        # grid widths so Word honours the layout
        tblGrid = t._tbl.tblGrid
        for gc, w in zip(tblGrid.findall(qn("w:gridCol")), widths):
            gc.set(qn("w:w"), str(int(w * 1440)))
        tblPr = t._tbl.tblPr
        if tblPr.find(qn("w:tblLayout")) is None:
            tblPr.append(_el("w:tblLayout", **{"w:type": "fixed"}))
        spacer = self.doc.add_paragraph()
        spacer.paragraph_format.space_after = Pt(4)

    # figures -------------------------------------------------------------
    def b_fig(self, key, path, caption, max_h_frac=0.80, max_w_frac=1.0):
        path = Path(path)
        w_px, h_px = Image.open(path).size
        nat_w, nat_h = w_px / DIAGRAM_DPI, h_px / DIAGRAM_DPI
        uw, uh = self.usable
        # every figure may use up to 90% of the usable height; scale never exceeds 1.0
        max_w, max_h = uw * max_w_frac, uh * max(max_h_frac, 0.9)
        scale = min(1.0, max_w / nat_w, max_h / nat_h)
        width = nat_w * scale
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(6)
        p.paragraph_format.space_after = Pt(2)
        keep_next(p)
        p.add_run().add_picture(str(path), width=Inches(width))
        cap = self.doc.add_paragraph(style="Caption")
        self._caption_label(cap, "Figure", self.n.fig[key])
        r = cap.add_run(": " + self.n.sub(caption)); r.italic = False
        self.figure_scales = getattr(self, "figure_scales", {})
        self.figure_scales[key] = (path.name, round(scale, 3), round(width, 2))

    # code listings -------------------------------------------------------
    def b_code(self, key, caption, code):
        cap = self.doc.add_paragraph(style="Caption")
        cap.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
        cap.paragraph_format.space_after = Pt(3)
        keep_next(cap)
        self._caption_label(cap, "Listing", self.n.lst[key])
        r = cap.add_run(": " + self.n.sub(caption)); r.italic = False
        lines = code.strip("\n").split("\n")
        for i, line in enumerate(lines):
            p = self.doc.add_paragraph(style="Code Block")
            run = p.add_run(line if line else " ")
            pPr = p._p.get_or_add_pPr()
            pPr.append(_el("w:shd", **{"w:val": "clear", "w:color": "auto", "w:fill": "F3F5F7"}))
            bdr = _el("w:pBdr")
            for side in ("left", "right") + (("top",) if i == 0 else ()) + (("bottom",) if i == len(lines) - 1 else ()):
                bdr.append(_el(f"w:{side}", **{"w:val": "single", "w:sz": 4, "w:space": 4, "w:color": "BFC7D1"}))
            pPr.append(bdr)
            p.paragraph_format.left_indent = Inches(0.1)
            p.paragraph_format.right_indent = Inches(0.1)
            if i < len(lines) - 1:
                keep_next(p)
        sp = self.doc.add_paragraph()
        sp.paragraph_format.space_after = Pt(4)

    def _caption_label(self, cap, label, entry):
        r = cap.add_run(f"{label} {entry[0]}."); r.bold = True; r.italic = False
        add_field(cap, f"SEQ {label} \\* ARABIC", str(entry[1]), bold=True)

    def b_chap(self, label):
        """Reset the SEQ counters at a chapter start with hidden fields."""
        p = self.doc.add_paragraph()
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.keep_with_next = True
        for seq in ("Figure", "Table", "Listing"):
            add_field(p, f"SEQ {seq} \\r 0 \\h", "")
        for r in p.runs:
            r.font.size = Pt(1)

    # sections ------------------------------------------------------------
    def b_landscape(self, on):
        sec = self.doc.add_section(WD_SECTION.NEW_PAGE)
        self.landscape = on
        set_page(sec, landscape=on)
        write_header_footer(sec, self.header_text)
        page_number_format(sec)


# --------------------------------------------------------------------------
# front matter
# --------------------------------------------------------------------------
def copy_cover(doc, template_path, replacements):
    """Copy the template's cover, dedication and acknowledgement paragraphs."""
    tpl = Document(template_path)
    body = doc.element.body
    first = body[0] if len(body) else None
    paras = tpl.paragraphs
    for idx in range(0, 17):
        el = copy.deepcopy(paras[idx]._p)
        body.insert(list(body).index(doc.element.body.sectPr) if first is None else len(body) - 1, el)
    # apply replacements on copied runs
    for p in doc.paragraphs[:17]:
        full = p.text
        for old, new in replacements.items():
            if full.strip() == old:
                runs = p.runs
                runs[0].text = new
                for r in runs[1:]:
                    r.text = ""
                if new.startswith("[") and new.endswith("]"):
                    for r in runs:
                        r.font.highlight_color = 7  # yellow, editable placeholder
    return doc


# --------------------------------------------------------------------------
# schema-order repair: children appended above must follow the OOXML sequence
# --------------------------------------------------------------------------
PPR_ORDER = ("pStyle keepNext keepLines pageBreakBefore framePr widowControl numPr suppressLineNumbers pBdr shd tabs "
             "suppressAutoHyphens kinsoku wordWrap overflowPunct topLinePunct autoSpaceDE autoSpaceDN bidi adjustRightInd "
             "snapToGrid spacing ind contextualSpacing mirrorIndents suppressOverlap jc textDirection textAlignment "
             "textboxTightWrap outlineLvl divId cnfStyle rPr sectPr pPrChange").split()
TBLPR_ORDER = ("tblStyle tblpPr tblOverlap bidiVisual tblStyleRowBandSize tblStyleColBandSize tblW jc tblCellSpacing tblInd "
               "tblBorders shd tblLayout tblCellMar tblLook tblCaption tblDescription tblPrChange").split()


PBDR_ORDER = "top left bottom right between bar".split()
SECTPR_ORDER = ("headerReference footerReference footnotePr endnotePr type pgSz pgMar paperSrc pgBorders lnNumType "
                "pgNumType cols formProt vAlign noEndnote titlePg textDirection bidi rtlGutter docGrid printerSettings "
                "sectPrChange").split()


def _reorder(el, order):
    rank = {qn("w:" + n): i for i, n in enumerate(order)}
    kids = list(el)
    kids_sorted = sorted(kids, key=lambda k: rank.get(k.tag, len(order)))
    if kids_sorted != kids:
        for k in kids:
            el.remove(k)
        for k in kids_sorted:
            el.append(k)


def repair_order(doc):
    parts = [doc.element]
    for s in doc.sections:
        for hf in (s.header, s.footer, s.first_page_header, s.first_page_footer):
            if not hf.is_linked_to_previous:
                parts.append(hf._element)
    for root in parts:
        for ppr in root.iter(qn("w:pPr")):
            _reorder(ppr, PPR_ORDER)
        for tpr in root.iter(qn("w:tblPr")):
            seen = set()
            for k in list(tpr):
                if k.tag in seen:
                    tpr.remove(k)
                seen.add(k.tag)
            _reorder(tpr, TBLPR_ORDER)
        for b in root.iter(qn("w:pBdr")):
            _reorder(b, PBDR_ORDER)
        for sp in root.iter(qn("w:sectPr")):
            _reorder(sp, SECTPR_ORDER)
    zoom = doc.settings.element.find(qn("w:zoom"))
    if zoom is not None and zoom.get(qn("w:percent")) is None:
        zoom.set(qn("w:percent"), "100")
