import streamlit as st
from ui.auth import logout

_NAV = [
    ("📊", "Dashboard",        ),
    ("🔄", "Process Document", ),
    ("👁️", "Review Queue",     ),
    ("📋", "History",          ),
    ("🛠️", "Tech Stack",       ),
    ("⚙️", "Settings",         ),
]

# Inline-style constants so visibility never depends on CSS inheritance
_SIDEBAR_BG      = "#1a2744"
_TEXT_LIGHT      = "#e8edf5"
_TEXT_DIM        = "rgba(232,237,245,0.65)"
_BTN_DEFAULT     = "rgba(255,255,255,0.07)"
_BTN_ACTIVE      = "rgba(255,255,255,0.18)"
_BTN_ACTIVE_BORDER = "rgba(255,255,255,0.35)"
_BTN_HOVER       = "rgba(255,255,255,0.12)"
_DIVIDER         = "rgba(255,255,255,0.12)"


def _nav_button(icon: str, label: str, is_active: bool) -> bool:
    bg     = _BTN_ACTIVE  if is_active else _BTN_DEFAULT
    border = f"1px solid {_BTN_ACTIVE_BORDER}" if is_active else "1px solid rgba(255,255,255,0.08)"
    fw     = "700" if is_active else "500"

    st.markdown(
        f"""<div style="
            background:{bg};
            border:{border};
            border-radius:8px;
            padding:9px 14px;
            margin:3px 0;
            cursor:pointer;
            display:flex;
            align-items:center;
            gap:10px;
            font-size:.92rem;
            font-weight:{fw};
            color:{_TEXT_LIGHT};
            line-height:1.3;
        ">{icon}&nbsp;&nbsp;{label}</div>""",
        unsafe_allow_html=True,
    )
    return st.button(
        f"{icon}  {label}",
        key=f"nav_{label}",
        use_container_width=True,
        help=f"Go to {label}",
    )


def render_sidebar() -> str:
    if "current_page" not in st.session_state:
        st.session_state.current_page = "Dashboard"

    with st.sidebar:
        # ── Logo ──────────────────────────────────────────────────────────────
        st.markdown(
            f"""<div style="
                padding:16px 4px 4px;
                color:{_TEXT_LIGHT};
                font-size:1.4rem;
                font-weight:800;
                letter-spacing:-0.5px;
                line-height:1.2;
            ">🧾 Doc Agent</div>
            <div style="
                color:{_TEXT_DIM};
                font-size:.75rem;
                padding:0 4px 14px;
                border-bottom:1px solid {_DIVIDER};
                margin-bottom:12px;
            ">Invoice Intelligence Platform</div>""",
            unsafe_allow_html=True,
        )

        # ── User info ──────────────────────────────────────────────────────────
        username = st.session_state.get("username", "user")
        st.markdown(
            f"""<div style="
                color:{_TEXT_DIM};
                font-size:.8rem;
                padding:0 4px 14px;
                margin-bottom:8px;
            ">👤 {username}</div>""",
            unsafe_allow_html=True,
        )

        # ── Nav label ──────────────────────────────────────────────────────────
        st.markdown(
            f"""<div style="
                color:{_TEXT_DIM};
                font-size:.65rem;
                text-transform:uppercase;
                letter-spacing:1.2px;
                padding:0 4px 6px;
            ">Navigation</div>""",
            unsafe_allow_html=True,
        )

        # ── Nav buttons ────────────────────────────────────────────────────────
        for icon, label in _NAV:
            is_active = st.session_state.current_page == label
            if st.button(
                f"{icon}  {label}",
                key=f"nav_{label}",
                use_container_width=True,
            ):
                st.session_state.current_page = label
                st.rerun()

        # ── Divider + Logout ───────────────────────────────────────────────────
        st.markdown(
            f"<hr style='border:none;border-top:1px solid {_DIVIDER};margin:16px 0'/>",
            unsafe_allow_html=True,
        )
        if st.button("🚪  Logout", use_container_width=True, key="nav_logout"):
            logout()
            st.rerun()


    return st.session_state.current_page
