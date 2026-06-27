"""Converts PDF/image files into preprocessed PIL images ready for OCR and VLM."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Union

from PIL import Image

from config import OCR_DPI
from utils.image_processing import deskew, enhance_contrast


def _find_poppler_path() -> Union[str, None]:
    """Return the explicit poppler bin directory so pdf2image always finds it.

    On macOS, Homebrew installs to /opt/homebrew/bin (Apple Silicon) or
    /usr/local/bin (Intel), but venv processes may not inherit the full PATH,
    so we always return the explicit path rather than relying on auto-detect.
    On Linux/Colab, pdftoppm is on the system PATH after apt-get install.
    """
    # Prefer explicit Homebrew paths on macOS (most reliable through venv)
    for candidate in (
        "/opt/homebrew/bin",   # Apple Silicon Mac
        "/usr/local/bin",      # Intel Mac
        "/opt/local/bin",      # MacPorts
    ):
        if Path(candidate, "pdftoppm").exists():
            return candidate
    # Linux / Colab — on PATH after apt-get install poppler-utils
    if shutil.which("pdftoppm"):
        return None   # let pdf2image use the system PATH
    return None


def load_document(path: Union[str, Path]) -> list[Image.Image]:
    """Return a list of preprocessed PIL images — one per page for PDFs."""
    path   = Path(path)
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return _pdf_to_images(path)
    elif suffix in {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"}:
        img = Image.open(path).convert("RGB")
        return [_preprocess(img)]
    else:
        raise ValueError(f"Unsupported file type: {suffix}. Supported: PDF, PNG, JPG, TIFF, BMP")


def _pdf_to_images(path: Path) -> list[Image.Image]:
    try:
        from pdf2image import convert_from_path
    except ImportError as e:
        raise ImportError("pdf2image not installed. Run: pip install pdf2image") from e

    poppler_path = _find_poppler_path()
    kwargs = {"dpi": OCR_DPI}
    if poppler_path:
        kwargs["poppler_path"] = poppler_path

    try:
        pages = convert_from_path(str(path), **kwargs)
    except Exception as e:
        err = str(e)
        if "poppler" in err.lower() or "page count" in err.lower():
            raise RuntimeError(
                "Poppler not found. Install it:\n"
                "  macOS:  brew install poppler\n"
                "  Ubuntu: sudo apt-get install poppler-utils\n"
                "  Colab:  !apt-get install -y poppler-utils"
            ) from e
        raise

    return [_preprocess(p.convert("RGB")) for p in pages]


def _preprocess(img: Image.Image) -> Image.Image:
    img = deskew(img)
    img = enhance_contrast(img)
    return img
