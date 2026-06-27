# Execution Plan — Multi-Modal Document Intelligence Agent

## Project Summary

Build a LangGraph multi-agent system that automatically processes invoices, receipts, and forms — extracting structured fields via a vision-language model, validating them with rule-based and semantic checks, auto-correcting failures, and routing low-confidence documents to a human review queue. Deployed as a Streamlit web app and a portable Google Colab notebook.

---

## Scope

| In Scope | Out of Scope |
|----------|-------------|
| PDF, PNG, JPG, TIFF input formats | Real-time email/ERP ingestion |
| Invoice, Receipt, Form document types | Handwriting recognition fine-tuning |
| VLM-based extraction (Claude / InternVL2 / LLaVA) | Production auth / multi-user RBAC |
| Tesseract OCR fallback | Payment gateway integration |
| Rule-based + semantic validation | Mobile app |
| Auto-correction (max 2 retries) | Multi-language support |
| Human review queue with approval UI | Cloud deployment / containerization |
| SQLite storage with audit trail | |
| JSON + CSV export | |
| Streamlit web UI + Colab notebook | |

---

## Architecture Overview

See [README.md](README.md) for the full block diagram and LangGraph state machine.

**Agent roles:**

| Agent | Input | Output |
|-------|-------|--------|
| Classification Agent | Preprocessed image | doc_type + schema + confidence |
| Extraction Agent | Image + schema + OCR (optional) | Pydantic data object |
| Validation Agent | Extracted data | Pass/Fail per field + confidence |
| Correction Agent | Image + failed fields | Corrected field values |

**Routing logic:**

```
Extracted confidence ≥ threshold  →  skip OCR fallback
Extracted confidence < threshold  →  run OCR, merge, re-extract

Validation PASS + confidence high  →  auto-store
Validation PASS + confidence low   →  human review
Validation FAIL (≤ max retries)    →  auto-correct → re-validate
Validation FAIL (> max retries)    →  human review queue
```

---

## Phase 1 — Environment & Foundation

**Goal:** Reproducible dev environment with working configuration layer.

**Tasks:**
- [ ] `requirements.txt` — all Python dependencies pinned
- [ ] `.env.example` — document all environment variables
- [ ] `config.py` — centralised settings loaded from `.env`
- [ ] `data/` directory structure — samples, output, db, chroma
- [ ] Verify Tesseract install on macOS and Linux
- [ ] Smoke test: `import anthropic; import langgraph; import chromadb`

**Deliverable:** `pip install -r requirements.txt` + `cp .env.example .env` is enough to start.

---

## Phase 2 — Document Ingestion Pipeline

**Goal:** Accept any supported file and return a list of clean, preprocessed PIL images.

**Module:** `pipeline/ingestion.py`

**Tasks:**
- [ ] PDF to image conversion via `pdf2image` at 300 DPI
- [ ] Direct image load for PNG, JPG, TIFF, BMP, WEBP
- [ ] Deskew: OpenCV `minAreaRect` rotation correction
- [ ] Contrast enhancement: Pillow `ImageEnhance.Contrast` (factor=1.5)
- [ ] Sharpening: Pillow `ImageEnhance.Sharpness` (factor=1.3)
- [ ] Multi-page handling — return `list[PIL.Image]`

**Test:** Feed a skewed scan; assert output image angle < 0.5°.

---

## Phase 3 — Classification Agent

**Goal:** Identify the document type before extraction so the correct schema is applied.

**Module:** `agents/classification_agent.py`

**Tasks:**
- [ ] Send first page image to VLM with classification prompt
- [ ] Parse response: `{"doc_type": "invoice|receipt|form", "confidence": 0.0-1.0}`
- [ ] Map `doc_type` → Pydantic schema class (`InvoiceData`, `ReceiptData`, `FormData`)
- [ ] Add `ReceiptData` and `FormData` Pydantic models to `models/schemas.py`
- [ ] Attach `doc_type` and `classification_confidence` to `InvoiceState`
- [ ] Wire into LangGraph as `[classify]` node after `[ingest]`

**Test:** Feed an invoice, receipt, and a form; assert correct type returned each time.

---

## Phase 4 — Extraction Agent

**Goal:** Extract structured fields from the document image using a VLM.

**Module:** `agents/extraction_agent.py`

