"""Pillow-based image preprocessing: deskew and contrast enhancement."""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter


def deskew(img: Image.Image) -> Image.Image:
    """Detect and correct skew using projection profile method."""
    try:
        import cv2
    except ImportError:
        return img  # skip silently if opencv not installed

    gray = np.array(img.convert("L"))
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    coords = np.column_stack(np.where(binary > 0))
    if len(coords) < 10:
        return img
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = 90 + angle
    if abs(angle) < 0.5:
        return img
    return img.rotate(-angle, expand=True, fillcolor=(255, 255, 255))


def enhance_contrast(img: Image.Image, factor: float = 1.5) -> Image.Image:
    """Apply contrast enhancement and mild sharpening."""
    img = ImageEnhance.Contrast(img).enhance(factor)
    img = ImageEnhance.Sharpness(img).enhance(1.3)
    return img


def image_to_base64(img: Image.Image, fmt: str = "PNG") -> str:
    """Encode a PIL image as a base64 string for API calls."""
    import base64
    import io

    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return base64.b64encode(buf.getvalue()).decode("utf-8")
