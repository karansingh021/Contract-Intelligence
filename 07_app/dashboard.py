# ================================================================================================
# dashboard.py — main analytics screen. Port of DASHBOARD.PY structure (render() pattern),
# load_kpi/load_register/load_alerts/load_credits queries, sidebar "Generate Leakage" action,
# and the Cortex-powered chat assistant (here: ai_query against a Databricks serving endpoint).
# ================================================================================================

import streamlit as st
import pandas as pd
from db import run_query, run_statement, CATALOG, RAW_SCHEMA, ANALYTICS_SCHEMA, GOLD_SCHEMA, LLM_ENDPOINT

RAW = f"{CATALOG}.{RAW_SCHEMA}"
ANALYTICS = f"{CATALOG}.{ANALYTICS_SCHEMA}"
GOLD = f"{CATALOG}.{GOLD_SCHEMA}"


# ------------------------------------------------------------------------------------------
# Data loaders — mirror DASHBOARD.PY's load_kpi() / load_register() / load_alerts() / load_credits()
# ------------------------------------------------------------------------------------------
@st.cache_data(ttl=60)
def load_kpi():
    return run_query(f"SELECT * FROM {GOLD}.gold_portfolio_kpi")


@st.cache_data(ttl=60)
def load_by_industry():
    return run_query(f"SELECT * FROM {GOLD}.gold_by_industry ORDER BY leakage_usd DESC")


@st.cache_data(ttl=60)
def load_by_rule():
    return run_query(f"SELECT * FROM {GOLD}.gold_by_rule")


@st.cache_data(ttl=60)
def load_by_customer():
    return run_query(f"SELECT * FROM {GOLD}.gold_by_customer LIMIT 25")


@st.cache_data(ttl=60)
def load_register():
    return run_query(f"""
        SELECT rule_id, rule_name, event_ref, contract_id, customer_name, industry,
               leakage_type, leakage_amount_usd, severity, event_date, calculation_detail
        FROM {ANALYTICS}.leakage_register
        ORDER BY leakage_amount_usd DESC
        LIMIT 500
    """)


@st.cache_data(ttl=60)
def load_alerts():
    return run_query(f"""
        SELECT alert_type, severity, customer_name, leakage_amount_usd,
               alert_message, status, created_at
        FROM {ANALYTICS}.alert_log
        ORDER BY created_at DESC
        LIMIT 500
    """)


@st.cache_data(ttl=60)
def load_credits():
    return run_query(f"""
        SELECT credit_type, customer_name, contract_id, credit_amount_usd,
               justification, status, created_at
        FROM {ANALYTICS}.credit_notes
        ORDER BY created_at DESC
        LIMIT 500
    """)


# ------------------------------------------------------------------------------------------
# AI assistant — replaces SNOWFLAKE.CORTEX.COMPLETE with ai_query() against a Databricks
# Foundation Model serving endpoint. Same idea as _build_system_context()/call_cortex() in
# the original: give the model the current KPI snapshot so its answers are grounded.
# ------------------------------------------------------------------------------------------
def _build_system_context(kpi_row: dict) -> str:
    return (
        "You are a revenue-leakage analyst assistant for a contract intelligence platform. "
        "Answer using ONLY the KPI snapshot below; if something isn't in it, say you don't "
        "have that data rather than guessing.\n\n"
        f"KPI SNAPSHOT: {kpi_row}"
    )


def call_llm(prompt: str, kpi_row: dict) -> str:
    system_context = _build_system_context(kpi_row).replace("'", "''")
    user_prompt = prompt.replace("'", "''")
    sql = f"""
        SELECT ai_query(
            '{LLM_ENDPOINT}',
            CONCAT('{system_context}', '\\n\\nQuestion: ', '{user_prompt}')
        ) AS response
    """
    try:
        result = run_query(sql)
        return result.iloc[0]["response"]
    except Exception as e:
        return f"(AI assistant unavailable: {e})"


