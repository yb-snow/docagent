"""Classification Agent — identifies document type before extraction."""

from __future__ import annotations

import json
import re

from PIL import Image

import config
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, GEMINI_API_KEY, GEMINI_MODEL
from utils.image_processing import image_to_base64

_SCHEMA_MAP = {
    "invoice": "InvoiceData",
    "receipt": "ReceiptData",
    "form":    "FormData",
}

_CLASSIFICATION_PROMPT = """Look at this document image and classify it into exactly one type.

Return ONLY this JSON object, nothing else:
{"doc_type": "invoice", "confidence": 0.95, "reasoning": "one sentence"}

Valid doc_type values:
- "invoice"  : formal vendor invoice such as an Amazon India invoice, B2B Invoice, with invoice number, bill-to name, line items, Date, Price
- "receipt"  : point-of-sale or purchase receipt (simpler, often from retail)
- "form"     : structured form such as W-9, expense report, or intake form

Rules:
- Return ONLY the JSON, no explanation or markdown fences.
- confidence must be a float between 0.0 and 1.0.
- for unclear images, treat document type = invoice, confidence = 0.5 reasoning = "Default"

"""

class ClassificationResult:
    def __init__(self, doc_type: str, confidence: float, schema_name: str, reasoning: str = ""):
        self.doc_type    = doc_type
        self.confidence  = confidence
        self.schema_name = schema_name
        self.reasoning   = reasoning

    def __repr__(self) -> str:
        return f"ClassificationResult(doc_type={self.doc_type!r}, confidence={self.confidence:.2f})"


def run(image: Image.Image) -> ClassificationResult:
    if config.VLM_BACKEND == "gemini":
        return _classify_with_gemini(image)
    elif config.VLM_BACKEND == "claude":
        return _classify_with_claude(image)
    return _fallback_classify()


# ── Gemini (free, recommended) ────────────────────────────────────────────────

def _classify_with_gemini(image: Image.Image) -> ClassificationResult:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[image, _CLASSIFICATION_PROMPT],
        config=types.GenerateContentConfig(
            max_output_tokens=500,
            temperature=0.1,
        ),
    )
    return _parse_response(response.text)


# ── Claude (optional, paid) ───────────────────────────────────────────────────

def _classify_with_claude(image: Image.Image) -> ClassificationResult:
    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    b64 = image_to_base64(image, fmt="PNG")

    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
                {"type": "text", "text": _CLASSIFICATION_PROMPT},
            ],
        }],
    )
    return _parse_response(message.content[0].text)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_response(text: str) -> ClassificationResult:
    text = re.sub(r"```(?:json)?", "", text).strip()
    match = re.search(r"\{[\s\S]*?\}", text)
    if match:
        try:
            obj = json.loads(match.group())
            doc_type   = obj.get("doc_type", "invoice").lower()
            confidence = float(obj.get("confidence", 0.7))
            reasoning  = obj.get("reasoning", "")
            schema     = _SCHEMA_MAP.get(doc_type, "InvoiceData")
            return ClassificationResult(doc_type, confidence, schema, reasoning)
        except Exception:
            pass
    return _fallback_classify()


def _fallback_classify() -> ClassificationResult:
    return ClassificationResult("invoice", 0.5, "InvoiceData", "Fallback — defaulting to invoice")
