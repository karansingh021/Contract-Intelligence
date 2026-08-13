# Databricks notebook source
# ================================================================================================
# MODULE 06b — RULE ENGINE VIEWS (R01-R06) + LEAKAGE_REGISTER
# Ports: 03_ANALYTICS.sql SECTION A + SECTION B — logic and thresholds are unchanged, only
# Snowflake-specific syntax (||, IFF, ILIKE) is swapped for Databricks SQL equivalents
# (concat/CASE). All dollar thresholds, formulas and severity bands are identical.
# ================================================================================================

# MAGIC %run ../00_setup/00_config

# COMMAND ----------

RAW = f"{CATALOG}.{RAW_SCHEMA}"
ANALYTICS = f"{CATALOG}.{ANALYTICS_SCHEMA}"

# ------------------------------------------------------------------------------------------
# R01 — SLA BREACH PENALTY (Healthcare CLAIM / Telecom INCIDENT)
#   leakage = reported_value * (penalty_pct / 100), fires when turnaround_hours > sla_hours
# ------------------------------------------------------------------------------------------
spark.sql(f"""
CREATE OR REPLACE VIEW {ANALYTICS}.rule_r01_sla_breach AS
SELECT
    'R01' AS rule_id, 'SLA Breach — Penalty Due' AS rule_name,
    e.event_id AS event_ref, e.contract_id, e.customer_id, cu.customer_name, cu.industry,
    c.contract_type, e.event_type, e.event_date,
    e.turnaround_hours AS actual_hours, c.sla_hours AS sla_threshold_hours,
    ROUND(e.turnaround_hours - c.sla_hours, 2) AS breach_hours,
    e.reported_value AS transaction_value, c.penalty_pct,
    ROUND(e.reported_value * (c.penalty_pct / 100), 2) AS leakage_amount_usd,
    CASE
        WHEN ROUND(e.reported_value * (c.penalty_pct/100),2) > 100000 THEN 'CRITICAL'
        WHEN ROUND(e.reported_value * (c.penalty_pct/100),2) > 10000  THEN 'HIGH'
        WHEN ROUND(e.reported_value * (c.penalty_pct/100),2) > 500    THEN 'MEDIUM'
        ELSE 'LOW'
    END AS severity,
    'SLA_BREACH_PENALTY' AS leakage_type,
    concat('SLA breach: ', e.turnaround_hours, ' hrs actual vs ', c.sla_hours, ' hrs SLA. Breach = ',
           ROUND(e.turnaround_hours - c.sla_hours, 1), ' hrs. Penalty = $', e.reported_value, ' x ',
           c.penalty_pct, '% = $', ROUND(e.reported_value * (c.penalty_pct/100), 2)) AS calculation_detail
FROM {RAW}.operational_events e
JOIN {RAW}.contracts c  ON c.contract_id  = e.contract_id
JOIN {RAW}.customers cu ON cu.customer_id = e.customer_id
WHERE e.turnaround_hours IS NOT NULL AND c.sla_hours IS NOT NULL AND c.penalty_pct IS NOT NULL
  AND e.turnaround_hours > c.sla_hours AND e.reported_value > 0
""")

# ------------------------------------------------------------------------------------------
# R02 — Q4 BONUS ELIGIBLE (UNCLAIMED)
# ------------------------------------------------------------------------------------------
spark.sql(f"""
CREATE OR REPLACE VIEW {ANALYTICS}.rule_r02_bonus_eligible AS
SELECT
    'R02' AS rule_id, 'Q4 Bonus — Unclaimed' AS rule_name,
    e.event_id AS event_ref, e.contract_id, e.customer_id, cu.customer_name, cu.industry,
    c.contract_type, e.event_type, e.event_date,
    e.turnaround_hours AS actual_hours, c.bonus_threshold_hrs AS sla_threshold_hours,
    ROUND(c.bonus_threshold_hrs - e.turnaround_hours, 2) AS breach_hours,
    e.reported_value AS transaction_value, c.bonus_pct AS penalty_pct,
    ROUND(e.reported_value * (c.bonus_pct / 100), 2) AS leakage_amount_usd,
    'LOW' AS severity, 'BONUS_UNCLAIMED' AS leakage_type,
    concat('Q4 bonus eligible: TAT ', e.turnaround_hours, ' hrs < ', c.bonus_threshold_hrs,
           ' hr threshold. Bonus = $', e.reported_value, ' x ', c.bonus_pct, '% = $',
           ROUND(e.reported_value * (c.bonus_pct/100), 2)) AS calculation_detail
FROM {RAW}.operational_events e
JOIN {RAW}.contracts c  ON c.contract_id  = e.contract_id
JOIN {RAW}.customers cu ON cu.customer_id = e.customer_id
WHERE e.turnaround_hours IS NOT NULL AND c.bonus_pct IS NOT NULL AND c.bonus_threshold_hrs IS NOT NULL
  AND e.turnaround_hours < c.bonus_threshold_hrs
  AND MONTH(e.event_date) IN (10, 11, 12)
  AND e.reported_value > 0
""")

