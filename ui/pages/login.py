import streamlit as st

from ui.auth import login


def render() -> None:
    # Three-column centering trick
    _, center, _ = st.columns([1, 1.2, 1])

    with center:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown(
            """
            <div style="text-align:center;margin-bottom:32px;">
                <div style="font-size:3.5rem;line-height:1;">🧾</div>
                <h1 style="font-size:2rem;font-weight:800;color:#1a2744;margin:8px 0 4px;">Doc Agent</h1>
                <p style="color:#6b7a99;font-size:.95rem;margin:0;">
                    Invoice &amp; Document Intelligence Platform
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.container(border=True):
            st.markdown(
                "<p style='font-size:1.1rem;font-weight:700;color:#1a2744;"
                "margin-bottom:20px;text-align:center'>Sign in to continue</p>",
                unsafe_allow_html=True,
            )

            if st.button("🔐  Sign in with Google", type="primary", use_container_width=True):
                try:
                    login()
                except Exception as e:
                    st.error(
                        "Couldn't start Google sign-in. If [auth] isn't in secrets.toml "
                        "yet, see .streamlit/secrets.toml.example for the exact fields. "
                        "Otherwise, the error below is the actual cause:"
                    )
                    st.caption(f"`{type(e).__name__}: {e}`")

        st.markdown(
            "<p style='text-align:center;font-size:.78rem;color:#9aa5be;margin-top:12px;'>"
            "Your Google identity is only used to sign in — you'll add your own "
            "Gemini/Claude API key separately in Settings after logging in."
            "</p>",
            unsafe_allow_html=True,
        )
