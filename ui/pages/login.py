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
                "<p style='font-size:1.1rem;font-weight:700;color:#1a2744;margin-bottom:20px;'>Sign in to your account</p>",
                unsafe_allow_html=True,
            )

            username = st.text_input(
                "Username",
                placeholder="Enter username",
                key="login_username",
            )
            password = st.text_input(
                "Password",
                type="password",
                placeholder="Enter password",
                key="login_password",
            )

            st.markdown("<br/>", unsafe_allow_html=True)

            if st.button("Sign In", type="primary", use_container_width=True):
                if not username or not password:
                    st.warning("Please enter both username and password.")
                elif login(username, password):
                    st.success("Login successful!")
                    st.rerun()
                else:
                    st.error("Invalid credentials. Try demo / demo")

        st.markdown(
            "<p style='text-align:center;font-size:.78rem;color:#9aa5be;margin-top:12px;'>"
            "Demo credentials: <strong>demo</strong> / <strong>demo</strong>"
            "</p>",
            unsafe_allow_html=True,
        )
