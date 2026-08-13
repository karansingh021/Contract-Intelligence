# ================================================================================================
# CONTRACT INTELLIGENCE PLATFORM — MAIN ENTRY POINT (Databricks Apps / Streamlit)
# File: app.py
# Port of: STREAMLIT.PY (the router), LANDINGPAGE.PY, DASHBOARD.PY
#
# Same structural fix documented in the original file is preserved here:
#   - st.set_page_config() is called exactly once, here, before anything else.
#   - landingpage.render() and dashboard.render() contain ALL of their st.* calls inside the
#     render() function -- nothing runs at import time -- so routing via session_state works.
# ================================================================================================

import streamlit as st

st.set_page_config(
    page_title="Contract Intelligence - Revenue Leakage AI",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

if "page" not in st.session_state:
    st.session_state.page = "landing"
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "quick_q" not in st.session_state:
    st.session_state.quick_q = None

import landingpage
import dashboard


def main():
    page = st.session_state.get("page", "landing")
    if page == "landing":
        landingpage.render()
    elif page == "dashboard":
        dashboard.render()
    else:
        st.session_state.page = "landing"
        st.rerun()


main()
