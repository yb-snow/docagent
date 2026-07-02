"""SQLite storage — CRUD, audit log, review queue, stats, and export."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import SQLITE_PATH
from models.schemas import ProcessingRecord


def _get_conn() -> sqlite3.Connection:
    Path(SQLITE_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS invoice_records (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id           TEXT UNIQUE NOT NULL,
                source_path           TEXT,
                doc_type              TEXT DEFAULT 'invoice',
                raw_ocr_text          TEXT,
                vlm_extraction        TEXT,
                corrections           TEXT,
                final_data            TEXT,
                validation_status     TEXT,
                extraction_confidence REAL DEFAULT 0.0,
                processing_notes      TEXT,
                created_at            TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id TEXT NOT NULL,
                event       TEXT,
                details     TEXT,
                timestamp   TEXT DEFAULT (datetime('now'))
            )
        """)
        # Add new columns to existing DBs without failing
        for col, typedef in [
            ("doc_type",              "TEXT DEFAULT 'invoice'"),
            ("extraction_confidence", "REAL DEFAULT 0.0"),
            ("processing_time_s",     "REAL DEFAULT NULL"),
        ]:
            try:
                conn.execute(f"ALTER TABLE invoice_records ADD COLUMN {col} {typedef}")
            except Exception:
                pass  # column already exists


# ── Write ─────────────────────────────────────────────────────────────────────

