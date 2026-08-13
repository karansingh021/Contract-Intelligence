# Databricks notebook source
# ================================================================================================
# MODULE 07 — GOLD ANALYTICS VIEWS (pre-aggregated for the dashboard)
# Ports: 04_DASHBOARD_VIEWS.sql SECTION C
# ================================================================================================

# MAGIC %run ../00_setup/00_config

# COMMAND ----------

RAW = f"{CATALOG}.{RAW_SCHEMA}"
ANALYTICS = f"{CATALOG}.{ANALYTICS_SCHEMA}"
GOLD = f"{CATALOG}.{GOLD_SCHEMA}"

spark.sql(f"""
CREATE OR REPLACE VIEW {GOLD}.gold_portfolio_kpi AS
SELECT
    COUNT(DISTINCT c.contract_id)                          AS total_contracts,
    SUM(c.annual_value_usd)                                AS portfolio_value_usd,
    COALESCE(SUM(lr.leakage_amount_usd), 0)                AS total_leakage_usd,
    COUNT(DISTINCT lr.event_ref)                            AS total_leakage_events,
    ROUND(COALESCE(SUM(lr.leakage_amount_usd),0) / NULLIF(SUM(c.annual_value_usd),0) * 100, 3) AS leakage_rate_pct,
    COUNT(CASE WHEN lr.severity = 'CRITICAL' THEN 1 END)   AS critical_events,
    COUNT(CASE WHEN lr.severity = 'HIGH'     THEN 1 END)   AS high_events,
    COUNT(CASE WHEN lr.severity = 'MEDIUM'   THEN 1 END)   AS medium_events,
    COUNT(CASE WHEN lr.severity = 'LOW'      THEN 1 END)   AS low_events
FROM {RAW}.contracts c
LEFT JOIN {ANALYTICS}.leakage_register lr ON lr.contract_id = c.contract_id
""")

spark.sql(f"""
CREATE OR REPLACE VIEW {GOLD}.gold_by_industry AS
SELECT
    cu.industry,
    COUNT(DISTINCT c.contract_id)                          AS contracts,
    SUM(c.annual_value_usd)                                AS portfolio_usd,
    COALESCE(SUM(lr.leakage_amount_usd), 0)                AS leakage_usd,
    ROUND(COALESCE(SUM(lr.leakage_amount_usd),0) / NULLIF(SUM(c.annual_value_usd),0) * 100, 2) AS leakage_pct,
    COUNT(DISTINCT lr.event_ref)                            AS events
FROM {RAW}.contracts  c
JOIN {RAW}.customers  cu ON cu.customer_id = c.customer_id
LEFT JOIN {ANALYTICS}.leakage_register lr ON lr.contract_id = c.contract_id
GROUP BY cu.industry
""")

spark.sql(f"""
CREATE OR REPLACE VIEW {GOLD}.gold_by_rule AS
SELECT
    rule_id, rule_name, leakage_type,
    COUNT(*)                    AS event_count,
    SUM(leakage_amount_usd)     AS total_usd,
    ROUND(AVG(leakage_amount_usd), 2) AS avg_usd,
    MAX(leakage_amount_usd)     AS max_usd
FROM {ANALYTICS}.leakage_register
GROUP BY rule_id, rule_name, leakage_type
ORDER BY total_usd DESC
""")

spark.sql(f"""
CREATE OR REPLACE VIEW {GOLD}.gold_by_customer AS
SELECT
    lr.customer_name, lr.industry, lr.contract_id,
    COUNT(DISTINCT lr.event_ref)      AS events,
    SUM(lr.leakage_amount_usd)        AS total_leakage_usd,
    MAX(lr.severity)                  AS worst_severity,
    array_join(collect_set(lr.leakage_type), ' | ') AS leakage_types
FROM {ANALYTICS}.leakage_register lr
GROUP BY lr.customer_name, lr.industry, lr.contract_id
ORDER BY total_leakage_usd DESC
""")

print("GOLD views created in", GOLD)
