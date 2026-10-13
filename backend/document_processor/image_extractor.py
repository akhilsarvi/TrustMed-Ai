from __future__ import annotations

from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None

try:
    import pytesseract
except ImportError:  # pragma: no cover
    pytesseract = None


def extract_image_text(file_path: str | Path) -> str:
    if Image is None:
        return "Image OCR is unavailable because Pillow is not installed."
    if pytesseract is None:
        return "Image OCR is unavailable because pytesseract is not installed."

    try:
        img = Image.open(str(file_path))
        text = pytesseract.image_to_string(img)
        return text.strip()
    except Exception:
        return "Image was uploaded but OCR could not extract readable text."