# ------------------------------------------------------------------------------------------
# R03 — BILLING MISMATCH (OVERBILLED / UNDERBILLED)
#   expected = quantity * contracted unit_rate ; mismatch = billed - expected
# ------------------------------------------------------------------------------------------
spark.sql(f"""
CREATE OR REPLACE VIEW {ANALYTICS}.rule_r03_billing_mismatch AS
WITH computed AS (
    SELECT
        bt.transaction_id, bt.contract_id, bt.customer_id, bt.transaction_date,
        bt.billing_period, bt.service_type, bt.quantity, bt.unit_price AS billed_unit_price,
        bt.billed_amount, c.unit_rate_usd AS contracted_unit_rate,
        ROUND(bt.quantity * c.unit_rate_usd, 2) AS expected_amount,
        bt.billed_amount - ROUND(bt.quantity * c.unit_rate_usd, 2) AS mismatch_amount
    FROM {RAW}.billing_transactions bt
    JOIN {RAW}.contracts c ON c.contract_id = bt.contract_id
    WHERE c.unit_rate_usd IS NOT NULL AND bt.quantity IS NOT NULL
)
SELECT
    'R03' AS rule_id, 'Billing Mismatch' AS rule_name,
    co.transaction_id AS event_ref, co.contract_id, co.customer_id, cu.customer_name, cu.industry,
    c.contract_type, 'BILLING' AS event_type, co.transaction_date AS event_date,
    CAST(NULL AS DOUBLE) AS actual_hours, CAST(NULL AS DOUBLE) AS sla_threshold_hours,
    CAST(NULL AS DOUBLE) AS breach_hours,
    co.billed_amount AS transaction_value, CAST(NULL AS DOUBLE) AS penalty_pct,
    ABS(co.mismatch_amount) AS leakage_amount_usd,
    CASE
        WHEN ABS(co.mismatch_amount) > 100000 THEN 'CRITICAL'
        WHEN ABS(co.mismatch_amount) > 10000  THEN 'HIGH'
        WHEN ABS(co.mismatch_amount) > 1000   THEN 'MEDIUM'
        ELSE 'LOW'
    END AS severity,
    CASE WHEN co.mismatch_amount > 0 THEN 'OVERBILLED' ELSE 'UNDERBILLED' END AS leakage_type,
    concat(CASE WHEN co.mismatch_amount > 0 THEN 'Overbilled: ' ELSE 'Underbilled: ' END,
           'Billed $', co.billed_amount, ' vs expected $', co.expected_amount, ' (', co.quantity,
           ' x $', co.contracted_unit_rate, '). Delta = $', ABS(co.mismatch_amount)) AS calculation_detail
FROM computed co
JOIN {RAW}.contracts c  ON c.contract_id  = co.contract_id
JOIN {RAW}.customers cu ON cu.customer_id = co.customer_id
WHERE ABS(co.mismatch_amount) > 0.01
""")

