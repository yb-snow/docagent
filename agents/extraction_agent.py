"""Extraction Agent — classifies document type AND extracts all fields in one VLM call."""

from __future__ import annotations

import json
import re
from typing import Tuple, List

from PIL import Image

import config
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, GEMINI_API_KEY, GEMINI_MODEL
from models.schemas import DocumentData, ExtractionResult

# One prompt does BOTH classification and full extraction — saves an API call
_PROMPT = """You are an expert document analyst. Examine this document image carefully.

Your task:
1. Identify the document type
2. Extract EVERY piece of information visible in the document — be exhaustive

Return ONLY a valid JSON object (no markdown fences, no explanation, no comments).
Use this exact structure:

{{
  "doc_type": "invoice",
  "doc_subtype": "tax_invoice",
  "confidence": 0.95,
  "fields": {{
    "vendor_name": "Acme Corp",
    "invoice_number": "INV-001",
    "invoice_date": "2024-01-15",
    "due_date": "2024-02-15",
    "customer_name": "John Doe",
    "billing_address": "123 Main St",
    "subtotal": 1000.00,
    "tax_rate": 18,
    "tax_amount": 180.00,
    "total_amount": 1180.00,
    "currency": "INR",
    "payment_terms": "Net 30",
    "gstin": "27AABCU9603R1ZX"
  }},
  "line_items": [
    {{"description": "Product A", "quantity": 2, "unit_price": 500.00, "total": 1000.00}}
  ],
  "extraction_notes": "Tax invoice from Acme Corp for Product A"
}}

Rules:
- doc_type must be one of: invoice, receipt, purchase_order, bank_statement, expense_report, quote, delivery_note, contract, form, other
- Include EVERY field visible in the document using snake_case keys
- Dates must be in YYYY-MM-DD format
- Amounts must be plain numbers without currency symbols
- Use null only for fields present but unreadable
- Do NOT include fields that do not exist in this document
- line_items must include every row from every table in the document

OCR TEXT (use as reference if image is unclear):
{ocr_text}"""


def run(images: List[Image.Image], ocr_text: str) -> ExtractionResult:
    backend = config.VLM_BACKEND          # read at call-time so Settings changes take effect
    if backend == "gemini":
        return _extract_with_gemini(images, ocr_text)
    elif backend == "claude":
        return _extract_with_claude(images, ocr_text)
    elif backend == "mlx":
        return _extract_with_mlx(images, ocr_text)
    elif backend == "moondream":
        return _extract_with_moondream(images, ocr_text)
    elif backend in ("internvl", "llava"):
        return _extract_with_local_vlm(images, ocr_text)
    raise ValueError(f"Unknown VLM_BACKEND: '{backend}'. Valid: gemini, claude, mlx, moondream")


# ── Gemini ────────────────────────────────────────────────────────────────────

def _extract_with_gemini(images: List[Image.Image], ocr_text: str) -> ExtractionResult:
    from google import genai
    from google.genai import types
    import time

    client   = genai.Client(api_key=GEMINI_API_KEY)
    prompt   = _PROMPT.format(ocr_text=ocr_text[:4000])

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[*images, prompt],
                config=types.GenerateContentConfig(
                    max_output_tokens=16384,
                    temperature=0.1,
                ),
            )
            break

        except Exception as e:
            print(f"Retry {attempt+1}/3:", e)

            if attempt == 2:
                raise e

            time.sleep(20)

    # Safely extract text — response.text raises ValueError when content is blocked
    try:
        raw_text = response.text or ""
    except Exception as e:
        print(f"[extraction_agent] response.text inaccessible: {e}")
        print(f"[extraction_agent] Full response object: {response}")
        raw_text = ""

    print(f"[extraction_agent] Gemini raw response ({len(raw_text)} chars):\n{raw_text[:2000]}")
    return _build_result(ocr_text, raw_text)


# ── Claude ────────────────────────────────────────────────────────────────────

def _extract_with_claude(images: List[Image.Image], ocr_text: str) -> ExtractionResult:
    import anthropic
    from utils.image_processing import image_to_base64

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = _PROMPT.format(ocr_text=ocr_text[:4000])
    encoded_images = [
        image_to_base64(img, fmt="PNG")
        for img in images
    ]

    content = []
    for b64 in encoded_images:
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": b64,
                },
            }
        )
    content.append({"type": "text", "text": prompt})

    msg = client.messages.create(
        model = CLAUDE_MODEL,
        max_tokens = 4096,
        messages = [
            {
                "role": "user",
                "content": content,
            }
        ],
    )
    
    return _build_result(ocr_text, msg.content[0].text)


