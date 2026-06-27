"""Pipeline step indicator — driven by real LangGraph node events."""

from typing import Optional
import streamlit as st

# Maps LangGraph node names → (display label, order index)
# Nodes that share a display label (e.g. correct loops back through validate)
# are collapsed into one stage for display purposes.
_NODE_STAGE_MAP = {
    "ingest":       ("Ingest",    0),
    "extract":      ("Extract",   1),
    "ocr_fallback": ("OCR Check", 2),
    "validate":     ("Validate",  3),
    "correct":      ("Correct",   4),
    "store":        ("Store",     5),
    "review_queue": ("Review",    5),
}

_ALL_STAGES = [
    ("📥", "Ingest"),
    ("🔍", "Extract"),
    ("📄", "OCR Check"),
    ("✅", "Validate"),
    ("🔄", "Correct"),
    ("💾", "Store"),
]


def _stage_index(name: str) -> int:
    return next((i for i, (_, n) in enumerate(_ALL_STAGES) if n == name), -1)


def render_progress(
    completed_nodes: set,
    active_node: Optional[str] = None,
    skipped_nodes: Optional[set] = None,
) -> None:
    """
    Render the stepper reflecting real pipeline progress.

    completed_nodes : set of LangGraph node names that have already finished
    active_node     : node currently executing (shown as spinning blue)
    skipped_nodes   : nodes skipped by a conditional edge (shown dimmed)
    """
    skipped_nodes = skipped_nodes or set()

    completed_stages = set()
    for n in completed_nodes:
        if n in _NODE_STAGE_MAP:
            completed_stages.add(_NODE_STAGE_MAP[n][0])

    active_stage = _NODE_STAGE_MAP.get(active_node, (None,))[0] if active_node else None
    skipped_stages = set()
    for n in skipped_nodes:
        if n in _NODE_STAGE_MAP:
            skipped_stages.add(_NODE_STAGE_MAP[n][0])

    circles = []
    for i, (icon, name) in enumerate(_ALL_STAGES):
        if name in skipped_stages:
            cls, label = "step-pending", "—"
        elif name in completed_stages:
            cls, label = "step-done", "✓"
        elif name == active_stage:
            cls, label = "step-active", icon
        else:
            cls, label = "step-pending", str(i + 1)

        line_cls = "done" if name in completed_stages and i < len(_ALL_STAGES) - 1 else ""
        line_html = f'<div class="step-line {line_cls}"></div>' if i < len(_ALL_STAGES) - 1 else ""

        circles.append(
            f'<div class="step-item">'
            f'<div class="step-circle {cls}">{label}</div>'
            f'<div class="step-name">{name}</div>'
            f'</div>' + line_html
        )

    st.markdown(
        '<div class="step-row">' + "".join(circles) + "</div>",
        unsafe_allow_html=True,
    )


def render(
    current_stage: Optional[str] = None,
    failed_stage: Optional[str] = None,
) -> None:
    """Legacy render — maps stage name string to progress display."""
    stage_names = [n for _, n in _ALL_STAGES]
    active_idx  = stage_names.index(current_stage) if current_stage in stage_names else -1
    failed_idx  = stage_names.index(failed_stage)  if failed_stage  in stage_names else -1

    completed = set(stage_names[:active_idx]) if active_idx > 0 else set()
    active    = current_stage
    skipped: set = set()

    circles = []
    for i, (icon, name) in enumerate(_ALL_STAGES):
        if failed_idx == i:
            cls, label = "step-error", "✗"
        elif name in completed:
            cls, label = "step-done", "✓"
        elif name == active:
            cls, label = "step-active", icon
        else:
            cls, label = "step-pending", str(i + 1)

        line_cls  = "done" if name in completed else ""
        line_html = f'<div class="step-line {line_cls}"></div>' if i < len(_ALL_STAGES) - 1 else ""

        circles.append(
            f'<div class="step-item">'
            f'<div class="step-circle {cls}">{label}</div>'
            f'<div class="step-name">{name}</div>'
            f'</div>' + line_html
        )

    st.markdown(
        '<div class="step-row">' + "".join(circles) + "</div>",
        unsafe_allow_html=True,
    )
