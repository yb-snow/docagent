"""FX Agent — detect non-INR currency, fetch live rate, convert monetary fields to INR."""

from __future__ import annotations

import re
import urllib.request
import json
from typing import Optional

from models.schemas import ExtractionResult

# Canonical currency codes that are already INR
_INR_CODES = {"INR", "RS", "RS.", "₹", "RUPEE", "RUPEES", "IND"}

# Monetary field name patterns
_MONEY_PATTERN = re.compile(
    r"(total|amount|subtotal|tax|vat|gst|igst|sgst|cgst|price|cost|fee|charge|discount|balance|due|payable|net)",
    re.I,
)


def _detect_currency(fields: dict) -> Optional[str]:
    """Return a normalised currency code from extracted fields, or None if unknown."""
    raw = (
        fields.get("currency")
        or fields.get("currency_code")
        or fields.get("currency_symbol")
        or ""
    )
    norm = str(raw).strip().upper().replace(".", "").replace(" ", "")
    if not norm:
        # Try to infer from monetary values containing a symbol
        for v in fields.values():
            sv = str(v or "")
            if "$" in sv:
                return "USD"
            if "€" in sv:
                return "EUR"
            if "£" in sv:
                return "GBP"
        return None
    # Map common symbols → ISO codes
    symbol_map = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY", "₹": "INR",
                  "RS": "INR", "INR": "INR", "USD": "USD", "EUR": "EUR",
                  "GBP": "GBP", "SGD": "SGD", "AED": "AED", "JPY": "JPY"}
    return symbol_map.get(norm, norm if len(norm) == 3 else None)


def _is_inr(currency: Optional[str]) -> bool:
    if currency is None:
        return True   # assume INR if unknown
    return currency.upper().strip() in _INR_CODES


def _fetch_rate(from_currency: str, to_currency: str = "INR") -> Optional[float]:
    """Fetch live FX rate via Frankfurter API (no key required)."""
    try:
        url = f"https://api.frankfurter.app/latest?from={from_currency}&to={to_currency}"
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read())
        return float(data["rates"][to_currency])
    except Exception:
        return None


def _clean_amount(value) -> Optional[float]:
    """Strip currency symbols and parse to float."""
    try:
        cleaned = re.sub(r"[₹$€£¥,\s]", "", str(value))
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _convert_fields(fields: dict, rate: float, from_currency: str) -> dict:
    """Return a new fields dict with all monetary values converted to INR."""
    converted = {}
    for key, val in fields.items():
        if _MONEY_PATTERN.search(key):
            amt = _clean_amount(val)
            if amt is not None:
                converted[key] = round(amt * rate, 2)
            else:
                converted[key] = val
        else:
            converted[key] = val
    # Update currency markers
    converted["currency"]        = "INR"
    converted["currency_symbol"] = "₹"
    converted["fx_rate_applied"] = f"1 {from_currency} = {rate} INR"
    return converted


def _convert_line_items(items: list, rate: float) -> list:
    """Convert monetary values inside each line-item dict."""
    result = []
    for item in items:
        new_item = {}
        for k, v in item.items():
            if _MONEY_PATTERN.search(k):
                amt = _clean_amount(v)
                new_item[k] = round(amt * rate, 2) if amt is not None else v
            else:
                new_item[k] = v
        result.append(new_item)
    return result


def run(extraction: ExtractionResult) -> tuple[ExtractionResult, bool, Optional[float], str]:
    """
    Inspect the extraction for currency; convert to INR if needed.

    Returns:
        (updated_extraction, was_converted, rate_used, human_readable_note)
    """
    fields   = extraction.extracted_data.fields
    currency = _detect_currency(fields)

    if _is_inr(currency):
        # Already INR — normalise symbol and return unchanged
        if currency is not None:
            fields = dict(fields)
            fields["currency"] = "INR"
            fields["currency_symbol"] = "₹"
            updated_data = extraction.extracted_data.model_copy(update={"fields": fields})
            updated_ext  = extraction.model_copy(update={"extracted_data": updated_data})
            return updated_ext, False, None, "Currency is INR — no conversion needed"
        return extraction, False, None, "Currency unknown — assumed INR"

    # Non-INR: fetch live rate
    rate = _fetch_rate(currency)
    if rate is None:
        # FX fetch failed — flag for human review but don't convert
        note = (f"⚠️ Non-INR currency detected ({currency}) but FX rate fetch failed. "
                f"Flagged for human review.")
        return extraction, False, None, note

    # Convert
    new_fields = _convert_fields(fields, rate, currency)
    new_items  = _convert_line_items(extraction.extracted_data.line_items or [], rate)

    updated_data = extraction.extracted_data.model_copy(
        update={"fields": new_fields, "line_items": new_items}
    )
    updated_ext = extraction.model_copy(update={"extracted_data": updated_data})

    note = (f"💱 Converted from {currency} to INR at rate {rate:.4f}. "
            f"All monetary fields updated.")
    return updated_ext, True, rate, note
