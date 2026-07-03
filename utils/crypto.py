"""Fernet-based encryption for per-user API keys.

The plaintext key only ever exists in memory for the duration of a request —
what gets written to SQLite is always the encrypted token.
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

import config


def _fernet() -> Fernet:
    key = config.FERNET_KEY
    if not key:
        raise RuntimeError(
            "FERNET_KEY is not configured. Set it in .env (local) or "
            "secrets.toml (deployed). Generate one with:\n"
            '  python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"'
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as e:
        raise ValueError("Could not decrypt value — FERNET_KEY may have changed.") from e
