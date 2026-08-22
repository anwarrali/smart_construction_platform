"""Build a small, valid, multi-page PDF with known text on each page.

Written by hand rather than with reportlab so the test suite gains no new
dependency for the sake of a fixture. The output is a genuine PDF — pypdf
parses it and extracts the text — which matters, because a test that fed the
extractor a mock would prove nothing about whether extraction works.

Each page carries exactly the string it was given, so a test can assert that
page 2's text came from page 2.
"""

from __future__ import annotations

from pathlib import Path


def _escape(text: str) -> str:
    """Escape the three characters that are special inside a PDF string."""
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def build_pdf(path: Path, pages: list[str]) -> Path:
    """Write a PDF to `path` with one page per entry in `pages`."""
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)  # object numbers are 1-based

    # Reserve 1 for the catalogue and 2 for the page tree, so page objects can
    # reference the tree before it is written.
    objects.append(b"")  # 1: catalogue, filled in below
    objects.append(b"")  # 2: page tree, filled in below
    font_number = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    page_numbers: list[int] = []
    for text in pages:
        if text:
            stream = (
                f"BT /F1 12 Tf 72 720 Td ({_escape(text)}) Tj ET".encode("latin-1", "replace")
            )
        else:
            # A page with no text at all — how a scanned page looks to pypdf.
            stream = b""
        content_number = add(
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
        )
        page_number = add(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 " + str(font_number).encode() + b" 0 R >> >> "
            b"/Contents " + str(content_number).encode() + b" 0 R >>"
        )
        page_numbers.append(page_number)

    kids = b" ".join(f"{number} 0 R".encode() for number in page_numbers)
    objects[1] = (
        b"<< /Type /Pages /Kids [" + kids + b"] /Count "
        + str(len(page_numbers)).encode() + b" >>"
    )
    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += str(number).encode() + b" 0 obj\n" + body + b"\nendobj\n"

    xref_offset = len(out)
    out += b"xref\n0 " + str(len(objects) + 1).encode() + b"\n"
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        b"trailer\n<< /Size " + str(len(objects) + 1).encode()
        + b" /Root 1 0 R >>\nstartxref\n" + str(xref_offset).encode() + b"\n%%EOF\n"
    )

    path.write_bytes(bytes(out))
    return path