# ------------------------------------------------------------------------------------------
# render()
# ------------------------------------------------------------------------------------------
def render():
    with st.sidebar:
        st.markdown("### ◈ Contract Intelligence")
        if st.button("← Back to landing"):
            st.session_state.page = "landing"
            st.rerun()

        st.markdown("---")
        st.markdown("**Rule engine**")
        if st.button("🔄 Run Rule Engine (GENERATE_LEAKAGE)", use_container_width=True):
            with st.spinner("Materialising leakage events, alerts, credit notes..."):
                try:
                    # Step 1: MERGE new leakage events (dedup on rule_id + event_ref)
                    run_statement(f"""
                        MERGE INTO {ANALYTICS}.leakage_events tgt
                        USING (
                            SELECT uuid() AS leakage_id, rule_id, rule_name, event_ref, contract_id,
                                   customer_id, customer_name, industry, leakage_type,
                                   leakage_amount_usd, severity, event_date, calculation_detail,
                                   current_timestamp() AS detected_at
                            FROM {ANALYTICS}.leakage_register
                        ) src
                        ON tgt.rule_id = src.rule_id AND tgt.event_ref = src.event_ref
                        WHEN NOT MATCHED THEN INSERT (
                            leakage_id, rule_id, rule_name, event_ref, contract_id, customer_id,
                            customer_name, industry, leakage_type, leakage_amount_usd, severity,
                            event_date, calculation_detail, detected_at
                        ) VALUES (
                            src.leakage_id, src.rule_id, src.rule_name, src.event_ref, src.contract_id,
                            src.customer_id, src.customer_name, src.industry, src.leakage_type,
                            src.leakage_amount_usd, src.severity, src.event_date, src.calculation_detail,
                            src.detected_at
                        )
                    """)
                    # Step 2: alerts for new leakage >= $100
                    run_statement(f"""
                        INSERT INTO {ANALYTICS}.alert_log
                            (alert_id, leakage_id, contract_id, customer_name, alert_type, severity,
                             leakage_amount_usd, alert_message, alert_channel, status, created_at)
                        SELECT uuid(), le.leakage_id, le.contract_id, le.customer_name, le.leakage_type,
                               le.severity, le.leakage_amount_usd,
                               concat('LEAKAGE DETECTED | ', le.rule_name, ' | Customer: ', le.customer_name,
                                      ' | $', format_number(le.leakage_amount_usd,2), ' | Severity: ', le.severity),
                               'EMAIL', 'PENDING', current_timestamp()
                        FROM {ANALYTICS}.leakage_events le
                        LEFT JOIN {ANALYTICS}.alert_log al ON al.leakage_id = le.leakage_id
                        WHERE al.alert_id IS NULL AND le.leakage_amount_usd >= 100
                    """)
                    # Step 3: credit notes for HIGH/CRITICAL >= $500
                    run_statement(f"""
                        INSERT INTO {ANALYTICS}.credit_notes
                            (credit_note_id, leakage_id, contract_id, customer_name, credit_type,
                             credit_amount_usd, justification, status, generated_by, created_at, erp_sync_status)
                        SELECT uuid(), le.leakage_id, le.contract_id, le.customer_name,
                               CASE le.leakage_type
                                   WHEN 'OVERBILLED' THEN 'BILLING_ADJUSTMENT'
                                   WHEN 'UNDERBILLED' THEN 'BILLING_ADJUSTMENT'
                                   WHEN 'TELECOM_USER_OVERAGE' THEN 'BILLING_ADJUSTMENT'
                                   WHEN 'SAAS_SEAT_OVERAGE' THEN 'BILLING_ADJUSTMENT'
                                   WHEN 'BONUS_UNCLAIMED' THEN 'BONUS_PAYMENT'
                                   ELSE 'PENALTY_CREDIT' END,
                               le.leakage_amount_usd,
                               concat(le.rule_name, ' | ', le.leakage_type, ' | Contract: ', le.contract_id,
                                      ' | ', le.calculation_detail),
                               'DRAFT', 'RULE_ENGINE', current_timestamp(), 'PENDING'
                        FROM {ANALYTICS}.leakage_events le
                        LEFT JOIN {ANALYTICS}.credit_notes cn ON cn.leakage_id = le.leakage_id
                        WHERE cn.credit_note_id IS NULL AND le.severity IN ('CRITICAL','HIGH')
                          AND le.leakage_amount_usd >= 500
                    """)
                    st.success("Rule engine run complete.")
                    st.cache_data.clear()
                except Exception as e:
                    st.error(f"Rule engine run failed: {e}")

        st.markdown("---")
        st.caption(f"Catalog: `{CATALOG}`")

    st.title("Revenue Leakage Dashboard")

    # KPI row
    try:
        kpi = load_kpi().iloc[0]
    except Exception:
        kpi = None

    if kpi is not None:
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Total contracts", f"{int(kpi['total_contracts']):,}")
        c2.metric("Portfolio value", f"${kpi['portfolio_value_usd']:,.0f}")
        c3.metric("Total leakage", f"${kpi['total_leakage_usd']:,.0f}")
        c4.metric("Leakage rate", f"{kpi['leakage_rate_pct'] or 0:.2f}%")
        c5.metric("Critical events", f"{int(kpi['critical_events']):,}")
    else:
        st.warning("GOLD views not reachable yet — run the pipeline modules first.")
        return

    st.markdown("### Leakage by industry")
    by_industry = load_by_industry()
    if not by_industry.empty:
        st.bar_chart(by_industry.set_index("industry")["leakage_usd"])

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("### Leakage by rule")
        by_rule = load_by_rule()
        if not by_rule.empty:
            st.dataframe(by_rule, use_container_width=True, hide_index=True)
    with col_b:
        st.markdown("### Top customers by leakage")
        by_customer = load_by_customer()
        if not by_customer.empty:
            st.dataframe(by_customer, use_container_width=True, hide_index=True)

    st.markdown("---")
    tab1, tab2, tab3, tab4 = st.tabs(
        ["📋 Full Issue Register", "🔔 Alert Log", "📄 Credit Notes", "🤖 AI Assistant"]
    )

    with tab1:
        st.dataframe(load_register(), use_container_width=True, hide_index=True)

    with tab2:
        st.dataframe(load_alerts(), use_container_width=True, hide_index=True)

    with tab3:
        st.dataframe(load_credits(), use_container_width=True, hide_index=True)

    with tab4:
        st.caption("Ask questions about the current KPI snapshot (grounded — won't invent numbers).")
        for role, msg in st.session_state.chat_history:
            with st.chat_message(role):
                st.markdown(msg)

        prompt = st.chat_input("e.g. Which industry has the highest leakage rate?")
        if prompt:
            st.session_state.chat_history.append(("user", prompt))
            with st.chat_message("user"):
                st.markdown(prompt)
            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    answer = call_llm(prompt, kpi.to_dict())
                st.markdown(answer)
            st.session_state.chat_history.append(("assistant", answer))