# ------------------------------------------------------------------------------------------
# R04 — OVERAGE UNBILLED (Telecom user overage / SaaS seat overage)
# ------------------------------------------------------------------------------------------
spark.sql(f"""
CREATE OR REPLACE VIEW {ANALYTICS}.rule_r04_overage_unbilled AS
SELECT
    'R04' AS rule_id, 'Overage — Unbilled Revenue' AS rule_name,
    e.event_id AS event_ref, e.contract_id, e.customer_id, cu.customer_name, cu.industry,
    c.contract_type, e.event_type, e.event_date,
    CAST(e.user_count AS DOUBLE) AS actual_hours, CAST(c.contracted_units AS DOUBLE) AS sla_threshold_hours,
    CAST(e.overage_units AS DOUBLE) AS breach_hours,
    e.reported_value AS transaction_value, CAST(NULL AS DOUBLE) AS penalty_pct,
    ROUND(e.overage_units * c.overage_rate_usd, 2) AS leakage_amount_usd,
    CASE
        WHEN ROUND(e.overage_units * c.overage_rate_usd,2) > 100000 THEN 'CRITICAL'
        WHEN ROUND(e.overage_units * c.overage_rate_usd,2) > 10000  THEN 'HIGH'
        ELSE 'MEDIUM'
    END AS severity,
    CASE
        WHEN cu.industry = 'TELECOM' THEN 'TELECOM_USER_OVERAGE'
        WHEN cu.industry = 'SAAS'    THEN 'SAAS_SEAT_OVERAGE'
        ELSE 'UNIT_OVERAGE'
    END AS leakage_type,
    concat('Overage: ', e.user_count, ' actual vs ', c.contracted_units, ' contracted. ',
           e.overage_units, ' overage units x $', c.overage_rate_usd, ' = $',
           ROUND(e.overage_units * c.overage_rate_usd, 2)) AS calculation_detail
FROM {RAW}.operational_events e
JOIN {RAW}.contracts c  ON c.contract_id  = e.contract_id
JOIN {RAW}.customers cu ON cu.customer_id = e.customer_id
WHERE e.overage_units IS NOT NULL AND e.overage_units > 0
  AND c.overage_rate_usd IS NOT NULL AND c.contracted_units IS NOT NULL
""")

# ------------------------------------------------------------------------------------------
# R05 — DELIVERY SLA BREACH (Manufacturing)
# ------------------------------------------------------------------------------------------
spark.sql(f"""
CREATE OR REPLACE VIEW {ANALYTICS}.rule_r05_delivery_sla AS
WITH calc AS (
    SELECT e.*, c.delivery_sla_pct, c.penalty_pct, c.unit_rate_usd,
        ROUND(e.units_ordered * (1 - e.delivery_pct/100), 0) AS late_units,
        ROUND(e.units_ordered * (1 - e.delivery_pct/100) * c.unit_rate_usd * (c.penalty_pct/100), 2) AS penalty_amount
    FROM {RAW}.operational_events e
    JOIN {RAW}.contracts c ON c.contract_id = e.contract_id
    WHERE e.delivery_pct IS NOT NULL AND c.delivery_sla_pct IS NOT NULL
      AND e.delivery_pct < c.delivery_sla_pct
)
SELECT
    'R05' AS rule_id, 'Delivery SLA Breach' AS rule_name,
    ca.event_id AS event_ref, ca.contract_id, ca.customer_id, cu.customer_name, cu.industry,
    c.contract_type, ca.event_type, ca.event_date,
    ca.delivery_pct AS actual_hours, ca.delivery_sla_pct AS sla_threshold_hours,
    ROUND(ca.delivery_sla_pct - ca.delivery_pct, 2) AS breach_hours,
    ROUND(ca.units_ordered * ca.unit_rate_usd, 2) AS transaction_value,
    ca.penalty_pct, ca.penalty_amount AS leakage_amount_usd,
    CASE WHEN ca.penalty_amount > 100000 THEN 'CRITICAL' WHEN ca.penalty_amount > 10000 THEN 'HIGH' ELSE 'MEDIUM' END AS severity,
    'DELIVERY_SLA_BREACH' AS leakage_type,
    concat('Delivery: ', ca.delivery_pct, '% actual vs ', ca.delivery_sla_pct, '% SLA. ',
           ca.late_units, ' late units x $', ca.unit_rate_usd, ' x ', ca.penalty_pct, '% = $', ca.penalty_amount) AS calculation_detail
FROM calc ca
JOIN {RAW}.contracts c  ON c.contract_id  = ca.contract_id
JOIN {RAW}.customers cu ON cu.customer_id = ca.customer_id
""")

