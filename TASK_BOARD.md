# Doc Agent — Team Task Board
### Capstone Project | Remaining Work & Assignments

---

## Project Status Summary

The project skeleton, architecture, and all major components are built.
**~65% complete.** The remaining work is wiring the layers together and replacing mock data with real pipeline output.

```
WHAT'S BUILT ✅                    WHAT NEEDS WIRING ⚠️
─────────────────────────────────  ──────────────────────────────────────
All 4 agents (code exists)         Classification agent → LangGraph
LangGraph state machine            OCR as conditional fallback (not always-on)
Streamlit UI (all 5 pages)         Confidence-based routing (auto vs review)
SQLite storage + audit log         UI pages reading from real database
Gemini + Claude VLM backends       Process page calling real pipeline
Colab notebook                     Review queue persisting to SQLite
```

---

## Block Diagram (Reference)

```
INPUT (PDF/Image)
    ↓
[INGESTION]  pdf2image → deskew → contrast            ← ✅ Done
    ↓
[CLASSIFICATION]  Gemini → Invoice / Receipt / Form   ← ⚠️ Agent done, not in pipeline
    ↓
[EXTRACTION]  Gemini Vision → Pydantic object         ← ✅ Done
    ↓  (if confidence < 0.70)
[OCR FALLBACK]  Tesseract → merge with VLM output     ← ⚠️ Always runs, needs condition
    ↓
[VALIDATION]  rule-based + ChromaDB/rapidfuzz         ← ✅ Done
    ↓ fail           ↓ pass + high conf   ↓ pass + low conf
[CORRECTION]     [AUTO-APPROVE]         [REVIEW QUEUE]
Max 2 retries    → SQLite               → pending_review
    ↓
[STORAGE]  SQLite + audit trail + JSON/CSV export     ← ⚠️ Storage done, UI not connected
```

---

## Team Assignments

> Each person owns one layer of the block diagram.
> All tasks are in the same GitHub repo: **https://github.com/yb-snow/capstone**

---

## 👤 Member 1 — Yogesh (Architecture Lead)
**Layer: Project Setup, Integration & Final Review**

*Already completed:* Full project skeleton, all agents, LangGraph workflow, Streamlit UI shell, Gemini integration, GitHub setup, Colab notebook.

**Remaining responsibilities:**
- [ ] Review and merge all pull requests from team members
- [ ] Run end-to-end integration test once all layers are connected
- [ ] Update `doc_agent_capstone_colab.ipynb` with any final changes
- [ ] Final demo preparation

---

## 👤 Member 2 — Classification Layer
**Layer: Document Classification + Schema Selection**

**Goal:** Wire the classification agent into the pipeline so every document is identified as Invoice, Receipt, or Form before extraction — and extraction uses the right schema for each type.

### Files to work on
| File | Action |
|------|--------|
| `models/schemas.py` | Add `ReceiptData` and `FormData` Pydantic models |
| `graph/workflow.py` | Add `classify` node between `ingest` and `extract` |
| `agents/classification_agent.py` | Already written — just needs testing |

### Tasks

**Task 2.1 — Add ReceiptData and FormData schemas** *(~2 hours)*

Open `models/schemas.py` and add two new models below `InvoiceData`:

```python
class ReceiptData(BaseModel):
    store_name:     Optional[str] = None
    receipt_date:   Optional[str] = None   # YYYY-MM-DD
    receipt_number: Optional[str] = None
    items:          list[LineItem] = Field(default_factory=list)
    subtotal:       Optional[float] = None
    tax_amount:     Optional[float] = None
    total_amount:   Optional[float] = None
    currency:       Optional[str] = "USD"
    payment_method: Optional[str] = None   # cash / card / etc.

class FormData(BaseModel):
    form_type:      Optional[str] = None   # W-9, expense report, etc.
    submitter_name: Optional[str] = None
    submission_date:Optional[str] = None
    fields:         dict = Field(default_factory=dict)  # key-value pairs
    reference_id:   Optional[str] = None
```

**Task 2.2 — Add `classify` node to LangGraph** *(~2 hours)*

Open `graph/workflow.py`. Currently the workflow is:
```
ingest → ocr → extract → validate → ...
```
Change it to:
```
ingest → classify → extract → validate → ...
```

Steps:
1. Import `classification_agent` at the top
2. Add `doc_type` and `classification_confidence` to `InvoiceState` TypedDict
3. Write a `node_classify` function that calls `classification_agent.run(state["images"][0])` and stores result in state
4. Add the node and edge in `build_graph()`

**Task 2.3 — Pass doc_type to extraction agent** *(~1 hour)*