# ── Apple MLX (M-chip, no API key) ───────────────────────────────────────────

def _extract_with_mlx(images: List[Image.Image], ocr_text: str) -> ExtractionResult:
    """Run a 4-bit quantised vision model via Apple MLX — fast on M1/M2/M3/M4."""
    try:
        import mlx_vlm
        from mlx_vlm import load, generate
        from mlx_vlm.prompt_utils import apply_chat_template
        from mlx_vlm.utils import load_config as mlx_load_config
    except ImportError as e:
        raise ImportError("Install mlx-vlm: pip install mlx-vlm") from e

    model_path = config.LOCAL_VLM_MODEL   # e.g. "mlx-community/llava-1.5-7b-4bit"
    print(f"[MLX] Loading {model_path} (downloads on first use)…")

    model, processor = load(model_path)
    mlx_cfg          = mlx_load_config(model_path)
    prompt           = _PROMPT.format(ocr_text=ocr_text[:3000])
    chat_prompt      = apply_chat_template(processor, mlx_cfg, prompt, num_images=len(images))

    # Save images to temporary files (mlx_vlm expects file paths)
    import tempfile
    import os

    tmp_paths = []

    try:
        for img in images:
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            img.save(tmp.name)
            tmp_paths.append(tmp.name)
            tmp.close()

            raw = generate(
                model,
                processor,
                tmp_paths,
                chat_prompt,
                verbose=False,
                max_tokens=2048,
            )

    finally:
        for p in tmp_paths:
            if os.path.exists(p):
                os.unlink(p)

    return _build_result(ocr_text, raw)


# ── moondream2 (tiny, CPU/MPS, no API key) ────────────────────────────────────

def _extract_with_moondream(images: List[Image.Image], ocr_text: str) -> ExtractionResult:
    """Run moondream2 (~2 GB) locally — works on CPU or Apple MPS."""
    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as e:
        raise ImportError("Install transformers: pip install transformers einops") from e

    import torch

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model_id = "vikhyatk/moondream2"
    print(f"[moondream2] Loading on {device.upper()} (downloads on first use ~2 GB)…")

    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        model_id, trust_remote_code=True,
        torch_dtype=torch.float16 if device == "mps" else torch.float32,
    ).to(device).eval()

    prompt = _PROMPT.format(ocr_text=ocr_text[:3000])
    encoded = [model.encode_image(img) for img in images]

    with torch.no_grad():
        answers = [
            model.answer_question(enc_img, prompt, tokenizer)
            for enc_img in enc_images
        ]
        raw = "\n\n".join(answers)

    return _build_result(ocr_text, raw)


# ── Local VLM (HuggingFace InternVL2 / LLaVA) ────────────────────────────────

def _extract_with_local_vlm(images: List[Image.Image], ocr_text: str) -> ExtractionResult:
    from config import LOCAL_VLM_DEVICE, LOCAL_VLM_MODEL
    try:
        import torch
        from transformers import AutoModel, AutoTokenizer
    except ImportError as e:
        raise ImportError("Install transformers and torch for local VLM support.") from e

    tokenizer = AutoTokenizer.from_pretrained(LOCAL_VLM_MODEL, trust_remote_code=True)
    model = AutoModel.from_pretrained(
        LOCAL_VLM_MODEL, torch_dtype=torch.float16,
        device_map=LOCAL_VLM_DEVICE, trust_remote_code=True,
    ).eval()
    
    prompt = _PROMPT.format(ocr_text=ocr_text[:4000])
    responses = []
    for image in images:
        inputs = tokenizer(prompt, return_tensors="pt").to(LOCAL_VLM_DEVICE)
        
        with torch.no_grad():
            out = model.generate(**inputs, max_new_tokens=2048)
            
        responses.append(
            tokenizer.decode(out[0], skip_special_tokens=True)
        )
    
    return _build_result(ocr_text, "\n\n".join(responses))


# ── Parse helpers ─────────────────────────────────────────────────────────────

def _build_result(ocr_text: str, raw: str) -> ExtractionResult:
    doc_data, confidence = _parse_response(raw)
    return ExtractionResult(
        raw_ocr_text=ocr_text,
        extracted_data=doc_data,
        confidence=confidence,
        vlm_response=raw,
    )


