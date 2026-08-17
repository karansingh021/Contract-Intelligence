# Contract Intelligence Streamlit entry point with 2-mode design and Permissions SDK
# Co-authored with CoCo
# ================================================================
# CONTRACT INTELLIGENCE — STREAMLIT ENTRY POINT
# Two modes:
#   DEMO     → provider's pre-extracted sample contracts (instant value)
#   CONSUMER → user uploads their own data in native enterprise formats:
#              - Contract Details: PDF
#              - CRM Data: JSON
#              - ERP Data: CSV
#              - OPS Data: JSON
# Permissions SDK checks run on every launch.
# ================================================================

import streamlit as st
import snowflake.permissions as permissions
from snowflake.snowpark.context import get_active_session

st.set_page_config(
    page_title="Contract Intelligence - Revenue Leakage AI",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

if "page" not in st.session_state:
    st.session_state.page = "landing"
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "quick_q" not in st.session_state:
    st.session_state.quick_q = None
if "setup_complete" not in st.session_state:
    st.session_state.setup_complete = False

import landingpage
import dashboard

session = get_active_session()


# ── Permissions & Reference Checks ────────────────────────────────────────

REQUIRED_REFERENCES = ["consumer_warehouse"]


def _check_reference_bound(ref_name):
    """Return True if the reference has at least one association."""
    try:
        assocs = permissions.get_reference_associations(ref_name)
        return len(assocs) > 0
    except Exception:
        return False


def _is_stage_configured():
    """Check if consumer data stage is configured."""
    try:
        rows = session.sql(
            "SELECT setting_value FROM config.app_settings WHERE setting_key='CONSUMER_STAGE'"
        ).collect()
        return bool(rows and rows[0][0])
    except Exception:
        return False


def _all_setup_done():
    """Check if warehouse ref is bound and stage is configured."""
    return all(_check_reference_bound(r) for r in REQUIRED_REFERENCES) and _is_stage_configured()


def render_setup():
    """Onboarding page — prompts consumer to bind warehouse and configure stage."""
    st.markdown("## Welcome to Contract Intelligence")
    st.markdown(
        "Before you can use your own data, we need a few permissions from your account. "
        "This only takes a moment."
    )
    st.markdown("---")

    # ── Step 1: Warehouse Reference ────────────────────────────────────────
    st.markdown("### Step 1: Select a Processing Warehouse")

    if not _check_reference_bound("consumer_warehouse"):
        st.info(
            "Select a warehouse for the app to use when running the ingestion pipeline "
            "and leakage detection rule engine."
        )
        if st.button("Select Warehouse", type="primary", key="btn_bind_wh"):
            permissions.request_reference("consumer_warehouse")
        return
    else:
        st.success("Warehouse bound.")

    # ── Step 2: Data Stage ─────────────────────────────────────────────────
    st.markdown("### Step 2: Configure Your Data Stage")

    if not _is_stage_configured():
        st.warning(
            "**Run these grants** to give the app read access to your stage:\n\n"
            "```sql\n"
            "GRANT USAGE ON DATABASE <db> TO APPLICATION CONTRACT_INTEL_APP;\n"
            "GRANT USAGE ON SCHEMA <db.schema> TO APPLICATION CONTRACT_INTEL_APP;\n"
            "GRANT READ ON STAGE <db.schema.stage> TO APPLICATION CONTRACT_INTEL_APP;\n"
            "```"
        )

        stage_input = st.text_input(
            "Enter your stage path (DB.SCHEMA.STAGE)",
            key="stage_input",
            placeholder="MY_DB.MY_SCHEMA.MY_STAGE"
        )

        if st.button("Save Stage Configuration", type="primary", key="btn_save_stage"):
            if stage_input and stage_input.count(".") >= 2:
                session.sql(f"CALL config.set_data_stage('{stage_input}')").collect()
                st.success(f"Stage set to: {stage_input}")
                st.rerun()
            else:
                st.error("Please enter a valid fully-qualified stage name (DB.SCHEMA.STAGE)")
        return
    else:
        st.success("Data stage configured.")

    # ── All done ───────────────────────────────────────────────────────────
    st.markdown("### Setup Complete")
    st.success("All permissions granted and stage configured. You're ready to go!")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Explore Demo Data", use_container_width=True, key="setup_done_demo"):
            st.session_state.setup_complete = True
            st.session_state.page = "landing"
            st.rerun()
    with col2:
        if st.button("Upload My Data", type="primary", use_container_width=True, key="setup_done_consumer"):
            session.sql("CALL config.switch_to_consumer()").collect()
            st.session_state.setup_complete = True
            st.session_state.page = "landing"
            st.rerun()


def main():
    # Check setup on launch (unless user already passed setup)
    if not st.session_state.setup_complete:
        if not _all_setup_done():
            render_setup()
            return

    page = st.session_state.get("page", "landing")

    if page == "landing":
        landingpage.render()
    elif page == "dashboard":
        dashboard.render()
    else:
        st.session_state.page = "landing"
        st.rerun()


main()
