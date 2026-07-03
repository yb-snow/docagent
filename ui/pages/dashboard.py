"""Dashboard page — live KPIs, aggregate metrics, trend chart, and pipeline health."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

sys.path.insert(0, os.getcwd())

import config
from ui.styles import badge, page_header
from ui.components.metrics import render_aggregate_row, render_kpi_row
from ui.components.field_groups import currency_symbol


def _load_stats() -> dict:
    try:
        from database.storage import get_stats
        return get_stats()
    except Exception:
        return {
            "total": 0, "success_rate": 0.0, "pending": 0, "today": 0,
            "by_type": {}, "avg_latency_s": None, "total_cost": None,
            "avg_cost_per_invoice": None,
        }


def _load_recent(limit: int = 8) -> list[dict]:
    try:
        from database.storage import list_records
        return list_records(limit=limit)
    except Exception:
        return []


def _load_daily_volume() -> list[dict]:
    try:
        from database.storage import get_daily_volume
        return get_daily_volume(days=7)
    except Exception:
        return []


def _section(label: str) -> None:
    st.markdown(f'<div class="section-header">{label}</div>', unsafe_allow_html=True)


def _check_pipeline_health() -> list[tuple[str, bool, str]]:
    """Live health checks for each pipeline stage — replaces a previously
    hardcoded 'everything is OK' display with checks that can actually fail."""
    import shutil
    import config
    from pipeline.ingestion import _find_poppler_path
    from pipeline.ocr import _TESSERACT_AVAILABLE

    checks: list[tuple[str, bool, str]] = []

    poppler_ok = _find_poppler_path() is not None or shutil.which("pdftoppm") is not None
    checks.append((
        "Ingestion", poppler_ok,
        "Poppler found" if poppler_ok else "Poppler not found — PDF ingestion will fail",
    ))

    backend = config.VLM_BACKEND
    if backend == "gemini":
        vlm_ok  = bool(config.GEMINI_API_KEY)
        vlm_msg = "Gemini configured" if vlm_ok else "No Gemini API key set (see Settings)"
    elif backend == "claude":
        vlm_ok  = bool(config.ANTHROPIC_API_KEY)
        vlm_msg = "Claude configured" if vlm_ok else "No Anthropic API key set (see Settings)"
    else:
        vlm_ok, vlm_msg = True, f"{backend} — local, no API key required"
    checks.append(("Extraction (VLM)", vlm_ok, vlm_msg))

    checks.append((
        "OCR Fallback", _TESSERACT_AVAILABLE,
        "Tesseract available" if _TESSERACT_AVAILABLE else "Tesseract not found",
    ))
    checks.append(("Validation", True, "Rule-based — always available, no external dependency"))
    checks.append(("Correction", vlm_ok, vlm_msg))

    try:
        from database.storage import _get_conn
        with _get_conn() as conn:
            conn.execute("SELECT 1")
        checks.append(("Storage", True, "SQLite reachable"))
    except Exception as e:
        checks.append(("Storage", False, f"SQLite error: {e}"))

    return checks


def _pipeline_stages() -> None:
    for name, ok, msg in _check_pipeline_health():
        col_a, col_b = st.columns([3, 1])
        with col_a:
            st.markdown(f"<span style='font-size:.88rem;font-weight:500'>{name}</span>",
                        unsafe_allow_html=True)
        with col_b:
            icon, color, label = ("✅", "#16a34a", "OK") if ok else ("⚠️", "#dc2626", "Issue")
            st.markdown(f"<span style='font-size:.82rem;color:{color};font-weight:600'>{icon} {label}</span>",
                        unsafe_allow_html=True)
        if not ok:
            st.caption(f"⚠️ {msg}")
        st.markdown("<div style='height:1px;background:#f0f4f8;margin:4px 0'></div>",
                    unsafe_allow_html=True)


def render() -> None:
    page_header("📊", "Dashboard", "Real-time overview of document processing activity")

    stats  = _load_stats()
    recent = _load_recent()

    # ── Row 1: Core KPIs ─────────────────────────────────────────────────────
    _section("Processing Overview")
    render_kpi_row(
        total=stats["total"],
        success_rate=stats["success_rate"],
        pending=stats["pending"],
        today=stats["today"],
    )

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    # ── Row 2: Aggregate Metrics ──────────────────────────────────────────────
    _section("Aggregate Metrics")
    render_aggregate_row(
        avg_latency_s=stats.get("avg_latency_s"),
        avg_cost_per_invoice=stats.get("avg_cost_per_invoice"),
        total_cost=stats.get("total_cost"),
        currency_symbol=currency_symbol(config.LOCAL_CURRENCY),
    )

    st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)

    # ── Main body: chart + activity | right panel ─────────────────────────────
    left, right = st.columns([3, 1], gap="large")

    with left:
        # Volume trend chart
        _section("Daily Volume — Last 7 Days")
        daily = _load_daily_volume()

        # Always show a 7-day window even if some days have no data
        today_dt = datetime.utcnow().date()
        date_range = [(today_dt - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
        volume_map = {d["day"]: d["count"] for d in daily}
        chart_df = pd.DataFrame({
            "Date": [d[-5:] for d in date_range],   # "MM-DD" labels
            "Documents": [volume_map.get(d, 0) for d in date_range],
        }).set_index("Date")

        st.markdown('<div class="chart-container">', unsafe_allow_html=True)
        st.bar_chart(chart_df, height=200, color="#2563eb")
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

        # Recent activity table
        _section("Recent Activity")
        if not recent:
            st.info("No documents processed yet. Go to **Process Document** to get started.")
        else:
            # Header row
            st.markdown(
                '<div class="activity-header activity-row">'
                '<span>Document</span><span>Vendor</span>'
                '<span>Amount</span><span>Confidence</span><span>Status</span>'
                '</div>',
                unsafe_allow_html=True,
            )
            for doc in recent:
                final  = json.loads(doc.get("final_data") or "{}")
                fields = final.get("fields", final)   # support both nested and flat
                status = doc.get("validation_status", "unknown")
                conf   = doc.get("extraction_confidence", 0.0)
                b      = badge(
                    status,
                    status if status in ("valid", "failed", "corrected", "pending_review", "rejected")
                    else "review",
                )
                fname  = (doc.get("source_path") or "").split("/")[-1] or doc["document_id"][:12]
                vendor = (
                    fields.get("vendor_name") or fields.get("vendor") or
                    fields.get("supplier_name") or fields.get("merchant") or "—"
                )
                total_amt = (
                    fields.get("total_amount") or fields.get("total") or
                    fields.get("amount_due") or fields.get("grand_total") or
                    fields.get("invoice_total") or fields.get("amount_payable")
                )
                try:
                    amt_val = float(
                        str(total_amt).replace(",", "").replace("$", "")
                        .replace("₹", "").replace("€", "").replace("£", "").strip()
                    )
                    total_str = f"{currency_symbol(fields.get('currency'))}{amt_val:,.2f}"
                except Exception:
                    total_str = "—"

                conf_color = "#16a34a" if conf >= 0.85 else "#d97706" if conf >= 0.60 else "#dc2626"
                conf_bar = (
                    f'<div style="display:flex;align-items:center;gap:6px">'
                    f'<div style="flex:1;height:5px;background:#e2e8f0;border-radius:3px">'
                    f'<div style="width:{conf*100:.0f}%;height:100%;background:{conf_color};border-radius:3px"></div>'
                    f'</div><span style="font-size:.78rem;color:{conf_color};font-weight:600">{conf*100:.0f}%</span>'
                    f'</div>'
                )

                with st.container(border=True):
                    c1, c2, c3, c4, c5 = st.columns([2.2, 1.8, 1, 1.4, 1])
                    with c1:
                        st.markdown(
                            f"<span style='font-weight:600;font-size:.88rem'>{fname}</span><br/>"
                            f"<span style='font-size:.73rem;color:#64748b'>{doc['document_id'][:8]}…</span>",
                            unsafe_allow_html=True,
                        )
                    with c2:
                        st.markdown(
                            f"<span style='font-size:.85rem'>{vendor}</span>",
                            unsafe_allow_html=True,
                        )
                    with c3:
                        st.markdown(
                            f"<span style='font-size:.88rem;font-weight:600'>{total_str}</span>",
                            unsafe_allow_html=True,
                        )
                    with c4:
                        st.markdown(conf_bar, unsafe_allow_html=True)
                    with c5:
                        st.markdown(b, unsafe_allow_html=True)

    with right:
        # Pipeline health
        _section("Pipeline Health")
        with st.container(border=True):
            _pipeline_stages()

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

        # Document type breakdown
        _section("Document Types")
        with st.container(border=True):
            by_type = stats.get("by_type", {})
            doc_total = stats["total"] or 1
            type_config = [
                ("🧾", "Invoices",       "invoice"),
                ("🧾", "Receipts",       "receipt"),
                ("📋", "Forms",          "form"),
                ("📦", "Purchase Orders","purchase_order"),
                ("📄", "Other",          "other"),
            ]
            found_any = False
            for icon, label, key in type_config:
                cnt = by_type.get(key, 0)
                if cnt == 0:
                    continue
                found_any = True
                pct = cnt / doc_total
                st.markdown(
                    f"<div style='display:flex;justify-content:space-between;margin-bottom:2px'>"
                    f"<span style='font-size:.83rem'>{icon} {label}</span>"
                    f"<span style='font-size:.8rem;font-weight:600;color:#1a2744'>{cnt} <span style='color:#64748b;font-weight:400'>({pct*100:.0f}%)</span></span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                st.progress(pct)
            if not found_any:
                st.caption("No documents yet.")

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

        # Quick actions
        _section("Quick Actions")
        with st.container(border=True):
            st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
            if st.button("➕  Process New Document", use_container_width=True):
                st.session_state["current_page"] = "Process Document"
                st.rerun()
            if st.button("🔍  Open Review Queue", use_container_width=True):
                st.session_state["current_page"] = "Review Queue"
                st.rerun()
            if st.button("📜  View Full History", use_container_width=True):
                st.session_state["current_page"] = "History"
                st.rerun()