Update `node_extract` in `workflow.py` so it passes `state["doc_type"]` to `extraction_agent.run()`, then update `extraction_agent.run()` to accept an optional `doc_type` parameter and mention it in the extraction prompt.

### Acceptance criteria
- [ ] `workflow.py` has a `classify` node running between `ingest` and `extract`
- [ ] `state["doc_type"]` is set to `"invoice"`, `"receipt"`, or `"form"`
- [ ] Running the pipeline on a receipt file logs `doc_type: receipt`
- [ ] `ReceiptData` and `FormData` models importable from `models.schemas`

---

## 👤 Member 3 — OCR Fallback Layer
**Layer: Conditional OCR + VLM+OCR Merge**

**Goal:** Make OCR a smart fallback — only trigger Tesseract when Gemini's extraction confidence is below the threshold, then merge the two outputs to fill missing fields.

### Files to work on
| File | Action |
|------|--------|
| `graph/workflow.py` | Replace always-on `ocr` node with conditional `ocr_fallback` |
| `pipeline/ocr.py` | Add `merge_ocr_with_extraction()` function |
| `pipeline/ingestion.py` | No changes needed |

### Tasks

**Task 3.1 — Make OCR conditional in workflow.py** *(~2 hours)*

Currently `workflow.py` always runs `node_ocr` after `node_ingest`. Change this:

```python
# Current (always runs OCR)
ingest → ocr → extract → ...

# Target (OCR only when needed)
ingest → extract → ocr_fallback? → validate → ...
```

Steps:
1. Move `node_ocr` to run AFTER `node_extract`
2. Rename it `node_ocr_fallback`
3. Add a router function `_should_run_ocr` that returns `"ocr_fallback"` if `state["extraction"].confidence < EXTRACTION_CONF_THRESHOLD` else `"validate"`
4. Use `add_conditional_edges` to route after `extract`

```python
# In graph/workflow.py
from config import EXTRACTION_CONF_THRESHOLD

def _should_run_ocr(state: InvoiceState) -> str:
    if state["extraction"] and state["extraction"].confidence < EXTRACTION_CONF_THRESHOLD:
        return "ocr_fallback"
    return "validate"
```

**Task 3.2 — Merge OCR output with VLM extraction** *(~2 hours)*

Open `pipeline/ocr.py` and add:

```python
def merge_ocr_with_extraction(ocr_text: str, extracted: InvoiceData) -> InvoiceData:
    """Fill None fields in extracted data using simple OCR text patterns."""
    import re
    data = extracted.model_copy(deep=True)

    # Example: find a date pattern in OCR text if invoice_date is None
    if data.invoice_date is None:
        date_match = re.search(r'\b(\d{4}-\d{2}-\d{2})\b', ocr_text)
        if date_match:
            data.invoice_date = date_match.group(1)

    # Example: find total amount if total_amount is None
    if data.total_amount is None:
        total_match = re.search(r'(?:total|amount due)[^\d]*(\d[\d,]*\.?\d*)', ocr_text, re.IGNORECASE)
        if total_match:
            try:
                data.total_amount = float(total_match.group(1).replace(',', ''))
            except ValueError:
                pass

    return data
```

Expand patterns for other fields (invoice_number, vendor_name, tax_amount).

**Task 3.3 — Wire merge into OCR fallback node** *(~30 min)*

In `workflow.py`, after OCR extracts text, call `merge_ocr_with_extraction()` and update `state["extraction"]`.

### Acceptance criteria
- [ ] High-quality invoice → OCR node is **skipped** (check processing_notes log)
- [ ] Low-quality/blurry image → OCR node **runs** and fills missing fields
- [ ] `state["processing_notes"]` shows either `"OCR skipped"` or `"OCR fallback ran — filled X fields"`

---

## 👤 Member 4 — Validation + Correction Layer
**Layer: Validation Improvements + Auto-Correction Testing**

**Goal:** Strengthen the validation agent with additional rules, seed the vendor database with real test data, and verify the auto-correction loop works end-to-end.

### Files to work on
| File | Action |
|------|--------|
| `agents/validation_agent.py` | Add required-field and line-item math checks |
| `utils/vendor_matcher.py` | Improve vendor seeding, add bulk-load function |
| `database/storage.py` | Add `get_audit_trail(doc_id)` function |
| `data/vendors.txt` | Create a list of sample vendor names for testing |

### Tasks

**Task 4.1 — Add required-field validation** *(~1.5 hours)*

Open `agents/validation_agent.py`. Currently it only checks `vendor_name`. Add a check for all required fields:

