"""Authentication via Streamlit's native Google OAuth (st.login).

Requires an [auth] section in secrets.toml — see .streamlit/secrets.toml.example.
"""

from __future__ import annotations

from typing import Optional

import streamlit as st


def check_auth() -> bool:
    try:
        return bool(st.user.is_logged_in)
    except AttributeError:
        # [auth] isn't configured in secrets.toml yet (e.g. before Google
        # OAuth credentials are set up) — treat as "not logged in" rather
        # than crashing the whole app.
        return False


def current_email() -> Optional[str]:
    return st.user.email if check_auth() else None


def current_name() -> Optional[str]:
    if not check_auth():
        return None
    return getattr(st.user, "name", None) or st.user.email


def login() -> None:
    # No provider name here: secrets.toml defines a single unnamed default
    # provider under [auth] (not a named [auth.google] block), so the
    # provider-less form is what picks it up.
    st.login()


def logout() -> None:
    st.logout()
