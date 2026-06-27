"""Settings page — live VLM backend switching with connection testing."""

from __future__ import annotations

import os
import sys

import streamlit as st

sys.path.insert(0, os.getcwd())

import config
from ui.styles import page_header


# ── Connection testers ────────────────────────────────────────────────────────

def _test_gemini(api_key: str, model: str) -> tuple[bool, str]:
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=api_key)
        client.models.generate_content(
            model=model,
            contents="Reply with: OK",
            config=types.GenerateContentConfig(max_output_tokens=5, temperature=0.0),
        )
        return True, "Connection successful"
    except Exception as e:
        err = str(e)
        if "429" in err or "RESOURCE_EXHAUSTED" in err:
            return False, "Rate limit reached — wait 60 seconds, then try again"
        if "401" in err or "403" in err or "API_KEY" in err.upper():
            return False, "Invalid API key — check your key at aistudio.google.com"
        if "404" in err or "NOT_FOUND" in err:
            return False, f"Model '{model}' not available for this key — try gemini-flash-latest"
        return False, str(e)[:120]


def _test_claude(api_key: str, model: str) -> tuple[bool, str]:
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        client.messages.create(
            model=model, max_tokens=5,
            messages=[{"role": "user", "content": "Say OK"}],
        )
        return True, "Connection successful"
    except Exception as e:
        err = str(e)
        if "401" in err or "invalid_api_key" in err.lower():
            return False, "Invalid Anthropic API key"
        if "permission" in err.lower():
            return False, "This key does not have access to that model"
        return False, str(e)[:120]


# ── Page ──────────────────────────────────────────────────────────────────────