```python
_REQUIRED_FIELDS = ["vendor_name", "invoice_date", "total_amount"]

def _check_required_fields(data: InvoiceData) -> list[FieldValidation]:
    results = []
    for field in _REQUIRED_FIELDS:
        value = getattr(data, field, None)
        if value is None or (isinstance(value, str) and not value.strip()):
            results.append(FieldValidation(
                field=field,
                status=ValidationStatus.FAILED,
                message=f"Required field '{field}' is missing",
            ))
        else:
            results.append(FieldValidation(field=field, status=ValidationStatus.VALID))
    return results
```

Add `_check_required_fields(data)` to the `run()` function's checks list.

**Task 4.2 — Add line-item total validation** *(~1.5 hours)*

Add a function to verify that each `line_item.total ≈ quantity × unit_price`, and that the sum of line items equals the subtotal:

```python
def _check_line_items(data: InvoiceData) -> list[FieldValidation]:
    results = []
    if not data.line_items:
        return results
    computed_subtotal = sum(item.total for item in data.line_items)
    if data.subtotal is not None:
        if abs(computed_subtotal - data.subtotal) > TOTAL_TOLERANCE:
            results.append(FieldValidation(
                field="subtotal",
                status=ValidationStatus.FAILED,
                message=f"Sum of line items ({computed_subtotal:.2f}) != subtotal ({data.subtotal:.2f})",
            ))
    return results
```

**Task 4.3 — Create vendor seed file and bulk-load function** *(~1 hour)*

1. Create `data/vendors.txt` — one vendor name per line (add 20+ realistic vendor names)
2. In `utils/vendor_matcher.py`, add:

```python
def load_vendors_from_file(filepath: str) -> None:
    """Load vendor names from a text file (one per line) into ChromaDB."""
    with open(filepath) as f:
        vendors = [line.strip() for line in f if line.strip()]
    add_vendors(vendors)
    print(f"Loaded {len(vendors)} vendors from {filepath}")
```

3. Call this in `database/storage.py` `init_db()` so vendors load on startup.

**Task 4.4 — Write end-to-end correction test** *(~1.5 hours)*

Create `tests/test_correction.py`:

```python
# Tests that a deliberately wrong total gets corrected
# Create a mock ExtractionResult with total_amount = 999.00 (wrong)
# Run validation → should fail on total_amount
# Run correction → should attempt fix
# Check that correction_attempts > 0 in final state
```

### Acceptance criteria
- [ ] Missing `vendor_name` or `total_amount` → shows as `FAILED` in validation
- [ ] Line items sum ≠ subtotal → shows as `FAILED`
- [ ] `data/vendors.txt` exists with 20+ vendor names
- [ ] Vendors auto-load on `init_db()`
- [ ] At least one test file in `tests/`

---

## 👤 Member 5 — Confidence Router + Review Queue
**Layer: Smart Routing + Human Review Persistence**

**Goal:** Implement confidence-based routing in LangGraph so high-confidence documents go straight to storage and low-confidence ones are saved as `pending_review` in SQLite. Wire the Review Queue UI to read from and write to the real database.

### Files to work on
| File | Action |
|------|--------|
| `graph/workflow.py` | Add confidence router, `review_queue` node |
| `database/storage.py` | Add `pending_review` status, approve/reject functions |
| `ui/pages/review.py` | Replace hardcoded mock data with real SQLite query |

### Tasks

**Task 5.1 — Add confidence router to LangGraph** *(~2 hours)*

Open `graph/workflow.py`. After `node_store`, add a second router that splits by confidence:

```python
from config import AUTO_APPROVE_THRESHOLD

def _confidence_route(state: InvoiceState) -> str:
    """Route to review queue if confidence is below auto-approve threshold."""
    extraction_conf = state["extraction"].confidence if state["extraction"] else 0.0
    validation_ok   = state["validation"].is_valid if state["validation"] else False

    if validation_ok and extraction_conf >= AUTO_APPROVE_THRESHOLD:
        return "store"
    elif state["correction_attempts"] >= MAX_CORRECTION_ATTEMPTS:
        return "review_queue"   # exhausted retries
    elif not validation_ok:
        return "correct"
    return "store"
```

Replace the existing `_should_correct` router with this one.

**Task 5.2 — Add `review_queue` node and SQLite status** *(~2 hours)*

1. Add a `node_review_queue` function in `workflow.py`:

