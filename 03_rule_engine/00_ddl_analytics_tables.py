# Databricks notebook source
# ================================================================================================
# MODULE 06a — ANALYTICS SCHEMA DDL
# Ports: 02_RULE_ENGINE_TABLES.sql — LEAKAGE_EVENTS, ALERT_LOG, CREDIT_NOTES
# ================================================================================================

# MAGIC %run ../00_setup/00_config

# COMMAND ----------

ANALYTICS = f"{CATALOG}.{ANALYTICS_SCHEMA}"

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {ANALYTICS}.leakage_events (
    leakage_id           STRING NOT NULL,
    rule_id              STRING NOT NULL COMMENT 'R01..R06',
    rule_name            STRING NOT NULL,
    event_ref             STRING NOT NULL COMMENT 'FK -> OPERATIONAL_EVENTS or BILLING_TRANSACTIONS',
    contract_id           STRING NOT NULL,
    customer_id            STRING NOT NULL,
    customer_name           STRING,
    industry                 STRING,
    leakage_type              STRING NOT NULL COMMENT 'SLA_BREACH | BILLING_MISMATCH | OVERAGE | etc.',
    leakage_amount_usd         DECIMAL(18,2) NOT NULL,
    severity                    STRING NOT NULL COMMENT 'CRITICAL | HIGH | MEDIUM | LOW',
    event_date                   DATE,
    calculation_detail            STRING,
    detected_at                    TIMESTAMP
) USING DELTA
""")

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {ANALYTICS}.alert_log (
    alert_id             STRING NOT NULL,
    leakage_id           STRING NOT NULL,
    contract_id           STRING,
    customer_name          STRING,
    alert_type              STRING,
    severity                 STRING,
    leakage_amount_usd        DECIMAL(18,2),
    alert_message              STRING,
    sent_to                     STRING,
    alert_channel                 STRING,
    status                        STRING,
    created_at                     TIMESTAMP,
    resolved_at                     TIMESTAMP
) USING DELTA
""")

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {ANALYTICS}.credit_notes (
    credit_note_id       STRING NOT NULL,
    leakage_id           STRING NOT NULL,
    contract_id           STRING,
    customer_name          STRING,
    credit_type              STRING COMMENT 'PENALTY_CREDIT | BILLING_ADJUSTMENT | BONUS_PAYMENT',
    credit_amount_usd         DECIMAL(18,2),
    justification               STRING,
    status                        STRING,
    generated_by                   STRING,
    created_at                      TIMESTAMP,
    approved_at                      TIMESTAMP,
    approved_by                       STRING,
    erp_sync_status                    STRING
) USING DELTA
""")

print("ANALYTICS schema tables created/verified in", ANALYTICS)
