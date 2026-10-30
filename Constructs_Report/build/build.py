"""Build Graduation_Project_Final_Report.docx from the repository and test evidence.

Run from report/build:  python build.py <path-to-template.docx>
"""
from __future__ import annotations

import copy
import csv
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.shared import Pt, Inches, RGBColor

import engine
from engine import Numbering, Renderer, add_field, add_rich, page_number_format, set_page, setup_styles, write_header_footer
from content_a import REFERENCES, chapter1, chapter2, front_abstract
from content_b import FR_GROUPS, NFR, chapter3, chapter4
from content_c import appendices, chapter5, chapter6

HERE = Path(__file__).resolve().parent
REPORT = HERE.parent
REPO = REPORT.parent
EVIDENCE = REPORT / "evidence"
OUT = REPORT / "Constructs_Graduation_Project_Report.docx"
HEADER = "Al-Quds University  |  Faculty of Engineering"


# --------------------------------------------------------------------------
# evidence gathered from the repository and the executed test suites
# --------------------------------------------------------------------------
def loc(paths):
    total = 0
    for p in paths:
        try:
            total += sum(1 for _ in open(p, encoding="utf-8", errors="ignore"))
        except OSError:
            pass
    return total


def rounded(n):
    return f"{round(n / 1000, 1)}k"


def gather():
    be = REPO / "backend"
    py = [p for p in (be / "app").rglob("*.py") if "__pycache__" not in p.parts]
    api_src = "".join(p.read_text(encoding="utf-8") for p in (be / "app" / "api").glob("*.py"))
    routes = len(re.findall(r"^@router\.(get|post|put|patch|delete)\(", api_src, re.M))
    router_modules = len(re.findall(r"api_router\.include_router\(", (be / "app" / "api" / "__init__.py").read_text(encoding="utf-8")))
    tables = len(set(re.findall(r'__tablename__\s*=\s*"(\w+)"', "".join(p.read_text(encoding="utf-8") for p in (be / "app" / "models").glob("*.py")))))
    migrations = len(list((be / "alembic" / "versions").glob("*.py")))
    perm_src = (be / "app" / "core" / "permission_catalogue.py").read_text(encoding="utf-8")
    inventory = (REPO / "docs" / "permission_inventory_table.md").read_text(encoding="utf-8")
    permissions = int(re.search(r"^(\d+) permissions", inventory, re.M).group(1))
    role_templates = len(re.findall(r'^\s+_t\("', (be / "app" / "core" / "role_templates.py").read_text(encoding="utf-8"), re.M))
    fe = [p for p in (REPO / "frontend" / "src").rglob("*") if p.suffix in (".ts", ".tsx")]
    fe_tests = [p for p in fe if ".test." in p.name]
    dart = list((REPO / "mobile_app" / "lib").rglob("*.dart"))
    dart_tests = list((REPO / "mobile_app" / "test").rglob("*_test.dart"))
    be_tests = list((be / "tests").glob("test_*.py"))
    test_funcs = sum(len(re.findall(r"^\s*(?:async )?def test_", p.read_text(encoding="utf-8"), re.M)) for p in be_tests)

    log = subprocess.run(["git", "log", "--format=%ad", "--date=short"], cwd=REPO, capture_output=True, text=True).stdout.split()

    # backend results
    root = ET.parse(EVIDENCE / "backend_junit.xml").getroot()
    suite = root if root.tag == "testsuite" else root[0]
    total, failed, errors, skipped = (int(suite.get(k)) for k in ("tests", "failures", "errors", "skipped"))
    groups = json.loads((EVIDENCE / "backend_groups.json").read_text())

    full = (EVIDENCE / "frontend_vitest_full.txt").read_text(encoding="utf-8")
    m_files = re.search(r"Test Files\s+(\d+) failed \| (\d+) passed \((\d+)\)", full)
    m_tests = re.search(r"Tests\s+(\d+) failed \| (\d+) passed \((\d+)\)", full)
    rerun = (EVIDENCE / "frontend_vitest_rerun.txt").read_text(encoding="utf-8")
    m_rerun = re.search(r"Tests\s+(\d+) passed \((\d+)\)", rerun)
    flutter = (EVIDENCE / "flutter_test.txt").read_text(encoding="utf-8")
    m_fl = re.findall(r"\+(\d+): All tests passed!", flutter)

    E = dict(
        py_modules=len(py), backend_loc=rounded(loc(py)), routes=routes, router_modules=router_modules,
        tables=tables, migrations=migrations, permissions=permissions, role_templates=role_templates,
        fe_files=len(fe), frontend_loc=rounded(loc(fe)), fe_test_files=len(fe_tests),
        dart_files=len(dart), mobile_loc=rounded(loc(dart)), dart_test_files=len(dart_tests),
        be_test_files=len(be_tests), be_test_funcs=test_funcs,
        commits=len(log), first_commit=min(log), last_commit=max(log),
        be_total=total, be_failed=failed + errors, be_skipped=skipped, be_passed=total - failed - errors - skipped,
        groups=groups,
        fe_files_run=m_files.group(3), fe_tests_run=m_tests.group(3),
        fe_full_result=f"{m_tests.group(2)} passed, {m_tests.group(1)} failed (timeouts)",
        fe_passed=int(m_tests.group(2)), fe_failed=int(m_tests.group(1)),
        fe_rerun_tests=m_rerun.group(2), fe_rerun_result=f"{m_rerun.group(1)} passed, 0 failed",
        mobile_tests=m_fl[-1], mobile_result="All passed",
    )
    E["backend_summary"] = f"the backend suite ran {total} tests with {E['be_passed']} passing, {E['be_failed']} environment-dependent failure and {skipped} intentional skip"
    E["frontend_summary"] = f"the web suite passed {m_tests.group(2)} of {m_tests.group(3)} tests, the {m_tests.group(1)} remaining being timeouts that passed on a serial re-run"
    E["mobile_summary"] = f"the mobile suite passed all {E['mobile_tests']} tests"
    return E


