import os

import streamlit as st

# Bridge Streamlit Cloud's secrets manager into environment variables so
# config.py (which reads via os.getenv/python-dotenv) picks them up the same
# way it reads a local .env file. No-ops safely when no secrets.toml exists
# (local dev, where .env is used instead) — st.secrets returns empty rather
# than raising when the file is missing.
#
# Note: GEMINI_API_KEY/ANTHROPIC_API_KEY are deliberately NOT bridged here —
# each signed-in user brings their own key (Settings page, encrypted at
# rest — see utils/user_keys.py), never a shared key from secrets/env.
try:
    for _key in ("FERNET_KEY",):
        if _key in st.secrets and not os.environ.get(_key):
            os.environ[_key] = st.secrets[_key]
except Exception:
    pass

st.set_page_config(
    page_title="Doc Agent — Invoice Intelligence",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Imports after set_page_config
from ui.auth import check_auth
from ui.styles import inject_css
import ui.pages.login as login_page
import ui.pages.dashboard as dashboard_page
import ui.pages.process as process_page
import ui.pages.review as review_page
import ui.pages.history as history_page
import ui.pages.techstack as techstack_page
import ui.pages.settings as settings_page
from ui.components.sidebar import render_sidebar

inject_css()

# Safe to call on every rerun — CREATE TABLE IF NOT EXISTS. Needed here (not
# just inside build_graph()) so Settings can save a key before anyone has
# ever processed a document.
from database.storage import init_db
init_db()

if not check_auth():
    login_page.render()
    st.stop()

page = render_sidebar()

_PAGES = {
    "Dashboard":        dashboard_page.render,
    "Process Document": process_page.render,
    "Review Queue":     review_page.render,
    "History":          history_page.render,
    "Tech Stack":       techstack_page.render,
    "Settings":         settings_page.render,
}

_PAGES.get(page, dashboard_page.render)()
