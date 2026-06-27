"""Tech Stack page — architecture layers mapped to technologies."""

from __future__ import annotations
import streamlit as st
from ui.styles import page_header

# ── Colour palette per category ───────────────────────────────────────────────
_CAT_COLORS = {
    "AI / VLM":        ("#dbeafe", "#1e40af", "#3b82f6"),   # bg, text, accent
    "Orchestration":   ("#ede9fe", "#4c1d95", "#7c3aed"),
    "Ingestion":       ("#dcfce7", "#14532d", "#16a34a"),
    "OCR":             ("#fef3c7", "#78350f", "#d97706"),
    "Validation":      ("#fee2e2", "#7f1d1d", "#dc2626"),
    "Storage":         ("#f0fdf4", "#166534", "#22c55e"),
    "UI / Frontend":   ("#f0f9ff", "#0c4a6e", "#0284c7"),
    "Infrastructure":  ("#f5f3ff", "#3b0764", "#a855f7"),
}

# ── Architecture blocks ───────────────────────────────────────────────────────
_BLOCKS = [
    {
        "icon": "📥",
        "title": "Document Ingestion Pipeline",
        "diagram_ref": "Block 1",
        "description": "Converts any uploaded document into clean, pre-processed images ready for the AI models.",
        "category": "Ingestion",
        "techs": [
            {
                "name": "pdf2image",
                "version": "1.17+",
                "role": "PDF → PIL Images",
                "detail": "Converts every PDF page to a high-resolution PIL image at 300 DPI using Poppler under the hood.",
                "link": "https://github.com/Belval/pdf2image",
            },
            {
                "name": "Pillow (PIL)",
                "version": "10+",
                "role": "Image Pre-processing",
                "detail": "Applies contrast enhancement (factor 1.5) and sharpening (factor 1.3) to improve OCR and VLM accuracy.",
                "link": "https://python-pillow.org",
            },
            {
                "name": "OpenCV",
                "version": "4.8+",
                "role": "Deskew / Rotation Fix",
                "detail": "Detects text skew using minAreaRect() and rotates the image to correct orientation before processing.",
                "link": "https://opencv.org",
            },
            {
                "name": "Poppler",
                "version": "23+",
                "role": "PDF Rendering Engine",
                "detail": "System-level library used by pdf2image to rasterise PDF pages. Installed via brew/apt.",
                "link": "https://poppler.freedesktop.org",
            },
        ],
    },
    {
        "icon": "🔍",
        "title": "Classification + Extraction Agent",
        "diagram_ref": "Block 2 & 3",
        "description": "A single VLM call that BOTH identifies the document type (invoice/receipt/form/etc.) AND extracts every visible field — no predefined schema required.",
        "category": "AI / VLM",
        "techs": [
            {
                "name": "Google Gemini",
                "version": "gemini-flash-latest",
                "role": "Primary VLM (FREE)",
                "detail": "Multimodal vision-language model. Free tier: 30 req/min, 1,500 req/day. Get key at aistudio.google.com — just needs a Google account.",
                "link": "https://aistudio.google.com",
            },
            {
                "name": "Anthropic Claude",
                "version": "claude-sonnet-4-6",
                "role": "Alternative VLM (Paid)",
                "detail": "High-accuracy vision model. Requires a paid Anthropic API key. Best for production-grade extraction.",
                "link": "https://console.anthropic.com",
            },
            {
                "name": "Apple MLX (LLaVA / Phi)",
                "version": "mlx-vlm",
                "role": "Local VLM — No API key",
                "detail": "Runs 4-bit quantised vision models (LLaVA-1.5-7B, Phi-3.5) entirely on Apple M-chip via the MLX framework. Downloads ~4–6 GB once, then runs offline.",
                "link": "https://github.com/Blaizzy/mlx-vlm",
            },
            {
                "name": "moondream2",
                "version": "vikhyatk/moondream2",
                "role": "Lightweight Local VLM — No API key",
                "detail": "~2 GB open-source vision model via HuggingFace Transformers. Works on CPU, MPS (Apple Silicon), or CUDA. Good fallback with no internet/API dependency.",
                "link": "https://github.com/vikhyatk/moondream",
            },
            {
                "name": "google-genai SDK",
                "version": "1.0+",
                "role": "Gemini API Client",
                "detail": "Official Google SDK for Gemini API calls. Replaced deprecated google-generativeai. Sends image + prompt to Gemini and parses the response.",
                "link": "https://github.com/googleapis/python-genai",
            },
        ],
    },
    {
        "icon": "📄",
        "title": "OCR Fallback",
        "diagram_ref": "Block 4",
        "description": "Runs only when VLM extraction confidence falls below the threshold (default 70%). Fills missing fields by parsing raw text patterns.",
        "category": "OCR",
        "techs": [
            {
                "name": "Tesseract OCR",
                "version": "5.x",
                "role": "OCR Engine",
                "detail": "Google's open-source OCR engine. Extracts raw text and per-word bounding boxes from images. Auto-detected at /opt/homebrew/bin on macOS.",
                "link": "https://github.com/tesseract-ocr/tesseract",
            },
            {
                "name": "pytesseract",
                "version": "0.3.13+",
                "role": "Python Wrapper",
                "detail": "Python bindings for Tesseract. Used for full-page text extraction (PSM 6) and bounding-box data for targeted image crops.",
                "link": "https://github.com/madmaze/pytesseract",
            },
        ],
    },
    {
        "icon": "🔀",
        "title": "Multi-Agent Orchestration",
        "diagram_ref": "All blocks",
        "description": "LangGraph manages the entire pipeline as a stateful graph — each agent is a node, conditional edges handle routing based on confidence scores.",
        "category": "Orchestration",
        "techs": [
            {
                "name": "LangGraph",
                "version": "0.6+",
                "role": "Agent Workflow Engine",
                "detail": "Builds the pipeline as a StateGraph where each node (ingest → extract → ocr_fallback → validate → correct → store/review) receives and returns shared state. Supports .stream() for real-time UI updates.",
                "link": "https://langchain-ai.github.io/langgraph",
            },
            {
                "name": "LangChain Core",
                "version": "0.3+",
                "role": "Base Primitives",
                "detail": "Provides runnable interface and serialisation primitives used by LangGraph internally.",
                "link": "https://python.langchain.com",
            },
            {
                "name": "Pydantic v2",
                "version": "2.13+",
                "role": "Data Schemas & Validation",
                "detail": "Defines DocumentData (flexible field dict), ValidationResult, ProcessingRecord. Field validators parse currency strings to floats and normalise date formats.",
                "link": "https://docs.pydantic.dev",
            },
        ],
    },
    {
        "icon": "✅",
        "title": "Validation Agent",
        "diagram_ref": "Block 5",
        "description": "Applies rule-based checks (totals, date formats, IBAN regex) and semantic checks (vendor name fuzzy matching) to verify extracted data.",
        "category": "Validation",
        "techs": [
            {
                "name": "rapidfuzz",
                "version": "3.13+",
                "role": "Fuzzy String Matching",
                "detail": "Matches extracted vendor names against the known vendor registry using token_sort_ratio scoring. Threshold: 80/100. Fast C++ implementation.",
                "link": "https://github.com/rapidfuzz/RapidFuzz",
            },
            {
                "name": "ChromaDB",
                "version": "1.5+",
                "role": "Vendor Vector Database",
                "detail": "Stores vendor names as semantic embeddings. Query retrieves top-k candidate matches before rapidfuzz re-ranks them. Persists to data/chroma/.",
                "link": "https://www.trychroma.com",
            },
            {
                "name": "Python re (regex)",
                "version": "stdlib",
                "role": "IBAN & Date Pattern Checks",
                "detail": "Validates IBAN format (^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$) and checks date fields are ISO 8601 (YYYY-MM-DD).",
                "link": "https://docs.python.org/3/library/re.html",
            },
        ],
    },
    {
        "icon": "💾",
        "title": "Storage & Audit Trail",
        "diagram_ref": "Block 7",
        "description": "Every document is stored with its full history — raw OCR, VLM extraction, corrections applied, validation status, and timestamped audit events.",
        "category": "Storage",
        "techs": [
            {
                "name": "SQLite",
                "version": "3.x",
                "role": "Primary Database",
                "detail": "Two tables: invoice_records (final extracted data + status) and audit_log (timestamped events per document). File stored at data/invoices.db.",
                "link": "https://sqlite.org",
            },
            {
                "name": "sqlite3",
                "version": "stdlib",
                "role": "Python DB Driver",
                "detail": "Built-in Python module. Uses Row factory for dict-like access. All writes use ON CONFLICT DO UPDATE (upsert) for idempotency.",
                "link": "https://docs.python.org/3/library/sqlite3.html",
            },
        ],
    },
    {
        "icon": "🖥️",
        "title": "Web UI",
        "diagram_ref": "Frontend",
        "description": "Full web application with login, real-time pipeline visualisation, document review workflow, history browsing, and live settings switching.",
        "category": "UI / Frontend",
        "techs": [
            {
                "name": "Streamlit",
                "version": "1.50+",
                "role": "Web Application Framework",
                "detail": "Renders the entire UI in Python. Uses session_state for routing and auth. LangGraph .stream() drives real-time pipeline stage updates via st.empty().",
                "link": "https://streamlit.io",
            },
            {
                "name": "Pandas",
                "version": "2.3+",
                "role": "Data Display & Export",
                "detail": "Powers the History and Review Queue tables. Used for CSV/JSON export of extracted records.",
                "link": "https://pandas.pydata.org",
            },
        ],
    },
    {
        "icon": "⚙️",
        "title": "Infrastructure & Config",
        "diagram_ref": "Cross-cutting",
        "description": "Project configuration, dependency management, and Colab support for team collaboration.",
        "category": "Infrastructure",
        "techs": [
            {
                "name": "Python",
                "version": "3.9+",
                "role": "Runtime",
                "detail": "All agents, pipeline, and UI are written in Python. Tested on 3.9 (local macOS) and 3.10 (Google Colab).",
                "link": "https://python.org",
            },
            {
                "name": "python-dotenv",
                "version": "1.2+",
                "role": "Configuration Management",
                "detail": "Loads API keys and settings from .env file at startup. config.py exposes an apply() function for live runtime updates without restart.",
                "link": "https://github.com/theskumar/python-dotenv",
            },
            {
                "name": "Google Colab",
                "version": "—",
                "role": "Team Development Environment",
                "detail": "doc_agent_capstone_colab.ipynb provides a self-contained notebook. Streamlit is exposed via Cloudflare Tunnel so teammates access a live URL.",
                "link": "https://colab.research.google.com",
            },
        ],
    },
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _tech_card(tech: dict, bg: str, text_col: str, accent: str) -> str:
    return f"""
    <div style="
        background:{bg};
        border:1.5px solid {accent}33;
        border-left:4px solid {accent};
        border-radius:10px;
        padding:14px 16px;
        margin:6px 0;
    ">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
            <span style="font-size:1rem;font-weight:700;color:{text_col};">{tech['name']}</span>
            <span style="
                background:{accent}22;color:{accent};
                font-size:.65rem;font-weight:600;padding:2px 7px;
                border-radius:999px;letter-spacing:.4px;
            ">{tech['version']}</span>
            <span style="margin-left:auto;font-size:.72rem;color:{text_col}aa;font-style:italic;">{tech['role']}</span>
        </div>
        <div style="font-size:.82rem;color:{text_col}cc;line-height:1.55;">{tech['detail']}</div>
    </div>"""


def _block_header(block: dict, bg: str, text_col: str, accent: str) -> str:
    return f"""
    <div style="
        background:linear-gradient(135deg,{accent}18,{accent}08);
        border:1.5px solid {accent}44;
        border-radius:12px 12px 0 0;
        padding:16px 20px 12px;
        border-bottom:2px solid {accent}55;
    ">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;">
            <span style="font-size:1.6rem;">{block['icon']}</span>
            <div>
                <div style="font-size:1.05rem;font-weight:700;color:{text_col};">{block['title']}</div>
                <div style="font-size:.72rem;color:{accent};font-weight:600;letter-spacing:.5px;
                            text-transform:uppercase;">{block['diagram_ref']}</div>
            </div>
            <span style="margin-left:auto;background:{accent};color:#fff;
                         font-size:.7rem;font-weight:700;padding:3px 10px;
                         border-radius:999px;white-space:nowrap;">
                {block['category']}
            </span>
        </div>
        <div style="font-size:.85rem;color:{text_col}bb;line-height:1.5;">{block['description']}</div>
    </div>"""


# ── Page render ───────────────────────────────────────────────────────────────

def render() -> None:
    page_header("🛠️", "Tech Stack", "Every architecture block mapped to its technology")

    # ── Summary badges ────────────────────────────────────────────────────────
    st.markdown("#### At a Glance")
    all_techs = [t["name"] for b in _BLOCKS for t in b["techs"]]
    badge_html = " ".join(
        f'<span style="display:inline-block;background:#f1f5f9;color:#334155;'
        f'border:1px solid #e2e8f0;border-radius:999px;padding:4px 12px;'
        f'font-size:.78rem;font-weight:600;margin:3px 2px;">{t}</span>'
        for t in all_techs
    )
    st.markdown(f'<div style="line-height:2.2;">{badge_html}</div>',
                unsafe_allow_html=True)

    st.markdown("<br/>", unsafe_allow_html=True)

    # ── Flow diagram summary ──────────────────────────────────────────────────
    with st.expander("📐 Pipeline Flow — which block runs in which order", expanded=False):
        st.markdown("""
```
 User uploads PDF/Image
         ↓
 [📥 Ingestion]  pdf2image · Pillow · OpenCV
         ↓
 [🔍 Extract]   Gemini / Claude / MLX / moondream  ← classifies + extracts all fields
         ↓  (if confidence < 70%)
 [📄 OCR Fallback]  Tesseract · pytesseract  ← fills missing fields
         ↓
 [✅ Validate]   rapidfuzz · ChromaDB · regex
         ↓  (if failed)
 [🔄 Correct]   VLM re-queries cropped image region  (max 2×)
         ↓
 [🔀 Route]     LangGraph conditional edge
    ├─ confidence ≥ 85%  →  [💾 Store]  SQLite
    └─ confidence < 85%  →  [👁️ Review Queue]  → human approval → SQLite
```
        """)

    st.markdown("---")

    # ── Per-block detail ──────────────────────────────────────────────────────
    for i, block in enumerate(_BLOCKS):
        cat    = block["category"]
        bg, text_col, accent = _CAT_COLORS.get(cat, ("#f9fafb", "#111827", "#6b7280"))

        # Render header
        st.markdown(_block_header(block, bg, text_col, accent), unsafe_allow_html=True)

        # Render tech cards inside a box
        cards_html = "".join(_tech_card(t, bg, text_col, accent) for t in block["techs"])
        st.markdown(
            f'<div style="'
            f'background:{bg}88;'
            f'border:1.5px solid {accent}33;'
            f'border-top:none;'
            f'border-radius:0 0 12px 12px;'
            f'padding:8px 16px 12px;'
            f'margin-bottom:20px;">'
            f'{cards_html}'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── Version table ─────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### Full Dependency Versions")

    import pandas as pd, importlib.metadata as meta

    _PKGS = [
        ("streamlit",             "UI Framework"),
        ("langgraph",             "Agent Orchestration"),
        ("langchain-core",        "LangChain Primitives"),
        ("pydantic",              "Data Validation"),
        ("google-genai",          "Gemini SDK"),
        ("anthropic",             "Claude SDK"),
        ("mlx-vlm",               "Apple MLX VLM"),
        ("Pillow",                "Image Processing"),
        ("pytesseract",           "OCR Wrapper"),
        ("pdf2image",             "PDF Conversion"),
        ("opencv-python-headless","Computer Vision"),
        ("chromadb",              "Vector Database"),
        ("rapidfuzz",             "Fuzzy Matching"),
        ("pandas",                "Data Tables"),
        ("python-dotenv",         "Config Management"),
    ]

    rows = []
    for pkg, role in _PKGS:
        try:
            ver = meta.version(pkg)
        except Exception:
            ver = "—"
        rows.append({"Package": pkg, "Version": ver, "Role": role})

    st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Package": st.column_config.TextColumn("Package", width="medium"),
            "Version": st.column_config.TextColumn("Version", width="small"),
            "Role":    st.column_config.TextColumn("Role",    width="large"),
        },
    )

    st.caption("Versions shown are what is installed in the current environment.")
