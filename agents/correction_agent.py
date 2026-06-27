"""Auto-Correction Agent — re-queries VLM with a focused crop to fix failed fields."""

from __future__ import annotations

import json
import re
from typing import Optional, List

from PIL import Image

import config
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, GEMINI_API_KEY, GEMINI_MODEL
from models.schemas import ExtractionResult, ValidationResult, ValidationStatus
from pipeline.ocr import crop_region
from utils.image_processing import image_to_base64

_PROMPT = """A field extracted from this document failed validation.

Field: {field}
Current value: {current_value}
Validation error: {error_message}

Look carefully at the image crop and extract ONLY the correct value for "{field}".
Return ONLY this JSON (no markdown, no explanation):
{{"field": "{field}", "value": <corrected value or null>}}

Rules: dates = YYYY-MM-DD, amounts = plain numbers, return ONLY JSON."""

# Keywords to find the right image region per field name
_REGION_KEYWORDS = {
    "total_amount": "total",  "subtotal": "subtotal",  "tax_amount": "tax",
    "invoice_date": "date",   "due_date": "due",        "invoice_number": "invoice",
    "vendor_name":  "vendor", "iban":     "iban",        "account_number": "account",
}


def run(
    images: List[Image.Image],
    extraction: ExtractionResult,
    validation: ValidationResult,
) -> ExtractionResult:
    updated = extraction.extracted_data.model_copy(deep=True)

    for field in validation.failed_fields:
        fv      = next((v for v in validation.field_validations if v.field == field), None)
        current = str(updated.fields.get(field, ""))
        error   = fv.message if fv else ""
        keyword = _REGION_KEYWORDS.get(field, field.replace("_", " "))

        corrected = None
        
        for image in images:
            corrected = _correct_field(image, field, current, error, keyword)
            if corrected is not None:
                break
        
        if corrected is not None:
            updated.fields[field] = corrected

    return ExtractionResult(
        raw_ocr_text=extraction.raw_ocr_text,
        extracted_data=updated,
        confidence=extraction.confidence,
        vlm_response=extraction.vlm_response,
        ocr_used=extraction.ocr_used,
    )


def _correct_field(image: Image.Image, field: str, current: str,
                   error: str, keyword: str) -> Optional[str]:
    crop   = crop_region(image, keyword) or image
    prompt = _PROMPT.format(field=field, current_value=current, error_message=error)

    if config.VLM_BACKEND == "gemini":
        return _correct_gemini(crop, prompt)
    elif config.VLM_BACKEND == "claude":
        return _correct_claude(crop, prompt)
    return None


def _correct_gemini(crop: Image.Image, prompt: str) -> Optional[str]:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=GEMINI_API_KEY)
    r = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[crop, prompt],
        config=types.GenerateContentConfig(max_output_tokens=256, temperature=0.1),
    )
    return _parse(r.text)


def _correct_claude(crop: Image.Image, prompt: str) -> Optional[str]:
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    b64    = image_to_base64(crop, fmt="PNG")
    msg    = client.messages.create(
        model=CLAUDE_MODEL, max_tokens=256,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
            {"type": "text",  "text": prompt},
        ]}],
    )
    return _parse(msg.content[0].text)


def _parse(text: str) -> Optional[str]:
    text = re.sub(r"```(?:json)?", "", text).strip()
    m    = re.search(r"\{[\s\S]*?\}", text)
    if not m:
        return None
    try:
        return json.loads(m.group()).get("value")
    except Exception:
        return None
