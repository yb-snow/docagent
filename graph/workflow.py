"""LangGraph multi-agent workflow — classify + extract in one VLM call."""

from __future__ import annotations

import time
import uuid
from typing import Optional, TypedDict

from langgraph.graph import END, StateGraph
from PIL import Image

from agents import correction_agent, extraction_agent, validation_agent
import config   # read at call-time so Settings changes take effect immediately
from database import storage
from models.schemas import ExtractionResult, ProcessingRecord, ValidationResult, ValidationStatus
from pipeline import ingestion, ocr


# ── State ─────────────────────────────────────────────────────────────────────

class InvoiceState(TypedDict):
    document_id:          str
    source_path:          str
    images:               list
    ocr_texts:            list
    extraction:           Optional[ExtractionResult]
    validation:           Optional[ValidationResult]
    correction_attempts:  int
    final_status:         Optional[ValidationStatus]
    processing_notes:     list
    timings:              dict      # {node_name: seconds}
    pipeline_start:       float    # epoch time when pipeline started


# ── Timing helper ─────────────────────────────────────────────────────────────

def _timed(state: InvoiceState, node: str, start: float) -> float:
    """Record elapsed time for a node and return it."""
    elapsed = round(time.time() - start, 2)
    state["timings"][node] = elapsed
    return elapsed


# ── Nodes ─────────────────────────────────────────────────────────────────────

def node_ingest(state: InvoiceState) -> InvoiceState:
    t0     = time.time()
    images = ingestion.load_document(state["source_path"])
    state["images"] = images
    elapsed = _timed(state, "ingest", t0)
    state["processing_notes"].append(
        f"📥 Ingested {len(images)} page(s) · ⏱ {elapsed}s"
    )
    storage.log_event(state["document_id"], "ingested",
                      {"pages": len(images), "latency_s": elapsed})
    return state


def node_extract(state: InvoiceState) -> InvoiceState:
    """Combined classify + extract — one VLM call identifies type and reads all fields."""
    t0           = time.time()
    combined_ocr = "\n\n".join(state.get("ocr_texts") or [])
    result       = extraction_agent.run(state["images"], combined_ocr)
    state["extraction"] = result
    elapsed = _timed(state, "extract", t0)

    doc = result.extracted_data
    sub = f" · subtype: {doc.doc_subtype}" if doc.doc_subtype else ""
    state["processing_notes"].append(
        f"🔍 Classified as '{doc.doc_type}'{sub} · "
        f"{len(doc.fields)} fields extracted · "
        f"confidence {result.confidence:.0%} · ⏱ {elapsed}s"
    )
    storage.log_event(state["document_id"], "extracted", {
        "doc_type":    doc.doc_type,
        "field_count": len(doc.fields),
        "confidence":  result.confidence,
        "latency_s":   elapsed,
    })
    return state


def node_ocr_fallback(state: InvoiceState) -> InvoiceState:
    """Run Tesseract and merge output to fill gaps from VLM extraction."""
    t0       = time.time()
    texts    = [ocr.ocr_extract_text(img) for img in state["images"]]
    combined = "\n\n".join(texts)
    state["ocr_texts"] = texts

    if state["extraction"]:
        merged = ocr.merge_ocr_with_extraction(combined, state["extraction"].extracted_data)
        state["extraction"] = ExtractionResult(
            raw_ocr_text=combined,
            extracted_data=merged,
            confidence=state["extraction"].confidence,
            vlm_response=state["extraction"].vlm_response,
            ocr_used=True,
        )
    elapsed = _timed(state, "ocr_fallback", t0)
    state["processing_notes"].append(
        f"📄 OCR fallback ran — merged with VLM output · ⏱ {elapsed}s"
    )
    storage.log_event(state["document_id"], "ocr_fallback",
                      {"chars": len(combined), "latency_s": elapsed})
    return state


def node_validate(state: InvoiceState) -> InvoiceState:
    t0     = time.time()
    result = validation_agent.run(state["extraction"])
    state["validation"] = result
    elapsed = _timed(state, "validate", t0)

    msg = "Validation passed" if result.is_valid else f"Validation failed: {result.failed_fields}"
    state["processing_notes"].append(f"✅ {msg} · ⏱ {elapsed}s")
    storage.log_event(state["document_id"], "validated", {
        "valid":      result.is_valid,
        "failed":     result.failed_fields,
        "latency_s":  elapsed,
    })
    return state


def node_correct(state: InvoiceState) -> InvoiceState:
    t0 = time.time()
    state["correction_attempts"] += 1
    updated = correction_agent.run(
        state["images"],
        state["extraction"],
        state["validation"],
    )
    state["extraction"] = updated
    elapsed = _timed(state, f"correct_{state['correction_attempts']}", t0)
    state["processing_notes"].append(
        f"🔄 Auto-correction attempt {state['correction_attempts']} · ⏱ {elapsed}s"
    )
    storage.log_event(state["document_id"], "corrected",
                      {"attempt": state["correction_attempts"], "latency_s": elapsed})
    return state


