# Databricks notebook source
# ================================================================================================
# MODULE 02 — BILLING / CUSTOMER / OPERATIONAL EVENTS INGESTION
# Ports: 02_BILLING_CUSTOMER_TRANSACTIONS_DATA_INGESTION.sql (STEP 3-5)
#
# Source layout expected under VOLUME_PATH (see 00_config for the plug-and-play contract):
#   erp/csv/VBRK_*.csv   -> billing header extract  -> RAW.BILLING_TRANSACTIONS
#   erp/csv/VBRP_*.csv   -> billing line extract     -> (kept as staging only, mirrors original)
#   crm/json/*.json       -> Salesforce account export -> RAW.CUSTOMERS
#   ops/json/*.json       -> operational events export -> RAW.OPERATIONAL_EVENTS
#
# Every load TRUNCATEs + reloads the target table (idempotent, same behaviour as the Snowflake
# version), except this uses `saveAsTable(..., mode="overwrite")` on Delta.
# ================================================================================================

# MAGIC %run ../00_setup/00_config

# COMMAND ----------

import uuid
from pyspark.sql import functions as F
from pyspark.sql.types import *

RAW = f"{CATALOG}.{RAW_SCHEMA}"

# ------------------------------------------------------------------------------------------
# STEP A — BILLING_TRANSACTIONS  (from erp/csv/VBRK_*.csv)
# ------------------------------------------------------------------------------------------
def _safe_list(path):
    try:
        return dbutils.fs.ls(path)
    except Exception:
        return []

vbrk_files = [f.path for f in _safe_list(f"{VOLUME_PATH}/erp/csv/")
              if f.name.upper().startswith("VBRK_") and f.name.lower().endswith(".csv")]

if vbrk_files:
    vbrk = (spark.read
            .option("header", True)
            .option("inferSchema", False)
            .csv(vbrk_files))

    billing_df = (vbrk
        .withColumn("TRANSACTION_ID", F.expr("uuid()"))
        .withColumn("CONTRACT_ID", F.col("CONTRACT_ID"))
        .withColumn("CUSTOMER_ID", F.col("KUNAG"))
        .withColumn("INVOICE_NUMBER", F.col("VBELN"))
        .withColumn("TRANSACTION_DATE", F.to_date(F.col("FKDAT"), "yyyyMMdd"))
        .withColumn("BILLING_PERIOD", F.concat_ws("-", F.col("GJAHR"), F.lpad(F.col("POPER"), 2, "0")))
        .withColumn("SERVICE_TYPE", F.col("INDUSTRY"))
        .withColumn("QUANTITY", F.lit(1))
        .withColumn("UNIT_PRICE", F.col("NETWR").cast("decimal(18,4)"))
        .withColumn("BILLED_AMOUNT", F.col("NETWR").cast("decimal(18,2)"))
        .withColumn("PAYMENT_STATUS",
                    F.when(F.upper(F.coalesce(F.col("HAS_MISMATCH"), F.lit(""))) == "TRUE", "REVIEW")
                     .otherwise("PAID"))
        .withColumn("SAP_DOCUMENT_TYPE", F.col("FKART"))
        .withColumn("SAP_COMPANY_CODE", F.col("BUKRS"))
        .withColumn("LOAD_TIMESTAMP", F.current_timestamp())
        .withColumn("RECORD_SOURCE", F.lit("SAP_S4H_VBRK"))
        .select("TRANSACTION_ID", "CONTRACT_ID", "CUSTOMER_ID", "INVOICE_NUMBER",
                "TRANSACTION_DATE", "BILLING_PERIOD", "SERVICE_TYPE", "QUANTITY",
                "UNIT_PRICE", "BILLED_AMOUNT", "PAYMENT_STATUS", "SAP_DOCUMENT_TYPE",
                "SAP_COMPANY_CODE", "LOAD_TIMESTAMP", "RECORD_SOURCE"))

    # lowercase to match DDL column names
    billing_df = billing_df.toDF(*[c.lower() for c in billing_df.columns])
    billing_df.write.mode("overwrite").saveAsTable(f"{RAW}.billing_transactions")
    print(f"BILLING_TRANSACTIONS loaded: {billing_df.count()} rows")
else:
    print(f"No VBRK_*.csv files found under {VOLUME_PATH}/erp/csv/ — skipping billing load.")

# ------------------------------------------------------------------------------------------
# STEP B — CUSTOMERS  (from crm/json/*.json, "accounts" array — mirrors the demo-data
# enrichment logic in the original script: random industry/segment/region assignment)
# ------------------------------------------------------------------------------------------
crm_files = [f.path for f in _safe_list(f"{VOLUME_PATH}/crm/json/") if f.name.lower().endswith(".json")]

