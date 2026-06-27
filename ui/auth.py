import streamlit as st

_CREDENTIALS = {"demo": "demo"}


def check_auth() -> bool:
    return st.session_state.get("logged_in", False)


def login(username: str, password: str) -> bool:
    if _CREDENTIALS.get(username) == password:
        st.session_state.logged_in = True
        st.session_state.username = username
        return True
    return False


def logout() -> None:
    for key in ("logged_in", "username", "current_page"):
        st.session_state.pop(key, None)