def _save(state: InvoiceState, status: ValidationStatus) -> None:
    """Shared save logic for store and review_queue nodes."""
    v   = state["validation"]
    ext = state["extraction"]

    # Total pipeline time
    total = round(time.time() - state["pipeline_start"], 2)
    state["timings"]["total"] = total
    state["processing_notes"].append(f"⏱ Total pipeline time: {total}s")

    try:
      storage.save_record(ProcessingRecord(
        document_id=state["document_id"],
        source_path=state["source_path"],
        doc_type=ext.extracted_data.doc_type if ext else "unknown",
        raw_ocr_text="\n\n".join(state.get("ocr_texts") or []),
        vlm_extraction={
            "fields":     ext.extracted_data.fields,
            "line_items": ext.extracted_data.line_items,
            "timings":    state["timings"],
        } if ext else {},
        corrections_applied=[
            fv.model_dump() for fv in (v.field_validations if v else [])
            if fv.status == ValidationStatus.CORRECTED
        ],
        final_data={
            "doc_type":         ext.extracted_data.doc_type,
            "doc_subtype":      ext.extracted_data.doc_subtype,
            "fields":           ext.extracted_data.fields,
            "line_items":       ext.extracted_data.line_items,
            "extraction_notes": ext.extracted_data.extraction_notes,
            "timings":          state["timings"],
        } if ext else {},
        validation_status=status,
        extraction_confidence=ext.confidence if ext else 0.0,
        processing_notes=state["processing_notes"],
      ))
    except Exception as e:
        print(f"[workflow] ERROR: could not save record {state['document_id']}: {e}")
        raise   # re-raise so the pipeline surface the failure visibly


def node_store(state: InvoiceState) -> InvoiceState:
    v      = state["validation"]
    status = ValidationStatus.VALID if (v and v.is_valid) else ValidationStatus.CORRECTED
    state["final_status"] = status
    _save(state, status)
    storage.log_event(state["document_id"], "stored",
                      {"status": status.value, "total_s": state["timings"].get("total")})
    return state


def node_review_queue(state: InvoiceState) -> InvoiceState:
    state["final_status"] = ValidationStatus.PENDING
    state["processing_notes"].append("Sent to human review queue")
    _save(state, ValidationStatus.PENDING)
    storage.log_event(state["document_id"], "review_queue",
                      {"reason": "low confidence or max corrections",
                       "total_s": state["timings"].get("total")})
    return state


# ── Routers ───────────────────────────────────────────────────────────────────

def _should_run_ocr(state: InvoiceState) -> str:
    conf = state["extraction"].confidence if state["extraction"] else 0.0
    return "ocr_fallback" if conf < config.EXTRACTION_CONF_THRESHOLD else "validate"


def _route_after_validation(state: InvoiceState) -> str:
    v    = state["validation"]
    conf = state["extraction"].confidence if state["extraction"] else 0.0

    if v and not v.is_valid:
        if state["correction_attempts"] < config.MAX_CORRECTION_ATTEMPTS:
            return "correct"
        return "review_queue"

    return "store" if conf >= config.AUTO_APPROVE_THRESHOLD else "review_queue"


# ── Build & run ───────────────────────────────────────────────────────────────

def build_graph():
    storage.init_db()
    g = StateGraph(InvoiceState)

    g.add_node("ingest",       node_ingest)
    g.add_node("extract",      node_extract)
    g.add_node("ocr_fallback", node_ocr_fallback)
    g.add_node("validate",     node_validate)
    g.add_node("correct",      node_correct)
    g.add_node("store",        node_store)
    g.add_node("review_queue", node_review_queue)

    g.set_entry_point("ingest")
    g.add_edge("ingest", "extract")
    g.add_conditional_edges("extract", _should_run_ocr,
                             {"ocr_fallback": "ocr_fallback", "validate": "validate"})
    g.add_edge("ocr_fallback", "validate")
    g.add_conditional_edges("validate", _route_after_validation,
                             {"correct": "correct", "store": "store",
                              "review_queue": "review_queue"})
    g.add_edge("correct",      "validate")
    g.add_edge("store",        END)
    g.add_edge("review_queue", END)

    return g.compile()


def _initial_state(path: str) -> InvoiceState:
    return {
        "document_id":         str(uuid.uuid4()),
        "source_path":         str(path),
        "images":              [],
        "ocr_texts":           [],
        "extraction":          None,
        "validation":          None,
        "correction_attempts": 0,
        "final_status":        None,
        "processing_notes":    [],
        "timings":             {},
        "pipeline_start":      time.time(),
    }


def process_document(path: str) -> InvoiceState:
    return build_graph().invoke(_initial_state(path))


def process_document_stream(path: str):
    """Yield (node_name, state) after each node completes."""
    graph = build_graph()
    for chunk in graph.stream(_initial_state(path)):
        node_name   = list(chunk.keys())[0]
        yield node_name, chunk[node_name]
