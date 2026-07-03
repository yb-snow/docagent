"""Per-user API key storage — ties each signed-in user's own Gemini/Claude
key to their authenticated email, encrypted at rest, so concurrent users on
a shared deployment never share or leak each other's keys."""

from __future__ import annotations

from typing import Optional

from database.storage import get_user_api_key_encrypted, save_user_api_key as _save_encrypted
from utils.crypto import decrypt, encrypt

PROVIDERS = ("gemini", "claude")


def get_api_keys(email: Optional[str]) -> dict:
    """Return {provider: decrypted_key} for whichever providers this user has saved."""
    if not email:
        return {}
    keys = {}
    for provider in PROVIDERS:
        enc = get_user_api_key_encrypted(email, provider)
        if enc:
            try:
                keys[provider] = decrypt(enc)
            except ValueError:
                pass   # e.g. FERNET_KEY rotated since this was saved — treat as unset
    return keys


def save_api_key(email: str, provider: str, plaintext_key: str) -> None:
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider: {provider}")
    _save_encrypted(email, provider, encrypt(plaintext_key))