def _close_truncated_json(partial: str) -> str:
    """Close a truncated JSON string that starts with '{' but has no closing braces.

    Uses character-level parsing to correctly track string context (so braces
    inside string values are not miscounted), then appends the missing closing
    brackets/braces to produce valid JSON.
    """
    result      = []
    in_string   = False
    escape_next = False
    depth_stack = []   # stack of expected closing chars: '}' or ']'

    for ch in partial:
        result.append(ch)
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth_stack.append("}")
        elif ch == "[":
            depth_stack.append("]")
        elif ch in "}]":
            if depth_stack and depth_stack[-1] == ch:
                depth_stack.pop()

    # Close any open string value
    if in_string:
        result.append('"')

    # Strip trailing comma before we close (invalid JSON at end of object/array)
    text = "".join(result).rstrip()
    if text and text[-1] == ",":
        text = text[:-1]

    # Close remaining open structures in reverse order
    text += "".join(reversed(depth_stack))
    return text


def _sanitise_json_strings(text: str) -> str:
    """Escape raw newlines and tabs inside JSON string values.

    Gemini sometimes embeds literal newlines inside strings (e.g. multi-line
    addresses) which are invalid JSON.  This walks the character stream and
    replaces bare \\n/\\t/\\r inside quoted strings with their escape sequences.
    """
    result = []
    in_string = False
    escape_next = False
    for ch in text:
        if escape_next:
            result.append(ch)
            escape_next = False
        elif ch == "\\":
            result.append(ch)
            escape_next = True
        elif ch == '"':
            result.append(ch)
            in_string = not in_string
        elif in_string and ch == "\n":
            result.append("\\n")
        elif in_string and ch == "\r":
            result.append("\\r")
        elif in_string and ch == "\t":
            result.append("\\t")
        else:
            result.append(ch)
    return "".join(result)


def _parse_response(text: str) -> Tuple[DocumentData, float]:
    if not text or not text.strip():
        print("[extraction_agent] VLM returned empty response")
        return DocumentData(), 0.0

    # Strip markdown code fences (opening and closing)
    text = re.sub(r"```(?:json)?", "", text).strip()
    text = re.sub(r"```", "", text).strip()

    # ── Step 1: locate the JSON object ───────────────────────────────────────
    match    = re.search(r"\{[\s\S]*\}", text)
    open_pos = text.find("{")

    if match:
        raw_json = match.group()
    elif open_pos != -1:
        # Truncated response — try to close the partial JSON
        print("[extraction_agent] Truncated JSON detected — attempting recovery.")
        raw_json = _close_truncated_json(text[open_pos:])
    else:
        print(f"[extraction_agent] No JSON found in VLM response.\nResponse: {text[:800]}")
        return DocumentData(), 0.0

    # ── Step 2: sanitise + parse ──────────────────────────────────────────────
    try:
        json_str = _sanitise_json_strings(raw_json)
        obj      = json.loads(json_str)
        if match is None:
            print("[extraction_agent] Truncated JSON recovered successfully.")
    except Exception as e:
        print(f"[extraction_agent] JSON parse error: {e}")
        print(f"[extraction_agent] Attempted to parse: {raw_json[:500]}")
        return DocumentData(), 0.0

    # ── Step 3: build DocumentData ────────────────────────────────────────────
    try:
        doc_type = str(obj.get("doc_type", "unknown")).lower().replace(" ", "_")
        subtype  = obj.get("doc_subtype")
        raw_conf = float(obj.get("confidence", 0.5))
        fields   = obj.get("fields") or {}
        items    = obj.get("line_items") or []
        notes    = obj.get("extraction_notes", "")

        # Normalise field values — strip surrounding whitespace, drop empty strings
        clean_fields: dict = {}
        for k, v in fields.items():
            if isinstance(v, str):
                cleaned = v.strip()
                clean_fields[k] = cleaned if cleaned else None
            else:
                clean_fields[k] = v

        # Confidence = VLM-reported confidence weighted by field coverage
        field_score = min(len([v for v in clean_fields.values() if v is not None]) / 8, 1.0)
        confidence  = round((raw_conf * 0.7) + (field_score * 0.3), 2)

        return DocumentData(
            doc_type=doc_type,
            doc_subtype=subtype,
            fields=clean_fields,
            line_items=items if isinstance(items, list) else [],
            extraction_notes=notes,
        ), confidence

    except Exception as e:
        print(f"[extraction_agent] Field extraction error: {e}")
        return DocumentData(), 0.0
