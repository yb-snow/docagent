"""Process Document page — upload, run real pipeline, display all extracted fields."""

from __future__ import annotations

import os
import json
import sys
import uuid
from pathlib import Path

import streamlit as st

from ui.styles import badge, page_header
from ui.components import pipeline_status
from ui.components.field_groups import format_line_items, format_value, group_fields, pretty_label

sys.path.insert(0, os.getcwd())

# Concurrent batch processing — Gemini free tier allows 30 req/min; capping
# workers well below that keeps typical demo-sized batches (< 10 files) safe
# without needing a dedicated rate-limiter.
_BATCH_MAX_WORKERS = 3

_DOC_TYPE_ICONS = {
    "invoice":        "🧾",
    "receipt":        "🧾",
    "bill":           "🧾",
    "purchase_order": "📦",
    "bank_statement": "🏦",
    "expense_report": "💸",
    "quote":          "💬",
    "delivery_note":  "🚚",
    "contract":       "📜",
    "form":           "📋",
    "other":          "📄",
    "unknown":        "❓",
}


def _get_user_api_keys() -> dict:
    """Decrypt and return the current user's saved API keys, keyed by provider."""
    from ui.auth import current_email
    from utils.user_keys import get_api_keys

    return get_api_keys(current_email())


def _save_upload(uploaded_file) -> tuple[str, str]:
    """Persist an uploaded file permanently under data/uploads/ and return
    (document_id, path). Documents used to be written to a tempfile and
    deleted right after processing — meaning a human reviewer could never
    actually see the source image. Keeping it lets Review Queue and History
    show it."""
    doc_id = str(uuid.uuid4())
    suffix = Path(uploaded_file.name).suffix or ".bin"
    upload_dir = Path("data/uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / f"{doc_id}{suffix}"
    path.write_bytes(uploaded_file.getvalue())
    return doc_id, str(path)


def _state_to_result(final_state: dict, skipped_nodes: set | None = None) -> dict:
    """Build the UI result dict from a finished pipeline state — shared by
    both the single-file streaming path and the concurrent batch path."""
    ext = final_state.get("extraction")
    val = final_state.get("validation")
    doc = ext.extracted_data if ext else None

    validation_details = []
    if val:
        for fv in val.field_validations:
            validation_details.append({
                "Field":   fv.field,
                "Status":  fv.status.value,
                "Message": fv.message or "",
            })

    return {
        "doc_type":              doc.doc_type         if doc else "unknown",
        "doc_subtype":           doc.doc_subtype       if doc else None,
        "fields":                doc.fields            if doc else {},
        "line_items":            doc.line_items        if doc else [],
        "extraction_notes":      doc.extraction_notes  if doc else "",
        "extraction_confidence": ext.confidence        if ext else 0.0,
        "confidence_breakdown": {
            "vlm_confidence":       ext.vlm_confidence,
            "field_coverage_score": ext.field_coverage_score,
        } if ext else None,
        "ocr_used":              ext.ocr_used          if ext else False,
        "validation_status":     final_state["final_status"].value
                                 if final_state.get("final_status") else "unknown",
        "corrections":           final_state.get("correction_attempts", 0),
        "validation_details":    validation_details,
        "document_id":           final_state.get("document_id", ""),
        "source_path":           final_state.get("source_path", ""),
        "processing_notes":      final_state.get("processing_notes", []),
        "skipped_nodes":         skipped_nodes or set(),
    }


def _run_pipeline(uploaded_file, placeholder) -> dict:
    """Run the real LangGraph pipeline and update the stepper after EACH node completes."""
    from graph.workflow import process_document_stream
    from ui.components.pipeline_status import render_progress

    doc_id, saved_path = _save_upload(uploaded_file)

    completed_nodes: set = set()
    final_state           = None
    skipped_nodes:  set = set()

    # Node display labels for the status caption
    _labels = {
        "ingest":       "📥 Ingesting document…",
        "extract":      "🔍 Classifying and extracting fields with AI…",
        "ocr_fallback": "📄 Running OCR fallback (low confidence detected)…",
        "validate":     "✅ Validating extracted data…",
        "correct":      "🔄 Auto-correcting failed fields…",
        "store":        "💾 Saving to database…",
        "review_queue": "👁️ Routing to human review queue…",
    }

    for node_name, state in process_document_stream(
        saved_path, document_id=doc_id, api_keys=_get_user_api_keys(),
    ):
        # Mark this node as done
        completed_nodes.add(node_name)
        final_state = state

        # Detect skipped OCR (if we jump straight from extract to validate)
        if node_name == "validate" and "ocr_fallback" not in completed_nodes:
            skipped_nodes.add("ocr_fallback")

        # Render the stepper with REAL progress
        with placeholder.container():
            render_progress(completed_nodes, skipped_nodes=skipped_nodes)
            label = _labels.get(node_name, f"Running {node_name}…")
            notes = state.get("processing_notes") or []
            last_note = notes[-1] if notes else ""
            st.caption(f"✓ {label}  " + (f"· _{last_note}_" if last_note else ""))

    if final_state is None:
        raise RuntimeError("Pipeline produced no output.")

    return _state_to_result(final_state, skipped_nodes)


def _run_batch_concurrent(uploaded_files) -> None:
    """Process multiple documents concurrently. VLM calls are I/O-bound
    (network requests), so a thread pool gives a real wall-clock speedup for
    batch uploads — safe here because worker threads only run the pipeline
    (each opens its own SQLite connection), never touch Streamlit widgets."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from graph.workflow import process_document

    jobs     = [(f.name, *_save_upload(f)) for f in uploaded_files]
    api_keys = _get_user_api_keys()   # same signed-in user for the whole batch

    progress = st.progress(0.0, text=f"Processing 0 / {len(jobs)}…")
    results: dict[str, dict] = {}
    errors:  dict[str, str]  = {}

    with ThreadPoolExecutor(max_workers=min(_BATCH_MAX_WORKERS, len(jobs))) as executor:
        future_to_name = {
            executor.submit(process_document, path, doc_id, api_keys): name
            for name, doc_id, path in jobs
        }
        done = 0
        for future in as_completed(future_to_name):
            name = future_to_name[future]
            done += 1
            try:
                results[name] = _state_to_result(future.result())
            except Exception as e:
                errors[name] = str(e)
            progress.progress(done / len(jobs), text=f"Processed {done} / {len(jobs)}…")

    progress.empty()

    for name, doc_id, _path in jobs:
        st.subheader(f"Processing: {name}")
        if name in errors:
            _handle_processing_error(name, errors[name], fallback_document_id=doc_id, source_path=_path)
            continue

        result = results[name]
        status = result["validation_status"]
        if status in ("valid", "corrected"):
            st.success(f"{name} processed successfully.")
        elif status == "pending_review":
            st.warning(f"{name} sent to Review Queue.")
        else:
            st.error(f"{name} processing failed.")
        _show_results(result)


def _handle_processing_error(filename: str, err: str, fallback_document_id: str, source_path: str) -> None:
    """Shared error-handling for both the single-file and batch paths."""
    if "429" in err or "RESOURCE_EXHAUSTED" in err:
        st.error(f"{filename}: Gemini quota exceeded.")
        return
    if "poppler" in err.lower() or "page count" in err.lower():
        st.error(f"{filename}: Poppler not found.")
        return
    if "tesseract" in err.lower():
        st.error(f"{filename}: Tesseract not found.")
        return

    # Other pipeline errors — save what we have to the review queue rather
    # than silently losing the document.
    try:
        from database.storage import save_record
        from models.schemas import ProcessingRecord, ValidationStatus

        save_record(ProcessingRecord(
            document_id=fallback_document_id,
            source_path=source_path,
            doc_type="unknown",
            raw_ocr_text="",
            vlm_extraction={},
            corrections_applied=[],
            final_data={},
            validation_status=ValidationStatus.PENDING,
            extraction_confidence=0.0,
            processing_notes=[
                f"Pipeline failed: {err}",
                "Automatically moved to Review Queue.",
            ],
        ))
        st.warning(f"{filename} could not be processed and has been moved to Review Queue.")
    except Exception as inner_e:
        st.error(f"Error saving failed record for {filename}: {inner_e}")
        st.error(f"{filename} processing failed with error: {err}")


def _show_source_preview(source_path: str) -> None:
    if not source_path:
        return
    try:
        from pipeline.ingestion import get_preview_image
        img = get_preview_image(source_path)
    except Exception:
        img = None
    if img is not None:
        with st.expander("🖼️ View source document", expanded=False):
            st.markdown('<div class="doc-preview">', unsafe_allow_html=True)
            st.image(img, use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)


def _show_results(result: dict) -> None:
    st.markdown("<br/>", unsafe_allow_html=True)

    doc_type = result["doc_type"]
    icon     = _DOC_TYPE_ICONS.get(doc_type, "📄")
    subtype  = f" · {result['doc_subtype']}" if result.get("doc_subtype") else ""
    status   = result["validation_status"]
    conf     = result["extraction_confidence"]
    ocr_note = "OCR fallback used" if result["ocr_used"] else "OCR skipped (high confidence)"

    # ── Summary banner ────────────────────────────────────────────────────────
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Document Type",   f"{icon} {doc_type.replace('_',' ').title()}{subtype}")
        c2.metric("Confidence",      f"{conf*100:.0f}%")
        c3.metric("Fields Found",    len(result["fields"]))
        c4.metric("Status",          status.replace("_"," ").title())

        breakdown = result.get("confidence_breakdown")
        if breakdown and breakdown.get("vlm_confidence") is not None:
            st.caption(
                f"🧮 Confidence = {breakdown['vlm_confidence']*100:.0f}% VLM self-report × 0.7 "
                f"+ {breakdown['field_coverage_score']*100:.0f}% field coverage × 0.3"
            )

    _show_source_preview(result.get("source_path", ""))

    if result.get("extraction_notes"):
        st.info(f"**AI summary:** {result['extraction_notes']}")

    # ── Tabs ──────────────────────────────────────────────────────────────────
    tab_fields, tab_items, tab_validation, tab_log, tab_export = st.tabs([
        "📋 Extracted Fields",
        f"🗒️ Line Items ({len(result['line_items'])})",
        "✅ Validation",
        "📜 Pipeline Log",
        "⬇️ Export",
    ])

    # ── Fields tab: grouped display ───────────────────────────────────────────
    with tab_fields:
        currency = str(result["fields"].get("currency") or "")
        groups   = group_fields(result["fields"])

        if not groups:
            st.warning("No fields were extracted. Try a clearer image.")
        else:
            for group_label, group_fields_dict in groups.items():
                st.markdown(f"**{group_label}**")
                cols = st.columns(2)
                for i, (key, val) in enumerate(group_fields_dict.items()):
                    cols[i % 2].text_input(
                        pretty_label(key),
                        value=format_value(key, val, currency),
                        disabled=True,
                        key=f"field_{result['document_id']}_{key}",
                    )
                st.markdown("<hr style='margin:8px 0;border-color:#e2e8f0'/>",
                            unsafe_allow_html=True)

    # ── Line items tab ────────────────────────────────────────────────────────
    with tab_items:
        items = result.get("line_items") or []
        if items:
            import pandas as pd
            df = pd.DataFrame(format_line_items(items, currency))
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.caption(f"{len(items)} line item(s) extracted")
        else:
            st.info("No line items / table data found in this document.")

    # ── Validation tab ────────────────────────────────────────────────────────
    with tab_validation:
        b = badge(status, status)
        st.markdown(
            f"""
            **Status:** {b} &nbsp;&nbsp;
            **Corrections applied:** {result['corrections']} &nbsp;&nbsp;
            {ocr_note}
            """,
            unsafe_allow_html=True,
        )
        if result["validation_details"]:
            import pandas as pd
            st.dataframe(
                pd.DataFrame(result["validation_details"]),
                use_container_width=True, hide_index=True,
            )

    # ── Log tab ───────────────────────────────────────────────────────────────
    with tab_log:
        for note in result.get("processing_notes", []):
            st.markdown(f"- {note}")

    # ── Export tab ────────────────────────────────────────────────────────────
    with tab_export:
        import pandas as pd

        export_data = {
            "doc_type":   result["doc_type"],
            "doc_subtype":result.get("doc_subtype"),
            **result["fields"],
        }
        c1, c2 = st.columns(2)
        with c1:
            st.download_button(
                "⬇️ Download JSON",
                data=json.dumps(export_data, indent=2, default=str),
                file_name=f"extracted_{result['document_id'][:8]}.json",
                mime="application/json",
                use_container_width=True,
                key=f"proc_dl_json_{result['document_id']}",
            )
        with c2:
            flat = {k: v for k, v in export_data.items() if not isinstance(v, list)}
            st.download_button(
                "⬇️ Download CSV",
                data=pd.DataFrame([flat]).to_csv(index=False),
                file_name=f"extracted_{result['document_id'][:8]}.csv",
                mime="text/csv",
                use_container_width=True,
                key=f"proc_dl_csv_{result['document_id']}",
            )
        if result["line_items"]:
            st.download_button(
                "⬇️ Line Items CSV",
                data=pd.DataFrame(result["line_items"]).to_csv(index=False),
                file_name=f"line_items_{result['document_id'][:8]}.csv",
                mime="text/csv",
                use_container_width=True,
                key=f"proc_dl_items_{result['document_id']}",
            )


def render() -> None:
    page_header("🔄🤖", "Process Document",
                "Upload any invoice, receipt, form, or document — AI auto-detects type and extracts all fields")

    if "process_result"  not in st.session_state:
        st.session_state.process_result  = None

    import config
    if config.VLM_BACKEND in ("gemini", "claude") and not _get_user_api_keys().get(config.VLM_BACKEND):
        st.warning(
            f"⚠️ No {config.VLM_BACKEND.title()} API key configured for your account yet. "
            f"Add your own key in **Settings → VLM Backend** before processing documents."
        )

    uploaded_files = st.file_uploader(
        "Drop files here or click to browse",
        type=["pdf", "png", "jpg", "jpeg", "tiff", "bmp"],
        help="Supported: PDF, PNG, JPG, TIFF, BMP  ·  Max 200 MB",
        key="doc_upload",
        accept_multiple_files=True,
    )

    if uploaded_files:
        st.markdown(f"### Selected Files ({len(uploaded_files)})")

        for f in uploaded_files:
            st.write(f"• {f.name} ({f.size // 1024} KB)")

        if len(uploaded_files) > 1:
            st.caption(
                f"⚡ Batch mode: up to {_BATCH_MAX_WORKERS} documents will process concurrently."
            )

        run = st.button(
            "▶ Run Pipeline",
            type="primary",
            use_container_width=True,
        )

        if run:
            if len(uploaded_files) > 1:
                with st.spinner(f"Processing {len(uploaded_files)} documents…"):
                    _run_batch_concurrent(uploaded_files)
            else:
                f = uploaded_files[0]
                st.subheader(f"Processing: {f.name}")
                placeholder = st.empty()

                with st.spinner(f"Processing {f.name}..."):
                    try:
                        st.session_state.process_result = _run_pipeline(f, placeholder)

                        status = st.session_state.process_result["validation_status"]

                        if status in ("valid", "corrected"):
                            st.success(f"{f.name} processed successfully.")
                        elif status == "pending_review":
                            st.warning(f"{f.name} sent to Review Queue.")
                        else:
                            st.error(f"{f.name} processing failed.")

                    except Exception as e:
                        _handle_processing_error(
                            f.name, str(e),
                            fallback_document_id=str(uuid.uuid4()),
                            source_path=f.name,
                        )

                placeholder.empty()

    elif st.session_state.process_result is None:
        st.markdown("<br/>", unsafe_allow_html=True)
        with st.container(border=True):
            pipeline_status.render()
            st.caption("Pipeline ready — upload any document to begin.")

    # Show the last processed document (single-file uploads only — batch
    # results are already rendered inline by _run_batch_concurrent above).
    if (
        st.session_state.process_result is not None
        and (not uploaded_files or len(uploaded_files) == 1)
    ):
        pipeline_status.render()

        status = st.session_state.process_result["validation_status"]

        if status in ("valid", "corrected"):
            st.success("Document processed successfully.")
        elif status == "pending_review":
            st.warning(
                "Document sent to Review Queue — confidence below auto-approve threshold."
            )
        else:
            st.error("Processing completed with errors.")

        _show_results(st.session_state.process_result)
