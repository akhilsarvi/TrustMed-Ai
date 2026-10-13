from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

from .docx_extractor import extract_docx_text
from .image_extractor import extract_image_text
from .pdf_extractor import extract_pdf_text
from .text_cleaner import clean_text

ALLOWED_TYPES = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".txt": "txt",
    ".csv": "csv",
    ".jpg": "image",
    ".jpeg": "image",
    ".png": "image",
}


def sanitize_filename(filename: str) -> str:
    if not filename:
        return "uploaded_file"
    return Path(filename).name.replace("..", "_")


def extract_document_text(file_path: str | Path) -> dict:
    path = Path(file_path)
    suffix = path.suffix.lower()
    file_type = ALLOWED_TYPES.get(suffix, "unknown")

    text = ""

    if suffix == ".pdf":
        text = extract_pdf_text(path)
    elif suffix == ".docx":
        text = extract_docx_text(path)
    elif suffix == ".txt":
        text = path.read_text(encoding="utf-8", errors="ignore")
    elif suffix == ".csv":
        df = pd.read_csv(path)
        text = df.to_string(index=False)
    elif suffix in {".jpg", ".jpeg", ".png"}:
        text = extract_image_text(path)
    else:
        text = "Unsupported document type or unreadable file."

    cleaned = clean_text(text)
    chunks = chunk_text(cleaned)

    return {
        "filename": sanitize_filename(path.name),
        "file_type": file_type,
        "text": cleaned,
        "document_chunks": chunks,
        "metadata": {
            "extension": suffix,
            "size_bytes": path.stat().st_size if path.exists() else 0,
            "pages": estimate_pages(cleaned),
        },
    }


def chunk_text(text: str, chunk_size: int = 700, overlap: int = 120) -> list[dict]:
    if not text:
        return []

    chunks = []
    start = 0
    idx = 1
    while start < len(text):
        end = min(start + chunk_size, len(text))
        part = text[start:end]
        if len(part.strip()) == 0:
            break
        chunks.append({
            "chunk_number": idx,
            "page_number": None,
            "text": part.strip(),
        })
        idx += 1
        if end == len(text):
            break
        start = max(0, end - overlap)
    return chunks


def estimate_pages(text: str) -> int:
    if not text:
        return 0
    lines = text.splitlines()
    return max(1, len(lines) // 35 + 1)
