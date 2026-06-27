"""Latency breakdown panel — parses timing from processing notes and renders a bar chart."""

from __future__ import annotations

import re
import streamlit as st

# Maps display label → emoji icon
_STAGE_ICONS = {
    "ingest":       "📥",
    "extract":      "🔍",
    "ocr_fallback": "📄",
    "validate":     "✅",
    "correct":      "🔄",
    "store":        "💾",
    "review_queue": "👁️",
}

_STAGE_LABELS = {
    "ingest":       "Ingestion",
    "extract":      "VLM Extraction",
    "ocr_fallback": "OCR Fallback",
    "validate":     "Validation",
    "correct":      "Auto-Correction",
    "store":        "Storage",
    "review_queue": "Review Queue",
}


def _parse_timings(notes: list[str], timings_dict: dict | None = None) -> dict[str, float]:
    """
    Extract per-node seconds from processing notes.
    Notes contain patterns like  '· ⏱ 3.2s'  or  '⏱ Total pipeline time: 4.8s'
    Falls back to timings_dict (stored in final_data) if available.
    """
    if timings_dict:
        return {k: v for k, v in timings_dict.items() if k != "total"}

    # Parse from notes text
    result = {}
    stage_keys = list(_STAGE_LABELS.keys())

    for note in notes:
        m = re.search(r"⏱\s*([\d.]+)s", note)
        if not m:
            continue
        secs = float(m.group(1))
        note_lower = note.lower()
        for key in stage_keys:
            label = _STAGE_LABELS[key].lower()
            # match by keyword in note
            if key in note_lower or any(w in note_lower for w in label.split()):
                result[key] = secs
                break

    return result


def render(notes: list[str], timings_dict: dict | None = None) -> None:
    """
    Render a latency breakdown panel.

    notes        : processing_notes list from the pipeline state
    timings_dict : optional pre-parsed timings dict from final_data['timings']
    """
    # Extract total from notes
    total_s = None
    for note in notes:
        m = re.search(r"Total pipeline time:\s*([\d.]+)s", note)
        if m:
            total_s = float(m.group(1))
            break

    # Parse per-stage timings
    timings = _parse_timings(notes, timings_dict)

    if not timings and total_s is None:
        st.caption("No timing data available for this document.")
        return

    st.markdown("**⏱ Latency Breakdown**")

    if timings:
        max_t = max(timings.values()) if timings else 1.0

        for key, label in _STAGE_LABELS.items():
            if key not in timings:
                continue
            secs  = timings[key]
            icon  = _STAGE_ICONS.get(key, "▪️")
            pct   = secs / max(max_t, 0.01)

            col_label, col_bar, col_val = st.columns([2, 5, 1])
            with col_label:
                st.markdown(
                    f"<div style='font-size:.82rem;color:#374151;padding-top:4px;'>"
                    f"{icon} {label}</div>",
                    unsafe_allow_html=True,
                )
            with col_bar:
                # Colour bar: red for slowest, green for fastest
                hue = int(120 * (1 - pct))   # 0=red, 120=green
                bar_color = f"hsl({hue},70%,45%)"
                bar_width  = max(int(pct * 100), 4)
                st.markdown(
                    f"<div style='background:#f1f5f9;border-radius:4px;margin-top:6px;'>"
                    f"<div style='background:{bar_color};width:{bar_width}%;"
                    f"height:10px;border-radius:4px;'></div></div>",
                    unsafe_allow_html=True,
                )
            with col_val:
                st.markdown(
                    f"<div style='font-size:.82rem;font-weight:600;color:#1a2744;"
                    f"text-align:right;padding-top:4px;'>{secs}s</div>",
                    unsafe_allow_html=True,
                )

    if total_s is not None:
        st.markdown(
            f"<div style='margin-top:10px;padding:10px 14px;"
            f"background:#f0fdf4;border-radius:8px;border-left:4px solid #16a34a;'>"
            f"<span style='font-size:.85rem;color:#166534;font-weight:700;'>"
            f"⏱ Total pipeline time: <strong>{total_s}s</strong></span>"
            f"</div>",
            unsafe_allow_html=True,
        )
    elif timings:
        total_computed = round(sum(timings.values()), 2)
        st.markdown(
            f"<div style='margin-top:10px;padding:10px 14px;"
            f"background:#f0fdf4;border-radius:8px;border-left:4px solid #16a34a;'>"
            f"<span style='font-size:.85rem;color:#166534;font-weight:700;'>"
            f"⏱ Measured stages total: {total_computed}s</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
