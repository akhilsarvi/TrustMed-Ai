from __future__ import annotations

from pathlib import Path

try:
    from PyPDF2 import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None


def extract_pdf_text(file_path: str | Path) -> str:
    if PdfReader is None:
        return "PDF extraction is unavailable because PyPDF2 is not installed."

    reader = PdfReader(str(file_path))
    pages = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            pages.append(f"[Page {page_number}]\n{text.strip()}")
    return "\n\n".join(pages)