def save_record(record: ProcessingRecord) -> None:
    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO invoice_records
                (document_id, source_path, doc_type, raw_ocr_text, vlm_extraction,
                 corrections, final_data, validation_status, extraction_confidence,
                 processing_notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(document_id) DO UPDATE SET
                doc_type              = excluded.doc_type,
                vlm_extraction        = excluded.vlm_extraction,
                corrections           = excluded.corrections,
                final_data            = excluded.final_data,
                validation_status     = excluded.validation_status,
                extraction_confidence = excluded.extraction_confidence,
                processing_notes      = excluded.processing_notes
            """,
            (
                record.document_id,
                record.source_path,
                record.doc_type,
                record.raw_ocr_text,
                json.dumps(record.vlm_extraction),
                json.dumps(record.corrections_applied),
                json.dumps(record.final_data),
                record.validation_status.value,
                record.extraction_confidence,
                json.dumps(record.processing_notes),
            ),
        )


def log_event(document_id: str, event: str, details: Optional[dict] = None) -> None:
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO audit_log (document_id, event, details) VALUES (?, ?, ?)",
            (document_id, event, json.dumps(details or {})),
        )


# ── Read ──────────────────────────────────────────────────────────────────────

def get_record(document_id: str) -> Optional[dict]:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM invoice_records WHERE document_id = ?", (document_id,)
        ).fetchone()
    return dict(row) if row else None


def list_records(limit: int = 200, status: Optional[str] = None) -> list[dict]:
    with _get_conn() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM invoice_records WHERE validation_status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM invoice_records ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
    return [dict(r) for r in rows]


def get_pending_review(limit: int = 100) -> list[dict]:
    return list_records(limit=limit, status="pending_review")


def get_audit_trail(document_id: str) -> list[dict]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_log WHERE document_id = ? ORDER BY timestamp ASC",
            (document_id,),
        ).fetchall()
    return [dict(r) for r in rows]


# ── Duplicate detection ───────────────────────────────────────────────────────

def find_duplicate(
    vendor_name: Optional[str],
    invoice_number: Optional[str],
    total_amount: Optional[float],
    invoice_date: Optional[str],
    exclude_document_id: Optional[str] = None,
) -> Optional[dict]:
    """Look for an already-stored record that looks like the same document.

    Match strategy: same vendor + same invoice/document number (strong
    match), or — if no number is available on either side — same vendor +
    same total + same date. Rejected records are excluded so a corrected
    resubmission of a previously-rejected document isn't flagged forever.
    """
    if not vendor_name:
        return None
    vendor_norm = vendor_name.strip().lower()

    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT document_id, final_data FROM invoice_records "
            "WHERE validation_status != 'rejected'"
        ).fetchall()

    for row in rows:
        if exclude_document_id and row["document_id"] == exclude_document_id:
            continue
        try:
            data   = json.loads(row["final_data"] or "{}")
            fields = data.get("fields") or {}
        except Exception:
            continue

        existing_vendor = str(
            fields.get("vendor_name") or fields.get("vendor") or
            fields.get("supplier_name") or fields.get("merchant") or ""
        ).strip().lower()
        if not existing_vendor or existing_vendor != vendor_norm:
            continue

        existing_number = (
            fields.get("invoice_number") or fields.get("receipt_number") or
            fields.get("document_number") or fields.get("reference_number")
        )
        if invoice_number and existing_number and \
           str(existing_number).strip().lower() == str(invoice_number).strip().lower():
            return {"document_id": row["document_id"], "reason": "same vendor + invoice number"}

        if not invoice_number or not existing_number:
            existing_total = fields.get("total_amount") or fields.get("total")
            existing_date  = fields.get("invoice_date") or fields.get("date")
            if total_amount is not None and existing_total is not None and invoice_date and existing_date:
                try:
                    if abs(float(existing_total) - float(total_amount)) < 0.01 \
                       and str(existing_date) == str(invoice_date):
                        return {"document_id": row["document_id"], "reason": "same vendor + amount + date"}
                except (TypeError, ValueError):
                    pass

    return None


# ── Review queue actions ──────────────────────────────────────────────────────

def approve_record(document_id: str, updated_data: dict) -> None:
    with _get_conn() as conn:
        conn.execute(
            """UPDATE invoice_records
               SET validation_status = 'valid', final_data = ?
               WHERE document_id = ?""",
            (json.dumps(updated_data), document_id),
        )
    log_event(document_id, "approved", {"by": "human_reviewer"})


def reject_record(document_id: str) -> None:
    with _get_conn() as conn:
        conn.execute(
            "UPDATE invoice_records SET validation_status = 'rejected' WHERE document_id = ?",
            (document_id,),
        )
    log_event(document_id, "rejected", {"by": "human_reviewer"})


# ── Aggregates for dashboard ──────────────────────────────────────────────────

def get_stats() -> dict:
    with _get_conn() as conn:
        total   = conn.execute("SELECT COUNT(*) FROM invoice_records").fetchone()[0]
        valid   = conn.execute(
            "SELECT COUNT(*) FROM invoice_records WHERE validation_status IN ('valid','corrected')"
        ).fetchone()[0]
        pending = conn.execute(
            "SELECT COUNT(*) FROM invoice_records WHERE validation_status = 'pending_review'"
        ).fetchone()[0]
        today   = conn.execute(
            "SELECT COUNT(*) FROM invoice_records WHERE created_at >= date('now')"
        ).fetchone()[0]

        by_type = conn.execute(
            "SELECT doc_type, COUNT(*) as cnt FROM invoice_records GROUP BY doc_type"
        ).fetchall()

        final_data_rows = conn.execute(
            "SELECT final_data FROM invoice_records WHERE final_data IS NOT NULL AND final_data != '{}'"
        ).fetchall()

    amounts  = []
    latencies = []
    for row in final_data_rows:
        try:
            data   = json.loads(row[0] or "{}")
            fields = data.get("fields", {})

            # Latency — stored in final_data["timings"]["total"] by the pipeline
            timings = data.get("timings", {})
            if isinstance(timings, dict) and timings.get("total"):
                latencies.append(float(timings["total"]))

            # Cost — total_amount lives inside data["fields"]
            amt_raw = (
                fields.get("total_amount")
                or fields.get("total")
                or fields.get("amount_due")
                or fields.get("grand_total")
                or fields.get("invoice_total")
                or fields.get("amount_payable")
            )
            if amt_raw is not None:
                amt = float(
                    str(amt_raw)
                    .replace(",", "").replace("$", "").replace("€", "")
                    .replace("£", "").replace("₹", "").replace("RS", "").strip()
                )
                if amt > 0:
                    amounts.append(amt)
        except Exception:
            pass

    total_cost  = sum(amounts)    if amounts   else None
    avg_cost    = total_cost / len(amounts)    if amounts   else None
    avg_latency = sum(latencies) / len(latencies) if latencies else None

    return {
        "total":        total,
        "success_rate": round(valid / total * 100, 1) if total else 0.0,
        "pending":      pending,
        "today":        today,
        "by_type":      {r["doc_type"]: r["cnt"] for r in by_type},
        "avg_latency_s":        avg_latency,
        "total_cost":           total_cost,
        "avg_cost_per_invoice": avg_cost,
    }


def get_daily_volume(days: int = 7) -> list[dict]:
    """Return per-day document counts for the last N days."""
    with _get_conn() as conn:
        rows = conn.execute(
            """
            SELECT date(created_at) as day, COUNT(*) as cnt
            FROM invoice_records
            WHERE created_at >= date('now', ?)
            GROUP BY day ORDER BY day ASC
            """,
            (f"-{days} days",),
        ).fetchall()
    return [{"day": r["day"], "count": r["cnt"]} for r in rows]


# ── Export ────────────────────────────────────────────────────────────────────

def export_json(document_id: str) -> str:
    record = get_record(document_id)
    if not record:
        return "{}"
    data = json.loads(record.get("final_data") or "{}")
    return json.dumps(data, indent=2, default=str)


def export_all_csv() -> str:
    import csv, io
    records = list_records(limit=10000)
    if not records:
        return ""
    buf = io.StringIO()
    fields = ["document_id", "source_path", "doc_type", "validation_status",
              "extraction_confidence", "created_at"]
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(records)
    return buf.getvalue()
