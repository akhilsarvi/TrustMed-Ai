from __future__ import annotations

from pathlib import Path

try:
    from docx import Document
except ImportError:  # pragma: no cover
    Document = None


def extract_docx_text(file_path: str | Path) -> str:
    if Document is None:
        return "DOCX extraction is unavailable because python-docx is not installed."

    doc = Document(str(file_path))
    paragraphs = []
    for para in doc.paragraphs:
        if para.text.strip():
            paragraphs.append(para.text.strip())
    return "\n".join(paragraphs)
