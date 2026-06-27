"""Review Queue — human approval for low-confidence / failed documents."""

from __future__ import annotations

import json
import os
import sys

import streamlit as st

sys.path.insert(0, os.getcwd())

from ui.styles import badge, page_header
from ui.components.latency_panel import render as render_latency


def _load_pending() -> list[dict]:
    try:
        from database.storage import get_pending_review
        return get_pending_review(limit=100)
    except Exception:
        return []


def render() -> None:
    page_header("👁️", "Review Queue", "Documents flagged for human verification")

    pending_records = _load_pending()

    # ── Stats ──────────────────────────────────────────────────────────────
    c1, c2, c3 = st.columns(3)
    c1.metric("Pending Review",        len(pending_records))
    c2.metric("Approved (this session)", len(st.session_state.get("approved_ids", set())))
    c3.metric("Rejected (this session)", len(st.session_state.get("rejected_ids",  set())))

    if "approved_ids" not in st.session_state:
        st.session_state.approved_ids = set()
    if "rejected_ids" not in st.session_state:
        st.session_state.rejected_ids = set()

    # Filter out already actioned
    pending = [
        r for r in pending_records
        if r["document_id"] not in st.session_state.approved_ids
        and r["document_id"] not in st.session_state.rejected_ids
    ]

    st.markdown("<br/>", unsafe_allow_html=True)

    if not pending:
        st.success("Review queue is empty — all documents have been actioned.")
        return

    for doc in pending:
        doc_id   = doc["document_id"]
        fname    = (doc.get("source_path") or "").split("/")[-1] or doc_id[:12]
        conf     = doc.get("extraction_confidence", 0.0)
        doc_type = (doc.get("doc_type") or "invoice").title()
        notes    = json.loads(doc.get("processing_notes") or "[]")
        final    = json.loads(doc.get("final_data")       or "{}")

        reason = next(
            (n for n in reversed(notes) if "review" in n.lower() or "confidence" in n.lower()),
            "Low confidence or validation failed",
        )

        with st.expander(
            f"🔍  {fname}  ·  {doc_type}  ·  Confidence {conf*100:.0f}%  ·  {reason}",
            expanded=False,
        ):
            from ui.components.field_groups import group_fields, pretty_label

            # Fields live under final["fields"] in the DocumentData schema
            fields_dict = final.get("fields") or {}
            line_items  = final.get("line_items") or []

            left, right = st.columns([2, 1])

            # ── Left: editable field panel ────────────────────────────────────
            with left:
                st.markdown("**Review & Edit Extracted Fields**")
                st.caption("All fields are pre-populated from the AI extraction. "
                           "Correct any errors before approving.")

                edited_fields: dict = {}

                if fields_dict:
                    groups = group_fields(fields_dict)
                    for group_label, gf in groups.items():
                        st.markdown(f"**{group_label}**")
                        cols = st.columns(2)
                        for i, (fkey, fval) in enumerate(gf.items()):
                            edited_fields[fkey] = cols[i % 2].text_input(
                                pretty_label(fkey),
                                value=str(fval) if fval is not None else "",
                                key=f"rv_{doc_id}_{fkey}",
                            )
                        st.markdown(
                            "<hr style='margin:6px 0;border-color:#e2e8f0'/>",
                            unsafe_allow_html=True,
                        )
                else:
                    st.warning(
                        "No fields were extracted. You can still approve or reject the document."
                    )

                # ── Line items (read-only — shown for context) ────────────────
                if line_items:
                    import pandas as pd
                    st.markdown("**Line Items** *(read-only)*")
                    st.dataframe(
                        pd.DataFrame(line_items),
                        use_container_width=True,
                        hide_index=True,
                    )

            # ── Right: summary + action buttons ──────────────────────────────
            with right:
                st.markdown("**Summary**")
                st.markdown(f"- **Doc ID:** `{doc_id[:8]}`")
                st.markdown(f"- **Type:** {doc_type}")
                st.markdown(
                    f"- **Confidence:** "
                    f"<span style='color:{'#d97706' if conf >= 0.5 else '#dc2626'};"
                    f"font-weight:700'>{conf*100:.0f}%</span>",
                    unsafe_allow_html=True,
                )
                st.markdown(f"- **Reason flagged:** {reason}")

                st.markdown("**Processing log:**")
                for note in notes[-5:]:
                    st.caption(f"• {note}")

                st.markdown("<br/>", unsafe_allow_html=True)
                timings = final.get("timings")
                render_latency(notes, timings_dict=timings)

                st.markdown("<br/>", unsafe_allow_html=True)
                col_a, col_r = st.columns(2)

                with col_a:
                    if st.button("✅ Approve & Save", key=f"approve_{doc_id}",
                                 use_container_width=True, type="primary"):
                        try:
                            from database.storage import approve_record

                            # Convert edited text back to typed values
                            _amount_keys = {
                                k for k in edited_fields
                                if any(w in k for w in
                                       ("amount","total","subtotal","tax","price",
                                        "cost","balance","discount","fee","net","gross"))
                            }
                            clean_fields: dict = {}
                            for k, v in edited_fields.items():
                                v = v.strip()
                                if v == "" or v.lower() == "none":
                                    clean_fields[k] = None
                                elif k in _amount_keys:
                                    try:
                                        clean_fields[k] = float(
                                            v.replace(",", "").replace("$", "")
                                             .replace("₹", "").replace("€", "")
                                        )
                                    except ValueError:
                                        clean_fields[k] = v
                                else:
                                    clean_fields[k] = v

                            # Save the full updated final_data (preserves line_items etc.)
                            updated_final = {
                                **final,
                                "fields": clean_fields,
                            }
                            approve_record(doc_id, updated_final)
                            st.session_state.approved_ids.add(doc_id)
                            st.toast(f"Document {doc_id[:8]} approved.", icon="✅")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Could not approve: {e}")

                with col_r:
                    if st.button("❌ Reject", key=f"reject_{doc_id}",
                                 use_container_width=True):
                        try:
                            from database.storage import reject_record
                            reject_record(doc_id)
                            st.session_state.rejected_ids.add(doc_id)
                            st.toast(f"Document {doc_id[:8]} rejected.", icon="🗑️")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Could not reject: {e}")
