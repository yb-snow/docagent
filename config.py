import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent

# ── VLM Backend ───────────────────────────────────────────────────────────────
# "gemini"  → Google Gemini (FREE — recommended for students, just needs Google account)
# "claude"  → Anthropic Claude (paid API key required)
# "internvl" / "llava" → local GPU model (HuggingFace, no API key, needs GPU)
VLM_BACKEND = os.getenv("VLM_BACKEND", "gemini")

# ── Google Gemini (Free Tier) ─────────────────────────────────────────────────
# Get your free API key at: https://aistudio.google.com/app/apikey
# No credit card required — just a Google account
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL   = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# ── Anthropic Claude (Optional) ───────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL      = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

# ── Local VLM (Optional — needs GPU) ─────────────────────────────────────────
LOCAL_VLM_MODEL  = os.getenv("LOCAL_VLM_MODEL", "InternVL2-8B")
LOCAL_VLM_DEVICE = os.getenv("LOCAL_VLM_DEVICE", "cuda")

# ── Tesseract OCR ─────────────────────────────────────────────────────────────
TESSERACT_CMD = os.getenv("TESSERACT_CMD", "tesseract")
OCR_DPI       = int(os.getenv("OCR_DPI", "300"))

# ── ChromaDB (vendor matching) ────────────────────────────────────────────────
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", str(BASE_DIR / "data" / "chroma"))
VENDOR_COLLECTION  = "vendors"

# ── SQLite storage ────────────────────────────────────────────────────────────
SQLITE_PATH = os.getenv("SQLITE_PATH", str(BASE_DIR / "data" / "invoices.db"))

# ── Validation thresholds ─────────────────────────────────────────────────────
TOTAL_TOLERANCE          = float(os.getenv("TOTAL_TOLERANCE", "0.01"))
FUZZY_VENDOR_THRESHOLD   = int(os.getenv("FUZZY_VENDOR_THRESHOLD", "80"))
EXTRACTION_CONF_THRESHOLD = float(os.getenv("EXTRACTION_CONF_THRESHOLD", "0.70"))
AUTO_APPROVE_THRESHOLD   = float(os.getenv("AUTO_APPROVE_THRESHOLD", "0.85"))

# ── Auto-correction ───────────────────────────────────────────────────────────
MAX_CORRECTION_ATTEMPTS = int(os.getenv("MAX_CORRECTION_ATTEMPTS", "2"))
CROP_PADDING_PX         = int(os.getenv("CROP_PADDING_PX", "20"))


# ── Runtime update helpers ────────────────────────────────────────────────────

def apply(updates: dict) -> None:
    """Update config values in memory AND persist to .env — no restart needed."""
    import sys
    module = sys.modules[__name__]

    # 1. Update module-level attributes so all importers see the new values
    for key, value in updates.items():
        os.environ[key] = str(value)
        if hasattr(module, key):
            current = getattr(module, key)
            try:
                setattr(module, key, type(current)(value))
            except (TypeError, ValueError):
                setattr(module, key, value)

    # 2. Persist to .env so values survive a restart
    env_path = BASE_DIR / ".env"
    try:
        existing: dict[str, str] = {}
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    existing[k.strip()] = v.strip()
        existing.update({k: str(v) for k, v in updates.items()})
        env_path.write_text(
            "\n".join(f"{k}={v}" for k, v in existing.items()) + "\n"
        )
    except Exception:
        pass   # write failure is non-fatal — in-memory update still works