```python
def node_review_queue(state: InvoiceState) -> InvoiceState:
    """Save document as pending_review — awaiting human approval."""
    state["final_status"] = ValidationStatus.FAILED
    save_record(ProcessingRecord(
        ...
        validation_status=ValidationStatus.FAILED,
        processing_notes=state["processing_notes"] + ["Sent to human review queue"],
    ))
    log_event(state["document_id"], "review_queue", {"reason": "low confidence or validation failed"})
    return state
```

2. In `database/storage.py` add two functions:

```python
def get_pending_review(limit: int = 50) -> list[dict]:
    """Return all records with validation_status = 'failed' awaiting review."""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM invoice_records WHERE validation_status = 'failed' ORDER BY created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
    return [dict(r) for r in rows]

def approve_record(document_id: str, updated_data: dict) -> None:
    """Mark a record as approved and update its final_data."""
    with _get_conn() as conn:
        conn.execute(
            "UPDATE invoice_records SET validation_status='valid', final_data=? WHERE document_id=?",
            (json.dumps(updated_data), document_id)
        )

def reject_record(document_id: str) -> None:
    with _get_conn() as conn:
        conn.execute(
            "UPDATE invoice_records SET validation_status='rejected' WHERE document_id=?",
            (document_id,)
        )
```

**Task 5.3 — Wire Review Queue UI to real database** *(~2 hours)*

Open `ui/pages/review.py`. Currently it uses `_PENDING` (hardcoded list).

Replace with:
```python
# At top of render():
import sys; sys.path.insert(0, ".")
from database.storage import get_pending_review, approve_record, reject_record

pending_records = get_pending_review()
# Map these to the same format the UI expects and display them
```

Update the Approve and Reject buttons to call `approve_record()` / `reject_record()` with the document ID.

### Acceptance criteria
- [ ] A low-confidence document processed via pipeline appears in the Review Queue page
- [ ] Clicking Approve updates `validation_status` to `"valid"` in SQLite
- [ ] Clicking Reject updates `validation_status` to `"rejected"` in SQLite
- [ ] High-confidence documents bypass the review queue and go straight to storage
- [ ] `processing_notes` shows the routing decision

---

## 👤 Member 6 — UI ↔ Backend Integration + Export
**Layer: Connect UI to Real Pipeline & Data**

**Goal:** This is the most visible work — wire the Process page to call the real LangGraph pipeline, and make Dashboard/History pages read live data from SQLite instead of hardcoded mock lists.

### Files to work on
| File | Action |
|------|--------|
| `ui/pages/process.py` | Replace `_run_mock_pipeline()` with real workflow call |
| `ui/pages/dashboard.py` | Replace hardcoded numbers with SQLite queries |
| `ui/pages/history.py` | Replace `_RECORDS` list with `storage.list_records()` |
| `database/storage.py` | Add `get_stats()` function |

### Tasks

**Task 6.1 — Wire Process page to real pipeline** *(~3 hours)*
> This is the most important task in the whole project.

Open `ui/pages/process.py`. Find `_run_mock_pipeline()` and replace it:

```python
def _run_real_pipeline(uploaded_file, placeholder) -> dict:
    import sys, os, uuid, tempfile
    sys.path.insert(0, os.getcwd())
    from graph.workflow import process_document

    # Save uploaded file to temp location
    suffix = Path(uploaded_file.name).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.read())
        tmp_path = tmp.name

    # Show pipeline steps while running
    stages = ["Ingest", "Classify", "Extract", "OCR Check", "Validate", "Route", "Store"]
    for i, stage in enumerate(stages):
        with placeholder.container():
            pipeline_status.render(current_stage=stage)
            st.caption(f"Running: {stage}...")

    # Run the real pipeline
    final_state = process_document(tmp_path)
    os.unlink(tmp_path)

    # Convert state to display format
    data = final_state["extraction"].extracted_data if final_state["extraction"] else {}
    return {
        "doc_type":                    final_state.get("doc_type", "invoice"),
        "classification_confidence":   final_state.get("classification_confidence", 0.0),
        "extraction_confidence":       final_state["extraction"].confidence if final_state["extraction"] else 0.0,
        "validation_status":           final_state["final_status"].value if final_state["final_status"] else "unknown",
        "corrections":                 final_state["correction_attempts"],
        "data":                        data.model_dump() if hasattr(data, "model_dump") else {},
        "line_items":                  data.line_items if hasattr(data, "line_items") else [],
    }
```

Update the button handler to call `_run_real_pipeline()` instead of `_run_mock_pipeline()`.

**Task 6.2 — Add `get_stats()` to storage.py** *(~1 hour)*

