# ================================================================================================
# landingpage.py — hero / entry screen. Port of LANDINGPAGE.PY structure: everything lives
# inside render(), nothing runs at import time.
# ================================================================================================

import streamlit as st
from db import run_query


def render():
    st.markdown(
        """
        <div style="text-align:center; padding: 60px 0 20px 0;">
            <h1 style="font-size:2.6rem;">◈ Contract Intelligence</h1>
            <h3 style="color:#888; font-weight:400;">Autonomous Revenue Leakage Prevention</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns(3)
    try:
        kpi = run_query(f"SELECT * FROM {st_catalog_kpi()}").iloc[0]
        col1.metric("Contracts under management", f"{int(kpi['total_contracts']):,}")
        col2.metric("Revenue leakage detected", f"${kpi['total_leakage_usd']:,.0f}")
        col3.metric("Leakage rate", f"{kpi['leakage_rate_pct']:.2f}%")
    except Exception:
        col1.metric("Contracts under management", "—")
        col2.metric("Revenue leakage detected", "—")
        col3.metric("Leakage rate", "—")
        st.caption("Run the pipeline (modules 00-08) at least once to populate the GOLD views.")

    st.markdown("<br>", unsafe_allow_html=True)
    _, mid, _ = st.columns([1, 1, 1])
    with mid:
        if st.button("Enter Dashboard →", use_container_width=True, type="primary"):
            st.session_state.page = "dashboard"
            st.rerun()

    st.markdown("<br><hr>", unsafe_allow_html=True)
    st.markdown(
        """
        **What this platform does**
        - Reads contract PDFs, SAP billing extracts, CRM customer data and operational events
          from a single Unity Catalog Volume.
        - Uses a Databricks Foundation Model endpoint to extract structured contract terms
          (dates, values, SLAs, renewal clauses) from unstructured PDF text.
        - Runs 6 revenue-leakage detection rules (SLA breach penalties, unclaimed bonuses,
          billing mismatches, unbilled overages, delivery/defect SLA breaches) against live
          billing and operational data.
        - Surfaces every detected leakage event, auto-drafted credit note, and alert here.
        """
    )


def st_catalog_kpi():
    from db import CATALOG, GOLD_SCHEMA
    return f"{CATALOG}.{GOLD_SCHEMA}.gold_portfolio_kpi"
