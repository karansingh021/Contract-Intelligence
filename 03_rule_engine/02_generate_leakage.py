# Databricks notebook source
# ================================================================================================
# MODULE 06c — GENERATE_LEAKAGE()
# Ports: 03_ANALYTICS.sql SECTION D — ANALYTICS.GENERATE_LEAKAGE() stored procedure
#
# Same 3 steps, same thresholds:
#   1. MERGE LEAKAGE_REGISTER -> LEAKAGE_EVENTS (dedup on rule_id + event_ref)
#   2. INSERT alerts for new leakage events >= $100 (dedup on leakage_id)
#   3. INSERT credit note drafts for HIGH/CRITICAL leakage >= $500 (dedup on leakage_id)
#
# Exposed as a plain Python function `generate_leakage()` so it can be called:
#   - interactively from this notebook,
#   - as a Databricks Job task (module 08 workflow),
#   - from the Streamlit app's "Run Rule Engine" button (via Jobs API run-now).
# ================================================================================================

# MAGIC %run ../00_setup/00_config

# COMMAND ----------

ANALYTICS = f"{CATALOG}.{ANALYTICS_SCHEMA}"


def generate_leakage():
    # Step 1: materialise leakage (MERGE avoids duplicates on repeated runs)
    n_before = spark.table(f"{ANALYTICS}.leakage_events").count()
    spark.sql(f"""
        MERGE INTO {ANALYTICS}.leakage_events tgt
        USING (
            SELECT
                uuid() AS leakage_id, rule_id, rule_name, event_ref, contract_id, customer_id,
                customer_name, industry, leakage_type, leakage_amount_usd, severity, event_date,
                calculation_detail, current_timestamp() AS detected_at
            FROM {ANALYTICS}.leakage_register
        ) src
        ON tgt.rule_id = src.rule_id AND tgt.event_ref = src.event_ref
        WHEN NOT MATCHED THEN INSERT (
            leakage_id, rule_id, rule_name, event_ref, contract_id, customer_id, customer_name,
            industry, leakage_type, leakage_amount_usd, severity, event_date, calculation_detail, detected_at
        ) VALUES (
            src.leakage_id, src.rule_id, src.rule_name, src.event_ref, src.contract_id, src.customer_id,
            src.customer_name, src.industry, src.leakage_type, src.leakage_amount_usd, src.severity,
            src.event_date, src.calculation_detail, src.detected_at
        )
    """)
    n_after = spark.table(f"{ANALYTICS}.leakage_events").count()
    n_leakage = n_after - n_before

    # Step 2: generate alerts for new leakage events (>= $100), skip ones already alerted
    n_alerts_before = spark.table(f"{ANALYTICS}.alert_log").count()
    spark.sql(f"""
        INSERT INTO {ANALYTICS}.alert_log
            (alert_id, leakage_id, contract_id, customer_name, alert_type, severity,
             leakage_amount_usd, alert_message, sent_to, alert_channel, status, created_at)
        SELECT
            uuid(), le.leakage_id, le.contract_id, le.customer_name, le.leakage_type, le.severity,
            le.leakage_amount_usd,
            concat('LEAKAGE DETECTED | ', le.rule_name, ' | Customer: ', le.customer_name,
                   ' | $', format_number(le.leakage_amount_usd, 2), ' | Severity: ', le.severity),
            CASE le.severity
                WHEN 'CRITICAL' THEN '{ALERT_RECIPIENT}'
                WHEN 'HIGH'     THEN '{ALERT_RECIPIENT}'
                WHEN 'MEDIUM'   THEN '{ALERT_RECIPIENT}'
                ELSE '{ALERT_RECIPIENT}'
            END,
            'EMAIL', 'PENDING', current_timestamp()
        FROM {ANALYTICS}.leakage_events le
        LEFT JOIN {ANALYTICS}.alert_log al ON al.leakage_id = le.leakage_id
        WHERE al.alert_id IS NULL AND le.leakage_amount_usd >= 100
    """)
    n_alerts = spark.table(f"{ANALYTICS}.alert_log").count() - n_alerts_before

    # Step 3: generate credit note drafts for HIGH/CRITICAL leakage (>= $500)
    n_credits_before = spark.table(f"{ANALYTICS}.credit_notes").count()
    spark.sql(f"""
        INSERT INTO {ANALYTICS}.credit_notes
            (credit_note_id, leakage_id, contract_id, customer_name, credit_type,
             credit_amount_usd, justification, status, generated_by, created_at, erp_sync_status)
        SELECT
            uuid(), le.leakage_id, le.contract_id, le.customer_name,
            CASE le.leakage_type
                WHEN 'OVERBILLED'           THEN 'BILLING_ADJUSTMENT'
                WHEN 'UNDERBILLED'          THEN 'BILLING_ADJUSTMENT'
                WHEN 'TELECOM_USER_OVERAGE' THEN 'BILLING_ADJUSTMENT'
                WHEN 'SAAS_SEAT_OVERAGE'    THEN 'BILLING_ADJUSTMENT'
                WHEN 'BONUS_UNCLAIMED'      THEN 'BONUS_PAYMENT'
                ELSE 'PENALTY_CREDIT'
            END,
            le.leakage_amount_usd,
            concat(le.rule_name, ' | ', le.leakage_type, ' | Contract: ', le.contract_id,
                   ' | ', le.calculation_detail),
            'DRAFT', 'RULE_ENGINE', current_timestamp(), 'PENDING'
        FROM {ANALYTICS}.leakage_events le
        LEFT JOIN {ANALYTICS}.credit_notes cn ON cn.leakage_id = le.leakage_id
        WHERE cn.credit_note_id IS NULL
          AND le.severity IN ('CRITICAL', 'HIGH')
          AND le.leakage_amount_usd >= 500
    """)
    n_credits = spark.table(f"{ANALYTICS}.credit_notes").count() - n_credits_before

    result = f"Done | leakage_events={n_leakage} | alerts={n_alerts} | credit_notes={n_credits}"
    return result


if __name__ == "__main__" or True:
    print(generate_leakage())
