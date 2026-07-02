"""Tesseract OCR fallback — text extraction, bounding boxes, and VLM merge."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Optional

from PIL import Image

from models.schemas import DocumentData

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


def crop_region(image: Image.Image, keyword: str, padding: int = 20) -> Optional[Image.Image]:
    """Crop toward the region where `keyword` was found by OCR.

    Finds the first OCR'd word/phrase containing `keyword`, then crops a band
    starting at that word and extending to the right edge of the image
    (values are usually beside their label) with vertical padding above and
    below. Returns None if the keyword wasn't found — callers should fall
    back to the full image in that case.
    """
    if not _TESSERACT_AVAILABLE:
        return None
    try:
        data = ocr_extract_with_boxes(image)
    except Exception:
        return None

    texts = data.get("text") or []
    if not texts:
        return None

    keyword_lower = keyword.lower().strip()
    if not keyword_lower:
        return None

    match_idx = next(
        (i for i, word in enumerate(texts) if word and keyword_lower in word.lower()),
        None,
    )
    if match_idx is None:
        return None

    left   = data["left"][match_idx]
    top    = data["top"][match_idx]
    height = data["height"][match_idx]

    img_w, img_h = image.size
    x0 = max(0, left - padding)
    y0 = max(0, top - padding)
    x1 = img_w                                    # extend right — value usually follows the label
    y1 = min(img_h, top + height + padding * 4)    # generous band below the label

    if x1 <= x0 or y1 <= y0:
        return None
    return image.crop((x0, y0, x1, y1))


# Regex fallback patterns for common fields — only used to fill gaps the VLM
# left null, never to override a value the VLM already found (the VLM read
# is generally more reliable than blind regex matching on noisy OCR text).
_FIELD_OCR_PATTERNS: dict[str, list[str]] = {
    # \b before "total" matters: without it, "total" also matches the
    # substring inside "Subtotal", stealing the subtotal value.
    "total_amount":    [r"\b(?:grand\s*)?total\b[:\s]*[₹$€£]?\s*([\d,]+\.\d{2})",
                        r"\bamount\s*due\b[:\s]*[₹$€£]?\s*([\d,]+\.\d{2})"],
    "subtotal":        [r"\bsub[\s-]*total\b[:\s]*[₹$€£]?\s*([\d,]+\.\d{2})"],
    "tax_amount":      [r"\b(?:tax|vat|gst)\b[:\s]*[₹$€£]?\s*([\d,]+\.\d{2})"],
    "invoice_number":  [r"\binvoice\s*(?:no\.?|number|#)[:\s]*([A-Za-z0-9\-\/\.]+)"],
    "invoice_date":    [r"\b(?:invoice\s*)?date\b[:\s]*(\d{4}-\d{2}-\d{2})"],
}


def merge_ocr_with_extraction(ocr_text: str, extracted: DocumentData) -> DocumentData:
    """Fill fields the VLM left null/missing using regex recovery from raw OCR text.

    Only called when extraction confidence was low enough to trigger the OCR
    fallback in the first place. Never overwrites a value the VLM already
    supplied.
    """
    if not ocr_text or not ocr_text.strip():
        return extracted

    updated = extracted.model_copy(deep=True)

    for field, patterns in _FIELD_OCR_PATTERNS.items():
        if updated.fields.get(field):
            continue
        for pattern in patterns:
            m = re.search(pattern, ocr_text, re.IGNORECASE)
            if m:
                updated.fields[field] = m.group(1).strip()
                break

    return updated