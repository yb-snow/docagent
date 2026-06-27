"""Smart field grouping — categorises any extracted key by name pattern."""

from __future__ import annotations

_GROUPS = {
    "📄 Document Info":     ["number", "invoice", "receipt", "order", "reference", "po_",
                              "date", "period", "terms", "due", "expiry", "issue", "bill_no"],
    "🏢 Vendor / Seller":   ["vendor", "supplier", "merchant", "seller", "company",
                              "issued_by", "billed_by", "from_", "provider"],
    "👤 Customer / Bill To":["customer", "client", "buyer", "billed_to", "bill_to",
                              "ship_to", "sold_to", "recipient", "payee"],
    "📍 Contact & Address": ["address", "street", "city", "state", "zip", "postal",
                              "country", "phone", "mobile", "tel", "fax", "email", "website"],
    "💰 Financials":        ["total", "subtotal", "sub_total", "net", "gross", "amount",
                              "tax", "vat", "gst", "hst", "discount", "price", "cost",
                              "currency", "rate", "balance", "payment", "charge", "fee"],
    "🏦 Banking":           ["iban", "account", "bank", "swift", "bic", "routing",
                              "sort_code", "branch", "ifsc"],
    "📝 Notes & Other":     [],  # catch-all — always last
}


def group_fields(fields: dict) -> dict[str, dict]:
    """
    Returns an ordered dict of {group_label: {field_key: value}}.
    Empty groups are omitted.
    """
    result: dict[str, dict] = {g: {} for g in _GROUPS}

    for key, value in fields.items():
        if value is None or value == "":
            continue
        assigned = False
        key_lower = key.lower()
        for group, keywords in _GROUPS.items():
            if group == "📝 Notes & Other":
                continue
            if any(kw in key_lower for kw in keywords):
                result[group][key] = value
                assigned = True
                break
        if not assigned:
            result["📝 Notes & Other"][key] = value

    return {g: v for g, v in result.items() if v}


_CURRENCY_SYMBOLS: dict[str, str] = {
    "INR": "₹", "USD": "$",  "EUR": "€",  "GBP": "£",
    "JPY": "¥", "CNY": "¥",  "AUD": "A$", "CAD": "C$",
    "SGD": "S$","AED": "د.إ ","SAR": "﷼ ", "CHF": "CHF ",
    "HKD": "HK$","MYR": "RM ","THB": "฿", "IDR": "Rp ",
}

# Keys containing these substrings are NOT monetary even if they contain
# "total", "amount", etc. — e.g. total_quantity_items, amount_in_words
_NON_MONETARY_SUBSTRINGS = (
    "quantity", "qty", "count", "items", "units", "pcs", "pieces",
    "words", "batch", "sequence", "route", "serial", "number", "no_",
    "_no", "ref", "code", "id",
)

_MONETARY_KEYWORDS = (
    "amount", "total", "subtotal", "sub_total", "tax", "price", "cost",
    "balance", "discount", "fee", "charge", "net", "gross", "vat", "gst",
    "sgst", "cgst", "igst", "cess", "duty", "tariff", "rate",
)


def pretty_label(key: str) -> str:
    """Convert snake_case key to Title Case label."""
    return key.replace("_", " ").title()


def format_value(key: str, value, currency: str = "") -> str:
    """Format a value for display using the document's own currency symbol."""
    if value is None:
        return "—"
    key_lower = key.lower()

    # Skip monetary formatting for quantity / non-monetary fields
    is_non_monetary = any(s in key_lower for s in _NON_MONETARY_SUBSTRINGS)

    is_monetary = (not is_non_monetary) and any(
        k in key_lower for k in _MONETARY_KEYWORDS
    )

    if is_monetary:
        try:
            symbol = _CURRENCY_SYMBOLS.get((currency or "").upper().strip(), "")
            # Fall back to the raw currency string if symbol not mapped
            if not symbol and currency:
                symbol = currency.strip() + " "
            return f"{symbol}{float(value):,.2f}"
        except (ValueError, TypeError):
            pass

    return str(value)
