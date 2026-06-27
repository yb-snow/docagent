import streamlit as st

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