```python
def get_stats() -> dict:
    """Return aggregate stats for the dashboard."""
    with _get_conn() as conn:
        total     = conn.execute("SELECT COUNT(*) FROM invoice_records").fetchone()[0]
        valid     = conn.execute("SELECT COUNT(*) FROM invoice_records WHERE validation_status='valid'").fetchone()[0]
        pending   = conn.execute("SELECT COUNT(*) FROM invoice_records WHERE validation_status='failed'").fetchone()[0]
        today_str = datetime.utcnow().strftime("%Y-%m-%d")
        today     = conn.execute(
            "SELECT COUNT(*) FROM invoice_records WHERE created_at LIKE ?", (f"{today_str}%",)
        ).fetchone()[0]
    return {
        "total":        total,
        "success_rate": round((valid / total * 100) if total > 0 else 0.0, 1),
        "pending":      pending,
        "today":        today,
    }
```

**Task 6.3 — Wire Dashboard to real data** *(~1 hour)*

Open `ui/pages/dashboard.py`. Replace the hardcoded `render_kpi_row(total=247, ...)` call:

```python
from database.storage import get_stats, list_records

stats = get_stats()
render_kpi_row(
    total=stats["total"],
    success_rate=stats["success_rate"],
    pending=stats["pending"],
    today=stats["today"],
)
```

Replace `_RECENT` hardcoded list with `list_records(limit=5)`.

**Task 6.4 — Wire History page to real data** *(~1 hour)*

Open `ui/pages/history.py`. Replace `_RECORDS = [...]` with:

```python
from database.storage import list_records
import json

raw = list_records(limit=500)
_RECORDS = []
for r in raw:
    final = json.loads(r["final_data"]) if r["final_data"] else {}
    _RECORDS.append({
        "ID":         r["document_id"][:8],
        "File":       r["source_path"].split("/")[-1],
        "Type":       r.get("doc_type", "invoice").title(),
        "Vendor":     final.get("vendor_name", "—"),
        "Total":      final.get("total_amount"),
        "Status":     r["validation_status"],
        "Date":       r["created_at"][:10],
    })
```

### Acceptance criteria
- [ ] Upload a real PDF → pipeline runs → extracted data shows in the UI (not mock data)
- [ ] Dashboard KPI numbers match what's in `invoices.db`
- [ ] History page shows real processed documents with correct statuses
- [ ] Download JSON/CSV from History exports real data
- [ ] No mock data anywhere in the UI when documents have been processed

---

## How to Contribute (Git Workflow)

```bash
# 1. Clone the repo
git clone https://github.com/yb-snow/capstone.git
cd capstone

# 2. Create a branch for your task
git checkout -b feature/member2-classification

# 3. Work on your tasks, then commit
git add .
git commit -m "Add classification node to LangGraph workflow"

# 4. Push and open a Pull Request on GitHub
git push origin feature/member2-classification
# → Go to github.com/yb-snow/capstone → "Compare & pull request"
```

**Branch naming convention:**
- `feature/member2-classification`
- `feature/member3-ocr-fallback`
- `feature/member4-validation`
- `feature/member5-review-queue`
- `feature/member6-ui-integration`

---

## Running the App Locally

```bash
cd capstone

# 1. Copy .env and add your Gemini API key
cp .env.example .env
# Edit .env → set GEMINI_API_KEY=AIza...

# 2. Install dependencies
pip install -r requirements.txt

# 3. Install Tesseract (macOS)
brew install tesseract

# 4. Run the app
.venv/bin/streamlit run app.py
# → Open http://localhost:8501
# → Login: demo / demo
```

**On Google Colab:** Open `doc_agent_capstone_colab.ipynb` and follow the 4 steps.

---

## Task Summary Table

| Member | Layer | Main File(s) | Effort Est. | Difficulty |
|--------|-------|-------------|-------------|------------|
| **1 — Yogesh** | Architecture + Integration | All | — | Lead |
| **2** | Classification | `workflow.py`, `schemas.py` | ~5 hrs | ⭐⭐ |
| **3** | OCR Fallback | `workflow.py`, `ocr.py` | ~5 hrs | ⭐⭐⭐ |
| **4** | Validation + Correction | `validation_agent.py`, `vendor_matcher.py` | ~6 hrs | ⭐⭐ |
| **5** | Confidence Router + Review Queue | `workflow.py`, `storage.py`, `review.py` | ~6 hrs | ⭐⭐⭐ |
| **6** | UI ↔ Backend Integration | `process.py`, `dashboard.py`, `history.py` | ~6 hrs | ⭐⭐⭐ |

---

*Last updated by Yogesh. Questions? Open a GitHub issue or ping the team.*
