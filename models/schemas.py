"""Pydantic models for Doc Agent — flexible document-type-agnostic extraction."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Document types ────────────────────────────────────────────────────────────

class DocType(str, Enum):
    INVOICE         = "invoice"
    RECEIPT         = "receipt"
    PURCHASE_ORDER  = "purchase_order"
    BANK_STATEMENT  = "bank_statement"
    EXPENSE_REPORT  = "expense_report"
    QUOTE           = "quote"
    DELIVERY_NOTE   = "delivery_note"
    CONTRACT        = "contract"
    FORM            = "form"
    OTHER           = "other"
    UNKNOWN         = "unknown"


class ValidationStatus(str, Enum):
    VALID    = "valid"
    FAILED   = "failed"
    CORRECTED= "corrected"
    PENDING  = "pending_review"
    REJECTED = "rejected"


# ── Core flexible data model ──────────────────────────────────────────────────

class DocumentData(BaseModel):
    """Flexible, schema-free container for any document type.

    Rather than hardcoding field names, the VLM extracts everything it finds
    into `fields` as a plain dict.  Helper properties provide convenient access
    to the most common financial / identification fields regardless of what
    exact key the model used.
    """

    doc_type:         str            = "unknown"
    doc_subtype:      Optional[str]  = None          # e.g. "tax_invoice", "pro_forma"
    fields:           dict           = Field(default_factory=dict)
    line_items:       list[dict]     = Field(default_factory=list)
    extraction_notes: Optional[str]  = None

    # ── Convenience accessors ─────────────────────────────────────────────────

    def get(self, *names: str, default: Any = None) -> Any:
        """Return first non-None value matching any of the given field names."""
        for name in names:
            v = self.fields.get(name)
            if v is not None and v != "":
                return v
        return default

    def _to_float(self, v: Any) -> Optional[float]:
        if v is None:
            return None
        try:
            return float(str(v).replace(",", "").replace("$", "").replace("€", "").replace("£", "").strip())
        except (ValueError, TypeError):
            return None

    # Common identification
    @property
    def document_number(self) -> Optional[str]:
        return self.get("invoice_number", "receipt_number", "order_number",
                        "document_number", "reference_number", "po_number", "bill_number")

    @property
    def vendor_name(self) -> Optional[str]:
        return self.get("vendor_name", "vendor", "supplier_name", "supplier",
                        "merchant", "company_name", "issued_by", "seller", "from")

    @property
    def customer_name(self) -> Optional[str]:
        return self.get("customer_name", "customer", "client_name", "client",
                        "billed_to", "bill_to", "buyer", "ship_to")

    @property
    def document_date(self) -> Optional[str]:
        return self.get("invoice_date", "receipt_date", "order_date", "issue_date",
                        "date", "transaction_date", "statement_date")

    @property
    def due_date(self) -> Optional[str]:
        return self.get("due_date", "payment_due", "payment_due_date", "expiry_date")

    @property
    def total_amount(self) -> Optional[float]:
        return self._to_float(
            self.get("total_amount", "total", "amount_due", "balance_due",
                     "grand_total", "invoice_total", "amount_payable")
        )

    @property
    def subtotal(self) -> Optional[float]:
        return self._to_float(
            self.get("subtotal", "sub_total", "net_amount", "net", "taxable_amount")
        )

    @property
    def tax_amount(self) -> Optional[float]:
        return self._to_float(
            self.get("tax_amount", "tax", "vat_amount", "gst_amount", "hst_amount",
                     "sales_tax", "value_added_tax")
        )

    @property
    def currency(self) -> Optional[str]:
        return self.get("currency", "currency_code")

    @property
    def iban(self) -> Optional[str]:
        return self.get("iban", "bank_iban")


# ── Pipeline result models ────────────────────────────────────────────────────

class FieldValidation(BaseModel):
    field:           str
    status:          ValidationStatus
    message:         Optional[str] = None
    original_value:  Optional[str] = None
    corrected_value: Optional[str] = None


class ExtractionResult(BaseModel):
    raw_ocr_text:   str
    extracted_data: DocumentData
    confidence:     float = Field(ge=0.0, le=1.0, default=0.0)
    vlm_response:   Optional[str] = None
    ocr_used:       bool = False


class ValidationResult(BaseModel):
    is_valid:           bool
    field_validations:  list[FieldValidation] = Field(default_factory=list)
    failed_fields:      list[str]             = Field(default_factory=list)
    overall_confidence: float                 = Field(ge=0.0, le=1.0, default=0.0)


class ProcessingRecord(BaseModel):
    document_id:           str
    source_path:           str
    doc_type:              str  = "unknown"
    raw_ocr_text:          str
    vlm_extraction:        dict
    corrections_applied:   list[dict] = Field(default_factory=list)
    final_data:            dict
    validation_status:     ValidationStatus
    extraction_confidence: float = 0.0
    processing_notes:      list[str] = Field(default_factory=list)
