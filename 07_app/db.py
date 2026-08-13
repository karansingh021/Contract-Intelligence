# ================================================================================================
# db.py — shared Databricks SQL Warehouse connection helper (plain workspace code)
#
# This is deliberately framework-free: no Databricks Apps, no app.yaml. It works anywhere you
# can `pip install databricks-sql-connector streamlit` and reach your workspace:
#   - `streamlit run app.py` from a Databricks cluster web terminal / Repos
#   - `streamlit run app.py` on your laptop against the workspace over the internet
#   - a notebook cell that just does `import subprocess; subprocess.Popen(["streamlit","run",...])`
#
# Auth is plain Personal Access Token + SQL Warehouse HTTP path, read from environment
# variables so nothing is hardcoded. Set them before launching Streamlit, e.g.:
#
#   export DATABRICKS_HOST="https://<your-workspace>.cloud.databricks.com"
#   export DATABRICKS_TOKEN="dapi********************************"
#   export DATABRICKS_HTTP_PATH="/sql/1.0/warehouses/<warehouse_id>"
#   export DATABRICKS_CATALOG="contract_intelligence"
#   streamlit run app.py
#
# (Get DATABRICKS_HTTP_PATH from: SQL Warehouses -> your warehouse -> Connection details.)
# ================================================================================================

import os
import streamlit as st
from databricks import sql

CATALOG = os.environ.get("DATABRICKS_CATALOG", "contract_intelligence")
RAW_SCHEMA = os.environ.get("DATABRICKS_RAW_SCHEMA", "raw")
ANALYTICS_SCHEMA = os.environ.get("DATABRICKS_ANALYTICS_SCHEMA", "analytics")
GOLD_SCHEMA = os.environ.get("DATABRICKS_GOLD_SCHEMA", "gold")
LLM_ENDPOINT = os.environ.get("DATABRICKS_LLM_ENDPOINT", "databricks-meta-llama-3-3-70b-instruct")


def _get_conn_params():
    """Reads connection details from env vars first; falls back to a sidebar form so the
    app is still usable if you forgot to export them (handy for first-run / demo)."""
    host = os.environ.get("DATABRICKS_HOST")
    token = os.environ.get("DATABRICKS_TOKEN")
    http_path = os.environ.get("DATABRICKS_HTTP_PATH")

    if host and token and http_path:
        return host, token, http_path

    with st.sidebar.expander("⚙️ Databricks connection (not found in env vars)", expanded=True):
        host = st.text_input("Workspace host", value=host or "https://<workspace>.cloud.databricks.com")
        http_path = st.text_input("SQL Warehouse HTTP path", value=http_path or "/sql/1.0/warehouses/xxxxxxxxxxxxxxxx")
        token = st.text_input("Personal access token", value=token or "", type="password")
    return host, token, http_path


def get_connection():
    host, token, http_path = _get_conn_params()
    if not (host and token and http_path):
        st.error("Databricks connection details are incomplete — fill in the sidebar form.")
        st.stop()
    return sql.connect(
        server_hostname=host.replace("https://", "").rstrip("/"),
        http_path=http_path,
        access_token=token,
    )


def run_query(query: str):
    """Returns a pandas DataFrame."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            return cur.fetchall_arrow().to_pandas()


def run_statement(statement: str):
    """For MERGE/INSERT/UPDATE — returns affected row count where the driver reports one."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(statement)
            return cur.rowcount