# --------------------------------------------------------------------------
# front matter
# --------------------------------------------------------------------------
COVER = {
    "Title of the Project": "Constructs",
    "Your Names": "Anwar Roumanen",
    "XXXXXXXXXX": "Prof. Dr. Eng. Salaheddin Odeh",
    "Palestine, 2022": "Palestine, 2026",
}
SUBTITLE = ("An AI-Assisted Construction Intelligence and Collaboration Platform "
            "for Design-to-Execution Integration")


def replace_text(p, new, highlight=False):
    runs = p.runs
    runs[0].text = new
    for r in runs[1:]:
        r.text = ""
    if highlight:
        for r in runs:
            r.font.highlight_color = 7


def insert_after(p, new_p):
    p._p.addnext(new_p)


def front_matter(doc, template):
    tpl = Document(template)
    body = doc.element.body
    sectPr = body.sectPr

    def put(el):
        # the template marks cover lines as outline level 0; they must stay out of the TOC
        from docx.oxml.ns import qn as _qn
        for lvl in el.iter(_qn("w:outlineLvl")):
            lvl.getparent().remove(lvl)
        sectPr.addprevious(el)

    tparas = tpl.paragraphs
    for idx in range(0, 14):                       # cover, through "Palestine, 2022"
        put(copy.deepcopy(tparas[idx]._p))
    for p in doc.paragraphs[:14]:
        key = p.text.strip()
        if key in COVER:
            replace_text(p, COVER[key])
        if key == "Title of the Project":
            title_p = p
    # subtitle directly under the title, in the template's typography
    sub = copy.deepcopy(title_p._p)
    title_p._p.addnext(sub)
    from docx.text.paragraph import Paragraph
    sp = Paragraph(sub, title_p._parent)
    replace_text(sp, SUBTITLE)
    for r in sp.runs:
        r.bold = False
        r.italic = True
        r.font.size = Pt(14)
    sp.paragraph_format.space_after = Pt(18)

    def page_break():
        p = doc.add_paragraph()
        p.add_run().add_break(WD_BREAK.PAGE)

    def front_title(text):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(text); r.bold = True; r.font.size = Pt(20)
        p.paragraph_format.space_after = Pt(18)
        return p

    # dedication and acknowledgement: template headings, author text still to be written
    page_break()
    put(copy.deepcopy(tparas[18]._p))
    d = copy.deepcopy(tparas[19]._p); put(d)
    replace_text(doc.paragraphs[-1], "[Dedication to be written by the author.]", highlight=True)
    page_break()
    put(copy.deepcopy(tparas[32]._p))
    put(copy.deepcopy(tparas[33]._p))
    replace_text(doc.paragraphs[-1], "[Acknowledgement to be written by the author, for example thanking the supervisor, "
                                     "Prof. Dr. Eng. Salaheddin Odeh, and the Department of Computer Engineering.]", highlight=True)
    return front_title, page_break


