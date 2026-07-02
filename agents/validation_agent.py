"""Validation Agent — dynamic checks that adapt to whatever fields were extracted."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from config import TOTAL_TOLERANCE
from models.schemas import ExtractionResult, FieldValidation, ValidationResult, ValidationStatus
from utils.vendor_matcher import VendorMatcher

_vendor_matcher = VendorMatcher()

# Failed checks that a VLM re-query can't fix — routing sends these straight
# to human review instead of wasting auto-correction attempts on them.
NON_CORRECTABLE_FIELDS = {"duplicate_check", "line_items"}


def run(extraction: ExtractionResult, document_id: Optional[str] = None) -> ValidationResult:
    data   = extraction.extracted_data
    checks: list[FieldValidation] = []

    checks.extend(_check_totals(data))
    checks.extend(_check_line_items(data))
    checks.extend(_check_dates(data))
    checks.extend(_check_iban(data))
    checks.extend(_check_vendor(data))
    checks.extend(_check_duplicate(data, document_id))

    failed     = [v.field for v in checks if v.status == ValidationStatus.FAILED]
    passed_cnt = sum(1 for v in checks if v.status == ValidationStatus.VALID)
    conf       = round(passed_cnt / max(len(checks), 1), 2)

    return ValidationResult(
        is_valid=len(failed) == 0,
        field_validations=checks,
        failed_fields=failed,
        overall_confidence=conf,
    )


# ── Checks ────────────────────────────────────────────────────────────────────

def _check_totals(data) -> list[FieldValidation]:
    """Verify subtotal + tax = total if all three are present."""
    total    = data.total_amount
    subtotal = data.subtotal
    tax      = data.tax_amount

    if None in (total, subtotal, tax):
        return []

    expected = round(subtotal + tax, 2)
    if abs(expected - total) > TOTAL_TOLERANCE:
        return [FieldValidation(
            field="total_amount",
            status=ValidationStatus.FAILED,
            message=f"Total {total} ≠ subtotal {subtotal} + tax {tax} = {expected}",
        )]
    return [FieldValidation(field="total_amount", status=ValidationStatus.VALID)]


def _check_dates(data) -> list[FieldValidation]:
    """Check any field whose name contains 'date' for ISO 8601 format."""
    results = []
    date_fields = {k: v for k, v in data.fields.items()
                   if "date" in k.lower() and v and isinstance(v, str)}
    for fname, value in date_fields.items():
        try:
            datetime.strptime(value, "%Y-%m-%d")
            results.append(FieldValidation(field=fname, status=ValidationStatus.VALID))
        except ValueError:
            results.append(FieldValidation(
                field=fname,
                status=ValidationStatus.FAILED,
                message=f"'{value}' is not YYYY-MM-DD format",
            ))
    return results


def _check_iban(data) -> list[FieldValidation]:
    """Validate IBAN format if present."""
    iban = data.iban
    if not iban:
        return []
    cleaned = iban.replace(" ", "").upper()
    if re.match(r"^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$", cleaned):
        return [FieldValidation(field="iban", status=ValidationStatus.VALID)]
    return [FieldValidation(
        field="iban",
        status=ValidationStatus.FAILED,
        message=f"Invalid IBAN format: {iban}",
    )]


def _check_vendor(data) -> list[FieldValidation]:
    """Fuzzy-match vendor name against known vendor registry."""
    vendor = data.vendor_name
    if not vendor:
        return []

    known, matched = _vendor_matcher.is_known_vendor(vendor)
    if known and matched and matched.lower() != vendor.lower():
        return [FieldValidation(
            field="vendor_name",
            status=ValidationStatus.VALID,
            message=f"Matched to known vendor: '{matched}'",
            corrected_value=matched,
        )]
    return [FieldValidation(field="vendor_name", status=ValidationStatus.VALID)]


def _check_line_items(data) -> list[FieldValidation]:
    """Verify extracted line items sum to the subtotal, when both are present."""
    items    = data.line_items
    subtotal = data.subtotal
    if not items or subtotal is None:
        return []

    running = 0.0
    counted = 0
    for item in items:
        raw = item.get("total") or item.get("amount") or item.get("line_total")
        if raw is None:
            qty   = item.get("quantity")
            price = item.get("unit_price") or item.get("price")
            if qty is not None and price is not None:
                try:
                    raw = float(qty) * float(price)
                except (TypeError, ValueError):
                    raw = None
        if raw is None:
            continue
        try:
            running += float(str(raw).replace(",", "").replace("$", "")
                              .replace("€", "").replace("£", "").replace("₹", ""))
            counted += 1
        except (TypeError, ValueError):
            continue

    if counted == 0 or counted < len(items):
        # Can't reliably reconcile if some line items have no derivable total
        return []

    running = round(running, 2)
    if abs(running - subtotal) > TOTAL_TOLERANCE:
        return [FieldValidation(
            field="line_items",
            status=ValidationStatus.FAILED,
            message=f"Line items sum to {running} but subtotal is {subtotal}",
        )]
    return [FieldValidation(field="line_items", status=ValidationStatus.VALID)]


def _check_duplicate(data, document_id: Optional[str]) -> list[FieldValidation]:
    """Flag likely duplicate submissions — same vendor + invoice number, or
    same vendor + amount + date. Prevents double-processing/double-payment."""
    from database.storage import find_duplicate

    dup = find_duplicate(
        vendor_name=data.vendor_name,
        invoice_number=data.document_number,
        total_amount=data.total_amount,
        invoice_date=data.document_date,
        exclude_document_id=document_id,
    )
    if dup:
        return [FieldValidation(
            field="duplicate_check",
            status=ValidationStatus.FAILED,
            message=f"⚠️ Possible duplicate of document {dup['document_id'][:8]} ({dup['reason']})",
        )]
    return [FieldValidation(field="duplicate_check", status=ValidationStatus.VALID)]
