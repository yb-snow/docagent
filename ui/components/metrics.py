from __future__ import annotations

import streamlit as st


def metric_card(label: str, value: str, delta: str = "", color: str = "blue", icon: str = "") -> str:
    delta_html = ""
    if delta:
        cls = "delta-up" if delta.startswith("+") else "delta-down"
        delta_html = f'<div class="metric-delta {cls}">{delta}</div>'
    icon_html = f'<div class="metric-icon">{icon}</div>' if icon else ""
    return f"""
    <div class="metric-card {color}">
        {icon_html}
        <div class="metric-label">{label}</div>
        <div class="metric-value">{value}</div>
        {delta_html}
    </div>
    """


def render_kpi_row(total: int, success_rate: float, pending: int, today: int) -> None:
    cols = st.columns(4)
    cards = [
        (cols[0], metric_card("Total Processed", str(total), icon="📄", color="blue")),
        (cols[1], metric_card("Success Rate", f"{success_rate:.1f}%",
                              "+2.3% vs last week" if success_rate > 0 else "", "green", "✅")),
        (cols[2], metric_card("Pending Review", str(pending),
                              "⚠️ needs attention" if pending > 5 else "", "amber", "🕐")),
        (cols[3], metric_card("Today's Volume", str(today), icon="📅", color="blue")),
    ]
    for col, html in cards:
        with col:
            st.markdown(html, unsafe_allow_html=True)


def render_aggregate_row(
    avg_latency_s: float | None,
    avg_cost_per_invoice: float | None,
    total_cost: float | None,
) -> None:
    latency_val = f"{avg_latency_s:.1f}s" if avg_latency_s is not None else "—"
    avg_cost_val = f"${avg_cost_per_invoice:,.2f}" if avg_cost_per_invoice is not None else "—"
    total_cost_val = f"${total_cost:,.2f}" if total_cost is not None else "—"

    cols = st.columns(3)
    cards = [
        (cols[0], metric_card("Avg Processing Latency", latency_val, icon="⚡", color="purple")),
        (cols[1], metric_card("Avg Cost / Invoice", avg_cost_val, icon="💰", color="teal")),
        (cols[2], metric_card("Total Invoice Value", total_cost_val, icon="📊", color="indigo")),
    ]
    for col, html in cards:
        with col:
            st.markdown(html, unsafe_allow_html=True)