if crm_files:
    crm_raw = spark.read.option("multiLine", True).json(crm_files)

    accounts = crm_raw.select(
        F.explode(F.col("accounts")).alias("account_id"),
        F.col("generated_at"),
        F.col("source_system"),
    )

    industries = F.array(*[F.lit(x) for x in ["TELECOM", "HEALTHCARE", "FINANCE", "RETAIL", "SAAS"]])
    segments = F.array(*[F.lit(x) for x in ["ENTERPRISE", "MID_MARKET", "SMB"]])
    regions = F.array(*[F.lit(x) for x in ["NORTH_AMERICA", "EUROPE", "APAC", "LATAM"]])

    customers_df = (accounts
        .withColumn("CUSTOMER_ID", F.col("account_id").cast("string"))
        .withColumn("CUSTOMER_NAME", F.concat(F.lit("Customer_"), F.expr("right(account_id, 6)")))
        .withColumn("INDUSTRY", industries.getItem((F.rand() * 5).cast("int")))
        .withColumn("SEGMENT", segments.getItem((F.rand() * 3).cast("int")))
        .withColumn("REGION", regions.getItem((F.rand() * 4).cast("int")))
        .withColumn("COUNTRY", F.lit("US"))
        .withColumn("ACCOUNT_MANAGER", F.concat(F.lit("AM_"), (F.rand() * 900 + 100).cast("int")))
        .withColumn("ARR_USD", (F.rand() * 4950000 + 50000).cast("decimal(18,2)"))
        .withColumn("RISK_SCORE", (F.round((F.rand() * 85 + 10) / 10, 1)).cast("decimal(4,1)"))
        .withColumn("SF_ACCOUNT_ID", F.concat(F.lit("SF_"), F.expr("right(account_id, 8)")))
        .withColumn("LOAD_TIMESTAMP",
                    F.coalesce(F.to_timestamp(F.col("generated_at")), F.current_timestamp()))
        .withColumn("RECORD_SOURCE", F.coalesce(F.col("source_system"), F.lit("SALESFORCE_FIVETRAN")))
        .select("CUSTOMER_ID", "CUSTOMER_NAME", "INDUSTRY", "SEGMENT", "REGION", "COUNTRY",
                "ACCOUNT_MANAGER", "ARR_USD", "RISK_SCORE", "SF_ACCOUNT_ID",
                "LOAD_TIMESTAMP", "RECORD_SOURCE"))

    customers_df = customers_df.toDF(*[c.lower() for c in customers_df.columns])
    customers_df.write.mode("overwrite").saveAsTable(f"{RAW}.customers")
    print(f"CUSTOMERS loaded: {customers_df.count()} rows")
else:
    print(f"No *.json files found under {VOLUME_PATH}/crm/json/ — skipping customer load.")

# ------------------------------------------------------------------------------------------
# STEP C — OPERATIONAL_EVENTS  (from ops/json/*.json)
# ------------------------------------------------------------------------------------------
ops_files = [f.path for f in _safe_list(f"{VOLUME_PATH}/ops/json/") if f.name.lower().endswith(".json")]

if ops_files:
    ops_raw = spark.read.option("multiLine", False).json(ops_files)

    events_df = (ops_raw
        .filter(F.col("event_id").isNotNull())
        .select(
            F.col("event_id").cast("string").alias("EVENT_ID"),
            F.col("contract_ref").cast("string").alias("CONTRACT_ID"),
            F.col("customer_ref").cast("string").alias("CUSTOMER_ID"),
            F.col("event_type").cast("string").alias("EVENT_TYPE"),
            F.to_date(F.col("event_date")).alias("EVENT_DATE"),
            F.to_timestamp(F.col("start_timestamp")).alias("START_TIMESTAMP"),
            F.to_timestamp(F.col("end_timestamp")).alias("END_TIMESTAMP"),
            F.col("turnaround_hours").cast("decimal(8,2)").alias("TURNAROUND_HOURS"),
            F.col("procedure_code").cast("string").alias("PROCEDURE_CODE"),
            F.col("service_code").cast("string").alias("SERVICE_CODE"),
            F.col("quantity").cast("decimal(12,4)").alias("QUANTITY"),
            F.col("reported_value").cast("decimal(18,2)").alias("REPORTED_VALUE"),
            F.col("delivery_pct").cast("decimal(5,2)").alias("DELIVERY_PCT"),
            F.col("defect_pct").cast("decimal(5,2)").alias("DEFECT_PCT"),
            F.col("units_ordered").cast("int").alias("UNITS_ORDERED"),
            F.col("uptime_pct").cast("decimal(7,4)").alias("UPTIME_PCT"),
            F.col("user_count").cast("int").alias("USER_COUNT"),
            F.col("overage_units").cast("int").alias("OVERAGE_UNITS"),
            F.col("status").cast("string").alias("STATUS"),
            F.col("record_source").cast("string").alias("RECORD_SOURCE"),
        )
        .withColumn("LOAD_TIMESTAMP", F.current_timestamp()))

    events_df = events_df.toDF(*[c.lower() for c in events_df.columns])
    events_df.write.mode("overwrite").saveAsTable(f"{RAW}.operational_events")
    print(f"OPERATIONAL_EVENTS loaded: {events_df.count()} rows")
else:
    print(f"No *.json files found under {VOLUME_PATH}/ops/json/ — skipping operational events load.")

# ------------------------------------------------------------------------------------------
# Verify
# ------------------------------------------------------------------------------------------
for t in ("customers", "billing_transactions", "operational_events"):
    try:
        n = spark.table(f"{RAW}.{t}").count()
    except Exception:
        n = 0
    print(f"{t:>22}: {n} rows")
