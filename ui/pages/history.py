"""History page — browse all processed records, view details, filter, export."""

from __future__ import annotations

import json
import os
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, os.getcwd())

from ui.styles import badge, page_header
from ui.components.latency_panel import render as render_latency


def _load_records() -> list[dict]:
    try:
        from database.storage import list_records
        return list_records(limit=500)
    except Exception:
        return []


def _to_display_df(raw: list[dict]) -> pd.DataFrame:
    rows = []
    for r in raw:
        final = json.loads(r.get("final_data") or "{}")
        rows.append({
            "ID":         r["document_id"][:8],
            "File":       (r.get("source_path") or "").split("/")[-1] or "—",
            "Type":       (r.get("doc_type") or "invoice").title(),
            "Vendor":     final.get("vendor_name") or "—",
            "Total":      final.get("total_amount"),
            "Status":     r.get("validation_status", "unknown"),
            "Confidence": f"{(r.get('extraction_confidence') or 0)*100:.0f}%",
            "Date":       (r.get("created_at") or "")[:10],
        })
    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["ID", "File", "Type", "Vendor", "Total", "Status", "Confidence", "Date"]
    )


def render() -> None:
    page_header("📋", "History", "All processed documents — click any row to view full details")

    raw     = _load_records()
    df      = _to_display_df(raw)

    if df.empty:
        st.info("No documents processed yet. Go to **Process Document** to get started.")
        return

    # ── Filters ───────────────────────────────────────────────────────────────
    f1, f2, f3 = st.columns([3, 1.5, 1.5])
    with f1:
        search = st.text_input("🔍 Search", placeholder="File name or vendor…",
                               label_visibility="collapsed")
    with f2:
        types    = ["All"] + sorted(df["Type"].dropna().unique().tolist())
        t_filter = st.selectbox("Type", types, label_visibility="collapsed")
    with f3:
        statuses  = ["All"] + sorted(df["Status"].dropna().unique().tolist())
        s_filter  = st.selectbox("Status", statuses, label_visibility="collapsed")

    filtered_df  = df.copy()
    filtered_raw = list(raw)

    if search:
        mask = (
            filtered_df["File"].str.contains(search, case=False, na=False)
            | filtered_df["Vendor"].str.contains(search, case=False, na=False)
        )
        filtered_df  = filtered_df[mask]
        filtered_raw = [r for r, keep in zip(raw, mask) if keep]

    if t_filter != "All":
        mask = filtered_df["Type"] == t_filter
        filtered_df  = filtered_df[mask]
        filtered_raw = [r for r, keep in zip(filtered_raw, mask) if keep]

    if s_filter != "All":
        mask = filtered_df["Status"] == s_filter
        filtered_df  = filtered_df[mask]
        filtered_raw = [r for r, keep in zip(filtered_raw, mask) if keep]

    filtered_df = filtered_df.reset_index(drop=True)

    st.caption(f"Showing {len(filtered_df)} of {len(df)} records  ·  select a row to view details")

    # ── Table ─────────────────────────────────────────────────────────────────
    selected = st.dataframe(
        filtered_df,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "Total":  st.column_config.NumberColumn("Total", format="$%.2f"),
            "Status": st.column_config.TextColumn("Status"),
        },
    )

    # ── Export ────────────────────────────────────────────────────────────────
    ec1, ec2, _ = st.columns([1, 1, 3])
    with ec1:
        st.download_button("⬇️ Export CSV",
            data=filtered_df.to_csv(index=False),
            file_name="doc_agent_history.csv", mime="text/csv",
            use_container_width=True,
            key="hist_export_csv")
    with ec2:
        st.download_button("⬇️ Export JSON",
            data=filtered_df.to_json(orient="records", indent=2),
            file_name="doc_agent_history.json", mime="application/json",
            use_container_width=True,
            key="hist_export_json")

    # ── Detail panel (shown when a row is selected) ───────────────────────────
    rows_sel = selected.get("selection", {}).get("rows", [])
    if not rows_sel:
        return

    idx     = rows_sel[0]
    if idx >= len(filtered_raw):
        return

    record  = filtered_raw[idx]
    final   = json.loads(record.get("final_data")  or "{}")
    vlm_raw = json.loads(record.get("vlm_extraction") or "{}")
    notes   = json.loads(record.get("processing_notes") or "[]")
    corrections = json.loads(record.get("corrections") or "[]")
    status  = record.get("validation_status", "unknown")

    st.markdown("---")
    st.markdown(f"### 📄 Document Details — `{record['document_id'][:8]}`")

    col_status, col_conf, col_type, col_date = st.columns(4)
    col_status.metric("Status",     status.replace("_", " ").title())
    col_conf.metric("Confidence",   f"{(record.get('extraction_confidence') or 0)*100:.0f}%")
    col_type.metric("Type",         (record.get("doc_type") or "invoice").title())
    col_date.metric("Processed",    (record.get("created_at") or "")[:10])

    tab_fields, tab_items, tab_ocr, tab_latency, tab_audit, tab_export = st.tabs([
        "📋 Extracted Fields", "🗒️ Line Items", "📄 Raw OCR",
        "⏱ Latency", "🔍 Audit Trail", "⬇️ Export"
    ])

    with tab_fields:
        from ui.components.field_groups import format_value, group_fields, pretty_label

        # Fields are stored under final["fields"], not at the top level
        fields_dict = final.get("fields") or {}
        currency    = str(fields_dict.get("currency") or "")

        if not fields_dict:
            st.info("No fields were extracted for this document.")
        else:
            groups = group_fields(fields_dict)
            for group_label, group_fields_dict in groups.items():
                st.markdown(f"**{group_label}**")
                cols = st.columns(2)
                for i, (fkey, fval) in enumerate(group_fields_dict.items()):
                    cols[i % 2].text_input(
                        pretty_label(fkey),
                        value=format_value(fkey, fval, currency),
                        disabled=True,
                        key=f"hist_{record['document_id']}_{fkey}",
                    )
                st.markdown(
                    "<hr style='margin:8px 0;border-color:#e2e8f0'/>",
                    unsafe_allow_html=True,
                )

        if corrections:
            st.markdown("**Auto-corrections applied:**")
            for c in corrections:
                st.markdown(
                    f"- `{c.get('field')}`: "
                    f"`{c.get('original_value')}` → `{c.get('corrected_value')}`"
                )

    with tab_items:
        items = final.get("line_items") or vlm_raw.get("line_items") or []
        if items:
            st.dataframe(pd.DataFrame(items), use_container_width=True, hide_index=True)
        else:
            st.info("No line items in this document.")

    with tab_ocr:
        ocr_text = record.get("raw_ocr_text") or ""
        if ocr_text.strip():
            st.text_area("Raw OCR Text", value=ocr_text, height=220, disabled=True,
                         key=f"ocr_{record['document_id']}")
        else:
            st.info("OCR was not used for this document (high confidence extraction).")

    with tab_latency:
        timings = final.get("timings") or {}
        render_latency(notes, timings_dict={k: v for k, v in timings.items() if k != "total"})

    with tab_audit:
        try:
            from database.storage import get_audit_trail
            events = get_audit_trail(record["document_id"])
            if events:
                audit_df = pd.DataFrame([{
                    "Time":    e["timestamp"],
                    "Event":   e["event"],
                    "Details": e["details"],
                } for e in events])
                st.dataframe(audit_df, use_container_width=True, hide_index=True)
            else:
                st.info("No audit events found.")
        except Exception as e:
            st.warning(f"Could not load audit trail: {e}")

    with tab_export:
        doc_json = json.dumps(final, indent=2, default=str)
        c1, c2 = st.columns(2)
        with c1:
            st.download_button(
                "⬇️ Download JSON",
                data=doc_json,
                file_name=f"doc_{record['document_id'][:8]}.json",
                mime="application/json",
                use_container_width=True,
                key=f"dl_json_{record['document_id']}",
            )
        with c2:
            st.download_button(
                "⬇️ Download CSV",
                data=pd.DataFrame([{k: v for k, v in final.items()
                                    if k != "line_items"}]).to_csv(index=False),
                file_name=f"doc_{record['document_id'][:8]}.csv",
                mime="text/csv",
                use_container_width=True,
                key=f"dl_csv_{record['document_id']}",
            )
