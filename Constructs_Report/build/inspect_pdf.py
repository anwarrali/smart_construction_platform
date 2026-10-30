"""Rasterize the exported PDF and flag layout problems.

Usage: python inspect_pdf.py <report.pdf> <out_dir>
Checks: images or text outside the 1-inch margins, near-empty pages, leftover
placeholder markers, and the page count.
"""
import re
import sys
from pathlib import Path

import pymupdf

pdf, out = Path(sys.argv[1]), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
doc = pymupdf.open(pdf)
MARGIN = 72 - 4  # points, small tolerance
problems = []
for i, page in enumerate(doc, 1):
    r = page.rect
    inner = pymupdf.Rect(MARGIN, MARGIN - 30, r.width - MARGIN, r.height - MARGIN + 30)  # header/footer band allowed
    for img in page.get_image_info():
        b = pymupdf.Rect(img["bbox"])
        if not inner.contains(b):
            problems.append(f"p{i}: image outside margins {tuple(round(x) for x in b)}")
    text = page.get_text()
    words = page.get_text("words")
    for w in words:
        if w[2] > r.width - MARGIN + 2 or w[0] < MARGIN - 2:
            problems.append(f"p{i}: text outside margins '{w[4]}'")
            break
    body_words = [w for w in words if 80 < w[1] < r.height - 80]
    if len(body_words) < 25 and not page.get_image_info():
        problems.append(f"p{i}: sparse page ({len(body_words)} words)")
    for marker in ("Error! Reference", "Update field", "Right-click", "{fig:", "{tab:", "{cite:", "**"):
        if marker in text:
            problems.append(f"p{i}: marker '{marker}'")
    page.get_pixmap(dpi=70).save(out / f"p{i:03d}.png")
print("pages", len(doc))
print("\n".join(problems) or "no problems flagged")
