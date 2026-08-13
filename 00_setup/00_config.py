# Databricks notebook source
# ================================================================================================
# MODULE 00 — CONFIG & BOOTSTRAP
# Contract Intelligence & Revenue Leakage Prevention — Databricks port of the Snowflake MVP
#
# DESIGN NOTE (plug-and-play):
#   The original Snowflake project used STORAGE INTEGRATION + EXTERNAL STAGE pointing at a
#   fixed S3 bucket. On Databricks we deliberately DO NOT hardcode any external storage
#   integration. Instead every module reads from ONE Unity Catalog Volume path, passed in as
#   a widget. Point VOLUME_PATH at any UC Volume that has these sub-folders (mirroring the
#   original S3 layout) and everything downstream just works:
#
#       <VOLUME_PATH>/contracts/pdf/*.pdf        (contract PDFs)
#       <VOLUME_PATH>/erp/csv/VBRK_*.csv         (SAP billing header extracts)
#       <VOLUME_PATH>/erp/csv/VBRP_*.csv         (SAP billing line extracts)
#       <VOLUME_PATH>/crm/json/*.json            (Salesforce customer extracts)
#       <VOLUME_PATH>/ops/json/*.json            (operational events extracts)
#
#   If a sub-folder doesn't exist / is empty, that module just loads zero rows — nothing
#   breaks. Re-running any module is always safe (idempotent truncate + reload / MERGE).
# ================================================================================================

dbutils.widgets.text("catalog", "contract_intelligence", "Unity Catalog name")
dbutils.widgets.text("raw_schema", "raw", "Raw schema")
dbutils.widgets.text("analytics_schema", "analytics", "Analytics schema")
dbutils.widgets.text("gold_schema", "gold", "Gold schema")
dbutils.widgets.text("simple_alerting_schema", "simple_alerting", "Alerting schema")
dbutils.widgets.text("volume_name", "landing", "UC Volume name (created if absent)")
dbutils.widgets.text("volume_path", "", "Full UC Volume path (leave blank to auto-derive)")
dbutils.widgets.text("llm_endpoint", "databricks-meta-llama-3-3-70b-instruct",
                      "Databricks Foundation Model serving endpoint")
dbutils.widgets.text("alert_recipient", "", "Email address for revenue-leakage alerts")

CATALOG = dbutils.widgets.get("catalog")
RAW_SCHEMA = dbutils.widgets.get("raw_schema")
ANALYTICS_SCHEMA = dbutils.widgets.get("analytics_schema")
GOLD_SCHEMA = dbutils.widgets.get("gold_schema")
ALERTING_SCHEMA = dbutils.widgets.get("simple_alerting_schema")
VOLUME_NAME = dbutils.widgets.get("volume_name")
LLM_ENDPOINT = dbutils.widgets.get("llm_endpoint")
ALERT_RECIPIENT = dbutils.widgets.get("alert_recipient")

# ------------------------------------------------------------------------------------------
# Bootstrap catalog / schemas / volume. Everything is created IF NOT EXISTS — safe to re-run.
# ------------------------------------------------------------------------------------------
spark.sql(f"CREATE CATALOG IF NOT EXISTS {CATALOG}")
for schema in (RAW_SCHEMA, ANALYTICS_SCHEMA, GOLD_SCHEMA, ALERTING_SCHEMA):
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{schema}")

spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.{RAW_SCHEMA}.{VOLUME_NAME}")

_volume_path_widget = dbutils.widgets.get("volume_path").strip()
VOLUME_PATH = _volume_path_widget if _volume_path_widget else f"/Volumes/{CATALOG}/{RAW_SCHEMA}/{VOLUME_NAME}"

# Create the expected sub-folder layout if it doesn't exist yet, so first-run users have
# somewhere obvious to drop files.
for sub in ("contracts/pdf", "erp/csv", "crm/json", "ops/json"):
    dbutils.fs.mkdirs(f"{VOLUME_PATH}/{sub}")

print(f"Catalog            : {CATALOG}")
print(f"Schemas            : {RAW_SCHEMA} | {ANALYTICS_SCHEMA} | {GOLD_SCHEMA} | {ALERTING_SCHEMA}")
print(f"Volume path        : {VOLUME_PATH}")
print(f"LLM serving endpoint: {LLM_ENDPOINT}")
print("Drop your source files into:")
print(f"  {VOLUME_PATH}/contracts/pdf/   -> *.pdf")
print(f"  {VOLUME_PATH}/erp/csv/         -> VBRK_*.csv, VBRP_*.csv")
print(f"  {VOLUME_PATH}/crm/json/        -> *.json (customer/account extracts)")
print(f"  {VOLUME_PATH}/ops/json/        -> *.json (operational event extracts)")

# ------------------------------------------------------------------------------------------
# Expose config to other notebooks via %run ./00_config, or via importable dict when used
# as a Python module inside a Databricks Job task.
# ------------------------------------------------------------------------------------------
CONFIG = dict(
    catalog=CATALOG,
    raw_schema=RAW_SCHEMA,
    analytics_schema=ANALYTICS_SCHEMA,
    gold_schema=GOLD_SCHEMA,
    alerting_schema=ALERTING_SCHEMA,
    volume_path=VOLUME_PATH,
    llm_endpoint=LLM_ENDPOINT,
    alert_recipient=ALERT_RECIPIENT,
)