**Tasks:**
- [ ] Schema-aware extraction prompt — include field list from the classified schema
- [ ] Claude vision API call: image (base64) + OCR text + prompt
- [ ] InternVL2-8B / LLaVA-7B local model path (optional, guarded by config)
- [ ] Parse VLM JSON response into Pydantic object
- [ ] Compute `extraction_confidence` as ratio of filled required fields
- [ ] Attach `extraction_confidence` to state

**Confidence threshold:** configurable via `EXTRACTION_CONFIDENCE_THRESHOLD` (default `0.7`)

**Test:** Feed a clear invoice PDF; assert `invoice_number`, `vendor_name`, `total_amount` all populated.

---

## Phase 5 — OCR Fallback

**Goal:** Supplement VLM extraction with Tesseract when confidence is low or fields are missing.

**Module:** `pipeline/ocr.py`

**Tasks:**
- [ ] `extract_text(image)` — Tesseract `--psm 6` full page text
- [ ] `extract_with_boxes(image)` — word-level bounding boxes
- [ ] `crop_region(image, keyword)` — crop around a keyword for focused re-query
- [ ] Merge OCR text with VLM output: fill `None` fields from OCR where possible
- [ ] Trigger condition: `extraction_confidence < EXTRACTION_CONFIDENCE_THRESHOLD`
- [ ] Wire into LangGraph as `[ocr_fallback]` conditional node

**Test:** Feed a low-quality scan; assert OCR text is non-empty and merged correctly.

---

## Phase 6 — Validation Agent

**Goal:** Verify extracted data against business rules and reference data.

**Module:** `agents/validation_agent.py`

**Rule-based checks:**
- [ ] Total amount = Subtotal + Tax (tolerance: ±0.01)
- [ ] Date fields parse as valid ISO 8601 (`YYYY-MM-DD`)
- [ ] IBAN matches regex `^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$`
- [ ] Required fields present (`vendor_name`, `total_amount`, `invoice_date`)

**Semantic checks:**
- [ ] Vendor name matched via ChromaDB vector search + rapidfuzz (threshold: 80)
- [ ] `VendorMatcher.match()` returns canonical vendor name on match

**Output:** `ValidationResult` with per-field pass/fail and `overall_confidence` score

**Test:** Inject a deliberate total mismatch; assert `total_amount` fails validation.

---

## Phase 7 — Auto-Correction Agent

**Goal:** Re-query the VLM with a focused image crop to fix individual failed fields.

**Module:** `agents/correction_agent.py`

**Tasks:**
- [ ] For each `failed_field`: find bounding box via Tesseract, crop image region
- [ ] Send crop + focused prompt to VLM: extract only the failed field
- [ ] Parse response and update the Pydantic object
- [ ] Track corrections in `corrections_applied` list
- [ ] Limit to `MAX_CORRECTION_ATTEMPTS` (default: 2) per document

**Test:** Inject a wrong date format; assert correction agent returns valid ISO date.

---

## Phase 8 — Confidence Router & Human Review Queue

**Goal:** Route auto-approved documents to storage; flag uncertain documents for human review.

**Routing logic in:** `graph/workflow.py`

**Tasks:**
- [ ] Compute `overall_confidence` from extraction confidence + validation pass rate
- [ ] If `overall_confidence >= AUTO_APPROVE_THRESHOLD`: route to `[store]`
- [ ] If `overall_confidence < AUTO_APPROVE_THRESHOLD` OR corrections exhausted: route to `[review_queue]`
- [ ] `review_queue` state: save to SQLite with `status = pending_review`
- [ ] UI review page: list pending records, allow field editing, approve or reject
- [ ] On approval: update `status = approved`, write to final storage

**Thresholds (configurable via `.env`):**
- `EXTRACTION_CONFIDENCE_THRESHOLD = 0.70`
- `AUTO_APPROVE_THRESHOLD = 0.85`

---

## Phase 9 — Storage & Export

**Goal:** Persist all records with a full audit trail; export to JSON and CSV.

**Module:** `database/storage.py`

**Tables:**
- `invoice_records` — final extracted + validated data per document
- `audit_log` — timestamped events: ingested, classified, extracted, validated, corrected, stored, reviewed