# ------------------------------------------------------------------------------------------
# R06 — DEFECT THRESHOLD BREACH (Manufacturing)
# ------------------------------------------------------------------------------------------
spark.sql(f"""
CREATE OR REPLACE VIEW {ANALYTICS}.rule_r06_defect_breach AS
WITH calc AS (
    SELECT e.*, c.defect_sla_pct, c.penalty_pct, c.unit_rate_usd,
        FLOOR((e.defect_pct - c.defect_sla_pct) / 0.1) AS penalty_units,
        ROUND(FLOOR((e.defect_pct - c.defect_sla_pct) / 0.1) * e.units_ordered * c.unit_rate_usd * (c.penalty_pct / 100), 2) AS penalty_amount
    FROM {RAW}.operational_events e
    JOIN {RAW}.contracts c ON c.contract_id = e.contract_id
    WHERE e.defect_pct IS NOT NULL AND c.defect_sla_pct IS NOT NULL AND e.defect_pct > c.defect_sla_pct
)
SELECT
    'R06' AS rule_id, 'Defect Threshold Breach' AS rule_name,
    ca.event_id AS event_ref, ca.contract_id, ca.customer_id, cu.customer_name, cu.industry,
    c.contract_type, ca.event_type, ca.event_date,
    ca.defect_pct AS actual_hours, ca.defect_sla_pct AS sla_threshold_hours,
    ROUND(ca.defect_pct - ca.defect_sla_pct, 3) AS breach_hours,
    ROUND(ca.units_ordered * ca.unit_rate_usd, 2) AS transaction_value,
    ca.penalty_pct, ca.penalty_amount AS leakage_amount_usd,
    CASE WHEN ca.penalty_amount > 100000 THEN 'CRITICAL' WHEN ca.penalty_amount > 10000 THEN 'HIGH' ELSE 'MEDIUM' END AS severity,
    'DEFECT_THRESHOLD_BREACH' AS leakage_type,
    concat('Defect rate: ', ca.defect_pct, '% vs ', ca.defect_sla_pct, '% SLA. Excess = ',
           ROUND(ca.defect_pct-ca.defect_sla_pct,3), '% -> ', ca.penalty_units, ' penalty unit(s). ',
           ca.penalty_units, ' x ', ca.units_ordered, ' units x $', ca.unit_rate_usd, ' x ',
           ca.penalty_pct, '% = $', ca.penalty_amount) AS calculation_detail
FROM calc ca
JOIN {RAW}.contracts c  ON c.contract_id  = ca.contract_id
JOIN {RAW}.customers cu ON cu.customer_id = ca.customer_id
""")

# ------------------------------------------------------------------------------------------
# LEAKAGE_REGISTER — union of all 6 rules (single source of truth for the dashboard)
# ------------------------------------------------------------------------------------------
union_cols = """rule_id,rule_name,event_ref,contract_id,customer_id,customer_name,
           industry,contract_type,event_type,event_date,
           actual_hours,sla_threshold_hours,breach_hours,
           transaction_value,penalty_pct,leakage_amount_usd,
           severity,leakage_type,calculation_detail"""

spark.sql(f"""
CREATE OR REPLACE VIEW {ANALYTICS}.leakage_register AS
    SELECT {union_cols}, current_timestamp() AS detected_at FROM {ANALYTICS}.rule_r01_sla_breach       WHERE leakage_amount_usd > 0
UNION ALL
    SELECT {union_cols}, current_timestamp() FROM {ANALYTICS}.rule_r02_bonus_eligible    WHERE leakage_amount_usd > 0
UNION ALL
    SELECT {union_cols}, current_timestamp() FROM {ANALYTICS}.rule_r03_billing_mismatch  WHERE leakage_amount_usd > 0
UNION ALL
    SELECT {union_cols}, current_timestamp() FROM {ANALYTICS}.rule_r04_overage_unbilled  WHERE leakage_amount_usd > 0
UNION ALL
    SELECT {union_cols}, current_timestamp() FROM {ANALYTICS}.rule_r05_delivery_sla      WHERE leakage_amount_usd > 0
UNION ALL
    SELECT {union_cols}, current_timestamp() FROM {ANALYTICS}.rule_r06_defect_breach     WHERE leakage_amount_usd > 0
""")

print("Rule views R01-R06 + LEAKAGE_REGISTER created in", ANALYTICS)
for r in ("rule_r01_sla_breach", "rule_r02_bonus_eligible", "rule_r03_billing_mismatch",
          "rule_r04_overage_unbilled", "rule_r05_delivery_sla", "rule_r06_defect_breach"):
    print(f"  {r}: {spark.table(f'{ANALYTICS}.{r}').count()} rows")