class ReportRenderer(Renderer):
    def b_ref(self, n, text):
        p = self.doc.add_paragraph()
        p.paragraph_format.left_indent = Inches(0.45)
        p.paragraph_format.first_line_indent = Inches(-0.45)
        p.paragraph_format.space_after = Pt(4)
        add_rich(p, f"[{n}]\t" + text, size=10)
        p.paragraph_format.tab_stops.add_tab_stop(Inches(0.45))


FIG_SOURCES = {}


def write_traceability(numbering):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    import content_b as cb
    fig_of = {"Use cases": "3.2, 3.3", "Task": "3.4, 3.5"}
    wb = Workbook()
    ws = wb.active
    ws.title = "Functional"
    head = ["Requirement ID", "Functional area", "Title", "Requirement", "Stakeholders", "Implementation evidence",
            "Automated tests", "Status", "Origin"]
    ws.append(head)
    rows_csv = [["Requirement ID", "Type", "Area", "Title", "Requirement", "Stakeholders", "Implementation evidence", "Automated tests", "Status", "Origin"]]
    for area, items in cb.FR_GROUPS:
        for (i, t, txt, a, e, tests, st, src) in items:
            ws.append([i, area, t, txt, a, e, tests, st, src])
            rows_csv.append([i, "Functional", area, t, txt, a, e, tests, st, src])
    ws2 = wb.create_sheet("Non-functional")
    ws2.append(["Requirement ID", "Category", "Requirement", "Evidence class", "Evidence"])
    for (i, c, txt, cls, ev) in cb.NFR:
        ws2.append([i, c, txt, cls, ev])
        rows_csv.append([i, "Non-functional", c, "", txt, "All", "", ev, cls, ""])
    ws3 = wb.create_sheet("Legend")
    for line in [
        ["Status", "Meaning"],
        ["Implemented", "Code and automated tests exist; tests executed 24 Oct 2026 (see evidence folder)."],
        ["Partial", "Part of the requirement is implemented; the remainder is missing or in transition."],
        ["Implemented, disabled by default", "Capability exists and is tested but is switched off by configuration."],
        ["Note", "Tests listed are the modules that exercise the requirement; a listed test does not prove end-to-end user workflows."],
    ]:
        ws3.append(line)
    for sheet in (ws, ws2, ws3):
        for c in sheet[1]:
            c.font = Font(bold=True)
            c.fill = PatternFill("solid", fgColor="DCE6F0")
        for col in sheet.columns:
            width = min(60, max(len(str(x.value or "")) for x in col) + 2)
            sheet.column_dimensions[col[0].column_letter].width = width
            for x in col:
                x.alignment = Alignment(wrap_text=True, vertical="top")
        sheet.freeze_panes = "A2"
    wb.save(REPORT / "Constructs_Traceability_Matrix.xlsx")
    with open(REPORT / "Constructs_Traceability_Matrix.csv", "w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(rows_csv)


def write_diagram_readme(numbering):
    lines = ["# Diagram sources", "",
             "Each figure in the report, its editable source and its rendered image.", "",
             "Regenerate PlantUML diagrams with `java -jar plantuml.jar -tpng -o ../png src/*.puml` (PlantUML 1.2024.7, "
             "Smetana layout, shared style in `src/_style.iuml`). Regenerate the concept diagram with `python src/00_concept.py` "
             "(matplotlib).", "", "| Figure | Caption | Source | Image |", "| --- | --- | --- | --- |"]
    for key, (chap, n) in sorted(numbering.fig.items(), key=lambda kv: (kv[1][0], kv[1][1])):
        png = FIG_SOURCES.get(key, "")
        stem = png.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        src = f"src/{stem}.py" if stem == "00_concept" else f"src/{stem}.puml"
        lines.append(f"| {chap}.{n} | {FIG_CAPTIONS.get(key, '')} | `{src}` | `png/{stem}.png` |")
    (REPORT / "diagrams" / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


FIG_CAPTIONS = {}


def main(template):
    E = gather()
    body_blocks = chapter1(E) + chapter2(E) + chapter3(E) + chapter4(E) + chapter5(E) + chapter6(E)
    # chapter 1 starts on a fresh section page, so it needs no page break of its own
    body_blocks[0] = ("h1", body_blocks[0][1], False)
    pre = appendices(E, [], {})                      # numbering pass needs the table blocks
    numbering = Numbering(front_abstract(E) + body_blocks + pre, REFERENCES)
    for b in body_blocks:
        if b[0] == "fig":
            FIG_SOURCES[b[1]] = b[2]
            FIG_CAPTIONS[b[1]] = b[3]
    refs = sorted(((numbering.cite[k], REFERENCES[k]) for k in REFERENCES), key=lambda x: x[0])
    app_blocks = appendices(E, refs, {})

    doc = Document()
    setup_styles(doc)
    sec0 = doc.sections[0]
    set_page(sec0)
    front_title, page_break = front_matter(doc, template)
    sec0.different_first_page_header_footer = False
    write_header_footer(sec0, None, numbered=False)

    # front matter section (roman numerals)
    sec1 = doc.add_section(WD_SECTION.NEW_PAGE)
    set_page(sec1)
    write_header_footer(sec1, None, numbered=True)
    page_number_format(sec1, fmt="lowerRoman", start=1)
    r = ReportRenderer(doc, numbering, HEADER)
    front_title("Abstract")
    r.render(front_abstract(E))
    page_break()
    front_title("Table of Contents")
    p = doc.add_paragraph(); add_field(p, 'TOC \\o "1-3" \\h \\z \\u', "Right-click and choose Update Field to build the table of contents.")
    page_break()
    front_title("List of Figures")
    p = doc.add_paragraph(); add_field(p, 'TOC \\h \\z \\c "Figure"', "Update field to build the list of figures.")
    page_break()
    front_title("List of Tables")
    p = doc.add_paragraph(); add_field(p, 'TOC \\h \\z \\c "Table"', "Update field to build the list of tables.")
    doc.add_paragraph()
    t = doc.add_paragraph(); rr = t.add_run("List of Listings"); rr.bold = True; rr.font.size = Pt(14)
    p = doc.add_paragraph(); add_field(p, 'TOC \\h \\z \\c "Listing"', "Update field to build the list of listings.")

    # main body (arabic numerals from 1)
    sec2 = doc.add_section(WD_SECTION.NEW_PAGE)
    set_page(sec2)
    write_header_footer(sec2, HEADER, numbered=True)
    page_number_format(sec2, fmt="decimal", start=1)
    r.render(body_blocks + app_blocks)

    # fields (TOC, SEQ, PAGE) are refreshed by word_finalize.py through Word itself
    engine.repair_order(doc)
    doc.core_properties.title = "Constructs - Graduation Project Report"
    doc.core_properties.author = "Anwar Roumanen"
    doc.core_properties.subject = "BSc Computer Engineering graduation project, Al-Quds University"
    doc.save(OUT)

    write_traceability(numbering)
    write_diagram_readme(numbering)
    (REPORT / "build" / "evidence_numbers.json").write_text(json.dumps({k: v for k, v in E.items() if k != "groups"}, indent=1))
    (REPORT / "build" / "figure_scales.json").write_text(json.dumps(r.figure_scales, indent=1))
    print("figures", len(numbering.fig), "tables", len(numbering.tab), "listings", len(numbering.lst), "refs", len(numbering.cite))
    print("saved", OUT)


if __name__ == "__main__":
    main(sys.argv[1])