**Export tasks:**
- [ ] `export_json(document_id)` — single record as formatted JSON file
- [ ] `export_csv(filters)` — batch export filtered records as CSV
- [ ] Expose export buttons in UI (History page)
- [ ] Include raw OCR text, VLM response, corrections, final data in export

---

## Phase 10 — Streamlit UI

**Goal:** Web interface for uploading documents, reviewing results, and managing the pipeline.

**Entry point:** `app.py`

### Pages

| Page | Purpose |
|------|---------|
| Login | Authenticate (demo/demo for prototype) |
| Dashboard | KPI metrics, pipeline health, recent activity |
| Process Document | Upload file, run pipeline, view results |
| Review Queue | Approve/reject flagged documents with field editing |
| History | Browse all records, filter, export JSON/CSV |
| Settings | VLM backend, API keys, confidence thresholds |

### Components

| Component | Purpose |
|-----------|---------|
| `sidebar.py` | Navigation + user info + logout |
| `metrics.py` | KPI cards (total, success rate, pending, today) |
| `pipeline_status.py` | Animated step indicator during processing |

---

## Phase 11 — Google Colab Export

**Goal:** Self-contained `.ipynb` notebook that runs end-to-end without separate files.

**Tasks:**
- [ ] Inline all module code into notebook cells
- [ ] Install system deps (`apt-get tesseract poppler-utils`) in Cell 1
- [ ] Use `google.colab.userdata` for API key (Secrets)
- [ ] `google.colab.files.upload()` for document input
- [ ] Display results as Pandas DataFrames
- [ ] `google.colab.files.download()` for SQLite export

**File:** `invoice_agent_colab.ipynb` ✅ (already created)

---

## Testing Strategy

| Layer | Method |
|-------|--------|
| Schemas | Pydantic validation errors on bad data |
| Ingestion | Feed sample PDF; assert `len(images) > 0` |
| OCR | Known text document; assert token in output |
| Extraction | Sample invoice; assert required fields non-null |
| Validation | Inject deliberate errors; assert correct field fails |
| Correction | Provide fixable error; assert corrected value applied |
| Workflow | End-to-end run on 3 sample docs (invoice, receipt, form) |
| UI | Manual walkthrough of login → upload → review → export |

---

## Dataset Plan

Per the project brief:

| Dataset Type | Purpose | Source |
|-------------|---------|--------|
| Public invoice/receipt samples | Baseline testing | Open repositories (e.g. Kaggle invoice datasets) |
| Synthetic vendor invoices (varied templates) | Layout generalization | Generated programmatically |
| Low-quality scans / mobile photos | OCR + vision stress test | Manually created or collected |
| Generic business forms | Form extraction beyond invoices | Created from business form templates |

Minimum recommended test set: **20 documents** (8 invoices, 6 receipts, 6 forms) with known ground-truth values.

---

## Tech Stack

| Concern | Technology |
|---------|-----------|
| Orchestration | LangGraph 0.2+ |
| VLM (cloud) | Anthropic Claude (claude-sonnet-4-6) |
| VLM (local) | InternVL2-8B / LLaVA-7B (HuggingFace) |
| Image preprocessing | Pillow + OpenCV |
| OCR fallback | Tesseract / pytesseract |
| PDF conversion | pdf2image + Poppler |
| Data validation | Pydantic v2 |
| Vendor matching | ChromaDB + rapidfuzz |
| Storage | SQLite (sqlite3) |
| UI | Streamlit |
| Colab | Jupyter (ipynb) |
| Config | python-dotenv |

---

## Current Build Status

| Phase | Status |
|-------|--------|
| Phase 1 — Environment & Foundation | ✅ Complete |
| Phase 2 — Document Ingestion Pipeline | ✅ Complete |
| Phase 3 — Classification Agent | 🔲 Stub created |
| Phase 4 — Extraction Agent | ✅ Complete (Claude + local VLM) |
| Phase 5 — OCR Fallback | ⚠️ Partial (always-on; needs conditional trigger) |
| Phase 6 — Validation Agent | ✅ Complete |
| Phase 7 — Auto-Correction Agent | ✅ Complete |
| Phase 8 — Confidence Router + Review Queue | 🔲 In progress |
| Phase 9 — Storage & Export | ⚠️ Partial (storage done; CSV/JSON export pending) |
| Phase 10 — Streamlit UI | 🔲 Skeleton in progress |
| Phase 11 — Colab Export | ✅ Complete |