def render() -> None:
    page_header("⚙️", "Settings", "Configure VLM backend, thresholds, and vendors")

    tab_vlm, tab_thresholds, tab_vendors, tab_about = st.tabs(
        ["🤖 VLM Backend", "🎚️ Thresholds", "🏢 Vendors", "ℹ️ About"]
    )

    # ── VLM Backend tab ───────────────────────────────────────────────────────
    with tab_vlm:

        active       = config.VLM_BACKEND
        active_color = {"gemini": "#16a34a", "claude": "#7c3aed"}.get(active, "#374151")
        st.markdown(
            f"**Currently active:** "
            f"<span style='color:{active_color};font-weight:700;font-size:1rem'>"
            f"{'🟢' if active == 'gemini' else '🟣' if active == 'claude' else '⚪'} "
            f"{active.upper()}</span>",
            unsafe_allow_html=True,
        )
        st.markdown("<br/>", unsafe_allow_html=True)

        backend_options = {
            "gemini":    "🟢 Google Gemini  (FREE — API key required)",
            "claude":    "🟣 Anthropic Claude  (paid API key required)",
            "mlx":       "🍎 Local MLX  (Apple M-chip, no API key, downloads model)",
            "moondream": "🤗 Local moondream2  (tiny ~2 GB, any hardware, no API key)",
        }
        selected_key = st.radio(
            "Select VLM Backend",
            list(backend_options.keys()),
            format_func=lambda k: backend_options[k],
            index=list(backend_options.keys()).index(active) if active in backend_options else 0,
        )

        st.divider()

        # ── Gemini ─────────────────────────────────────────────────────────────
        if selected_key == "gemini":
            st.markdown("#### Google Gemini Configuration")
            st.info(
                "**Get a free key:** [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) "
                "— no credit card required  \n"
                "**Free tier limits:** 30 requests/min · 1,500 requests/day  \n"
                "**Hit a rate limit?** Wait 60 seconds and retry, or switch to Claude below."
            )

            gemini_key = st.text_input(
                "Gemini API Key", value=config.GEMINI_API_KEY,
                type="password", placeholder="AIza…",
            )

            all_gemini_models = [
                "gemini-flash-latest",
                "gemini-2.5-flash",
                "gemini-2.0-flash",
                "gemini-2.0-flash-lite",
                "gemini-2.5-pro",
            ]
            current_gmodel = config.GEMINI_MODEL
            if current_gmodel not in all_gemini_models:
                all_gemini_models.insert(0, current_gmodel)

            gemini_model = st.selectbox(
                "Gemini Model",
                all_gemini_models,
                index=all_gemini_models.index(current_gmodel),
            )

            c1, c2 = st.columns(2)
            with c1:
                if st.button("🔌 Test Connection", use_container_width=True,
                             key="test_gemini"):
                    if not gemini_key:
                        st.warning("Enter an API key first.")
                    else:
                        with st.spinner("Testing…"):
                            ok, msg = _test_gemini(gemini_key, gemini_model)
                        (st.success if ok else st.error)(f"{'✅' if ok else '❌'} {msg}")

            with c2:
                if st.button("💾 Save & Apply", type="primary",
                             use_container_width=True, key="save_gemini"):
                    if not gemini_key:
                        st.warning("Enter an API key before saving.")
                    else:
                        config.apply({
                            "VLM_BACKEND":    "gemini",
                            "GEMINI_API_KEY": gemini_key,
                            "GEMINI_MODEL":   gemini_model,
                        })
                        st.success(
                            f"✅ Backend switched to **Gemini** (`{gemini_model}`) "
                            f"— active immediately, no restart needed."
                        )
                        st.rerun()

        # ── Claude ─────────────────────────────────────────────────────────────
        elif selected_key == "claude":
            st.markdown("#### Anthropic Claude Configuration")
            st.info(
                "Get your key at [console.anthropic.com](https://console.anthropic.com).  \n"
                "Claude Sonnet is the best model for document vision tasks."
            )

            claude_key = st.text_input(
                "Anthropic API Key", value=config.ANTHROPIC_API_KEY,
                type="password", placeholder="sk-ant-…",
            )

            claude_models = [
                "claude-sonnet-4-6",
                "claude-opus-4-7",
                "claude-haiku-4-5-20251001",
            ]
            current_cmodel = config.CLAUDE_MODEL
            if current_cmodel not in claude_models:
                claude_models.insert(0, current_cmodel)

            claude_model = st.selectbox(
                "Claude Model",
                claude_models,
                index=claude_models.index(current_cmodel) if current_cmodel in claude_models else 0,
            )

            c1, c2 = st.columns(2)
            with c1:
                if st.button("🔌 Test Connection", use_container_width=True,
                             key="test_claude"):
                    if not claude_key:
                        st.warning("Enter an API key first.")
                    else:
                        with st.spinner("Testing…"):
                            ok, msg = _test_claude(claude_key, claude_model)
                        (st.success if ok else st.error)(f"{'✅' if ok else '❌'} {msg}")

            with c2:
                if st.button("💾 Save & Apply", type="primary",
                             use_container_width=True, key="save_claude"):
                    if not claude_key:
                        st.warning("Enter an API key before saving.")
                    else:
                        config.apply({
                            "VLM_BACKEND":       "claude",
                            "ANTHROPIC_API_KEY": claude_key,
                            "CLAUDE_MODEL":      claude_model,
                        })
                        st.success(
                            f"✅ Backend switched to **Claude** (`{claude_model}`) "
                            f"— active immediately, no restart needed."
                        )
                        st.rerun()

        # ── Apple MLX ──────────────────────────────────────────────────────────
        elif selected_key == "mlx":
            st.markdown("#### 🍎 Apple MLX — Local Model (No API Key)")
            st.success(
                "**Best option for Apple M1/M2/M3/M4 chips.**  \n"
                "Models download from HuggingFace on first use (~4–6 GB) and run entirely on your Mac.  \n"
                "No internet required after download. No API key. No rate limits."
            )

            mlx_models = {
                "mlx-community/llava-1.5-7b-4bit":             "LLaVA-1.5 7B  (4-bit, ~4 GB) — Good quality, fast",
                "mlx-community/phi-3.5-vision-instruct-4bit":  "Phi-3.5 Vision  (4-bit, ~6 GB) — Excellent quality",
                "mlx-community/llava-1.5-13b-4bit":            "LLaVA-1.5 13B  (4-bit, ~8 GB) — Best quality",
            }
            current_local = config.LOCAL_VLM_MODEL
            mlx_model = st.selectbox(
                "Model  (downloads on first use)",
                list(mlx_models.keys()),
                format_func=lambda k: mlx_models[k],
                index=list(mlx_models.keys()).index(current_local)
                      if current_local in mlx_models else 0,
            )

            st.info(
                f"**Your hardware:** Apple M3 Pro · 18 GB unified memory  \n"
                f"**Estimated first download:** ~4–6 GB  \n"
                f"**Subsequent runs:** model is cached locally — instant start"
            )

            if st.button("💾 Save & Apply", type="primary",
                         use_container_width=True, key="save_mlx"):
                config.apply({
                    "VLM_BACKEND":     "mlx",
                    "LOCAL_VLM_MODEL": mlx_model,
                })
                st.success(
                    f"✅ Backend set to **MLX** (`{mlx_model}`)  \n"
                    f"Model will download on first document upload."
                )
                st.rerun()

        # ── moondream2 ──────────────────────────────────────────────────────────
        elif selected_key == "moondream":
            st.markdown("#### 🤗 moondream2 — Lightweight Local Model (No API Key)")
            st.success(
                "**Tiny ~2 GB model — works on any hardware including CPU.**  \n"
                "Downloads once from HuggingFace, then runs entirely offline.  \n"
                "Lower accuracy than Gemini or LLaVA but completely free and private."
            )
            st.info(
                "**Your hardware:** Apple M3 Pro · MPS available — will be fast  \n"
                "**Model:** `vikhyatk/moondream2` (~2 GB download)"
            )

            if st.button("💾 Save & Apply", type="primary",
                         use_container_width=True, key="save_moondream"):
                config.apply({
                    "VLM_BACKEND":     "moondream",
                    "LOCAL_VLM_MODEL": "vikhyatk/moondream2",
                })
                st.success(
                    "✅ Backend set to **moondream2**  \n"
                    "Model will download on first document upload (~2 GB)."
                )
                st.rerun()

    # ── Thresholds tab ────────────────────────────────────────────────────────
    with tab_thresholds:

        # ── Human Review Threshold (primary user-facing control) ──────────────
        st.markdown("### 👁️ Human Review Threshold")
        st.markdown(
            "Documents with an extraction confidence **below** this value are flagged "
            "and sent to the **Review Queue** for a human to verify before they are stored."
        )

        review_pct = st.slider(
            "Send to Human Review if confidence is below",
            min_value=0,
            max_value=100,
            value=int(float(config.AUTO_APPROVE_THRESHOLD) * 100),
            step=5,
            format="%d%%",
            key="thresh_review",
            help="Drag left to auto-approve more documents; drag right to review more.",
        )
        app_t = review_pct / 100.0

        # ── Visual band ───────────────────────────────────────────────────────
        ext_pct = int(float(config.EXTRACTION_CONF_THRESHOLD) * 100)
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.markdown(
                f"""<div style="background:#fee2e2;border-radius:8px;padding:12px 16px;text-align:center">
                    <div style="font-size:.75rem;color:#7f1d1d;font-weight:600;text-transform:uppercase;
                                letter-spacing:.6px">OCR Fallback zone</div>
                    <div style="font-size:1.4rem;font-weight:700;color:#dc2626">0 – {ext_pct}%</div>
                    <div style="font-size:.75rem;color:#7f1d1d">OCR supplements VLM</div>
                </div>""",
                unsafe_allow_html=True,
            )
        with col_b:
            st.markdown(
                f"""<div style="background:#fef3c7;border-radius:8px;padding:12px 16px;text-align:center">
                    <div style="font-size:.75rem;color:#78350f;font-weight:600;text-transform:uppercase;
                                letter-spacing:.6px">Human Review zone</div>
                    <div style="font-size:1.4rem;font-weight:700;color:#d97706">{ext_pct} – {review_pct}%</div>
                    <div style="font-size:.75rem;color:#78350f">Sent to Review Queue</div>
                </div>""",
                unsafe_allow_html=True,
            )
        with col_c:
            st.markdown(
                f"""<div style="background:#dcfce7;border-radius:8px;padding:12px 16px;text-align:center">
                    <div style="font-size:.75rem;color:#14532d;font-weight:600;text-transform:uppercase;
                                letter-spacing:.6px">Auto-approve zone</div>
                    <div style="font-size:1.4rem;font-weight:700;color:#16a34a">{review_pct} – 100%</div>
                    <div style="font-size:.75rem;color:#14532d">Stored automatically</div>
                </div>""",
                unsafe_allow_html=True,
            )

        st.markdown("<br/>", unsafe_allow_html=True)

        # ── OCR fallback threshold ────────────────────────────────────────────
        with st.expander("⚙️ Advanced — OCR & Validation Settings", expanded=False):
            st.markdown(
                "**OCR Fallback Threshold** — if extraction confidence is below this, "
                "Tesseract OCR runs to fill any gaps the VLM missed."
            )
            ext_t = st.slider(
                "OCR Fallback Threshold",
                min_value=0, max_value=100,
                value=ext_pct, step=5, format="%d%%",
                key="thresh_ocr",
                help="Keep this below the Human Review threshold.",
            )
            ext_t = ext_t / 100.0

            st.markdown("---")
            st.markdown("**Validation Rules**")
            tol  = st.number_input(
                "Total Reconciliation Tolerance ($)",
                0.0, 1.0, float(config.TOTAL_TOLERANCE), 0.01,
                format="%.2f", key="thresh_tol",
                help="Max allowed difference between (subtotal + tax) and total_amount.",
            )
            fuzz = st.slider(
                "Vendor Fuzzy Match Threshold (0–100)",
                0, 100, int(config.FUZZY_VENDOR_THRESHOLD),
                key="thresh_fuzz",
                help="Minimum similarity score to consider a vendor name a known match.",
            )
            corr = st.number_input(
                "Max Auto-Correction Attempts",
                1, 5, int(config.MAX_CORRECTION_ATTEMPTS),
                key="thresh_corr",
                help="How many times the pipeline re-queries the VLM to fix failed fields.",
            )
        if st.button("💾 Save Thresholds", type="primary", key="save_thresholds"):
            if ext_t >= app_t:
                st.error(
                    "OCR Fallback Threshold must be **lower** than the Human Review Threshold. "
                    f"Currently: OCR={ext_t:.0%} ≥ Review={app_t:.0%}"
                )
            else:
                config.apply({
                    "EXTRACTION_CONF_THRESHOLD": ext_t,
                    "AUTO_APPROVE_THRESHOLD":    app_t,
                    "TOTAL_TOLERANCE":           tol,
                    "FUZZY_VENDOR_THRESHOLD":    fuzz,
                    "MAX_CORRECTION_ATTEMPTS":   corr,
                })
                st.success(
                    f"✅ Saved — documents below **{review_pct}%** confidence will go to Review Queue."
                )

    # ── Vendors tab ───────────────────────────────────────────────────────────
    with tab_vendors:
        st.markdown("#### Known Vendor Registry (ChromaDB)")
        vendors_file = "data/vendors.txt"
        existing = open(vendors_file).read() if os.path.exists(vendors_file) else ""
        vendor_text = st.text_area("Known Vendors (one per line)", value=existing, height=200)

        if st.button("➕ Save Vendor List", type="primary"):
            try:
                os.makedirs("data", exist_ok=True)
                with open(vendors_file, "w") as f:
                    f.write(vendor_text)
                from utils.vendor_matcher import VendorMatcher
                added = VendorMatcher().add_vendors(
                    [v.strip() for v in vendor_text.splitlines() if v.strip()]
                )
                st.success(f"✅ Saved — {added} new vendor(s) added to ChromaDB.")
            except Exception as e:
                st.error(f"Error: {e}")

    # ── About tab ─────────────────────────────────────────────────────────────
    with tab_about:
        st.markdown("#### System Status")
        rows = [
            ("VLM Backend",   config.VLM_BACKEND.upper()),
            ("Gemini Model",  config.GEMINI_MODEL),
            ("Claude Model",  config.CLAUDE_MODEL),
            ("OCR Engine",    "Tesseract 5"),
            ("Storage",       config.SQLITE_PATH),
            ("Vector DB",     config.CHROMA_PERSIST_DIR),
            ("Orchestration", "LangGraph"),
            ("App Version",   "1.0.0"),
        ]
        for label, value in rows:
            c1, c2 = st.columns([1, 2])
            c1.markdown(f"**{label}**")
            c2.markdown(f"`{value}`")
