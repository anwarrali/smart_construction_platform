"""Open the generated report in Microsoft Word, update every field, save, export PDF.

Usage: python word_finalize.py <report.docx> <output.pdf>
"""
import sys
import time
from pathlib import Path

import pythoncom
import win32com.client as win32

docx_path = str(Path(sys.argv[1]).resolve())
pdf_path = str(Path(sys.argv[2]).resolve())

pythoncom.CoInitialize()
word = win32.DispatchEx("Word.Application")
word.Visible = False
word.DisplayAlerts = 0
try:
    doc = word.Documents.Open(docx_path, ConfirmConversions=False, ReadOnly=False, AddToRecentFiles=False)
    doc.Repaginate()
    for _ in range(2):                      # second pass settles page numbers after TOC growth
        doc.Fields.Update()
        for i in range(1, doc.TablesOfContents.Count + 1):
            doc.TablesOfContents(i).Update()
        for i in range(1, doc.TablesOfFigures.Count + 1):
            doc.TablesOfFigures(i).Update()
        for s in doc.Sections:
            for h in (s.Headers, s.Footers):
                for k in (1, 2, 3):
                    h(k).Range.Fields.Update()
        doc.Repaginate()
    print("pages", doc.ComputeStatistics(2), "toc", doc.TablesOfContents.Count, "tof", doc.TablesOfFigures.Count)
    doc.Save()
    doc.ExportAsFixedFormat(pdf_path, 17, OpenAfterExport=False, OptimizeFor=0, CreateBookmarks=1)
    doc.Close(False)
finally:
    try:
        word.Quit(SaveChanges=0)
    except Exception:
        pass
    pythoncom.CoUninitialize()
print("pdf", pdf_path)
