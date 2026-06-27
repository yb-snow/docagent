"""Tesseract OCR fallback — text extraction, bounding boxes, and VLM merge."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from PIL import Image

def _find_tesseract() -> Optional[str]:
    for candidate in (
        "/opt/homebrew/bin/tesseract",
        "/usr/local/bin/tesseract",
        "/usr/bin/tesseract",
        "/opt/local/bin/tesseract",
    ):
        if Path(candidate).exists():
            return candidate
    return shutil.which("tesseract")

try:
    import pytesseract
    from pytesseract import Output as _Output

    _tess_path = _find_tesseract()
    if _tess_path:
        pytesseract.pytesseract.tesseract_cmd = _tess_path

    pytesseract.get_tesseract_version()
    _TESSERACT_AVAILABLE = True

except Exception:
    _TESSERACT_AVAILABLE = False


def ocr_extract_text(image: Image.Image) -> str:
    if not _TESSERACT_AVAILABLE:
        return ""
    try:
        return pytesseract.image_to_string(image, config="--psm 6")
    except Exception:
        return ""


def ocr_extract_with_boxes(image: Image.Image) -> dict:
    if not _TESSERACT_AVAILABLE:
        return {"text": [], "conf": [], "left": [], "top": [], "width": [], "height": []}
    try:
        return pytesseract.image_to_data(image, output_type=_Output.DICT, config="--psm 6")
    except Exception:
        return {"text": [], "conf": [], "left": [], "top": [], "width": [], "height": []}


def crop_region(image: Image.Image, keyword: str, padding: int = 20) -> Image.Image:
    return image


def merge_ocr_with_extraction(ocr_text, extracted):
    return extracted