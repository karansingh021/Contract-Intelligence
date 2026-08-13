# Databricks notebook source
# ================================================================================================
# MODULE 08 — EMAIL ALERTING
# Ports: 05_ALERTING.sql — NOTIFICATION INTEGRATION + SEND_NEW_ALERTS() procedure
#
# Snowflake used a managed NOTIFICATION INTEGRATION + SYSTEM$SEND_EMAIL. Databricks has no
# built-in outbound email service, so this module sends via SMTP using credentials stored in
# a Databricks secret scope (never hardcode credentials in the notebook).
#
# One-time setup (run once from the Databricks CLI, not from this notebook):
#   databricks secrets create-scope contract-intel-alerts
#   databricks secrets put-secret contract-intel-alerts smtp-host
#   databricks secrets put-secret contract-intel-alerts smtp-port
#   databricks secrets put-secret contract-intel-alerts smtp-user
#   databricks secrets put-secret contract-intel-alerts smtp-password
#
# SENT_ALERTS dedup table lives in SIMPLE_ALERTING schema, exactly like the Snowflake version,
# so re-running this notebook never double-sends an alert.
# ================================================================================================

# MAGIC %run ../00_setup/00_config

# COMMAND ----------

import smtplib
from email.mime.text import MIMEText
from pyspark.sql import functions as F

ANALYTICS = f"{CATALOG}.{ANALYTICS_SCHEMA}"
ALERTING = f"{CATALOG}.{ALERTING_SCHEMA}"
SECRET_SCOPE = "contract-intel-alerts"

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {ALERTING}.sent_alerts (
    alert_id STRING,
    sent_at  TIMESTAMP
) USING DELTA
""")


def _smtp_config():
    """Reads SMTP creds from a Databricks secret scope. Falls back to None (dry-run/print
    mode) if the scope isn't configured yet, so the pipeline never hard-fails on first run."""
    try:
        return dict(
            host=dbutils.secrets.get(SECRET_SCOPE, "smtp-host"),
            port=int(dbutils.secrets.get(SECRET_SCOPE, "smtp-port")),
            user=dbutils.secrets.get(SECRET_SCOPE, "smtp-user"),
            password=dbutils.secrets.get(SECRET_SCOPE, "smtp-password"),
        )
    except Exception:
        return None


def _build_html_body(row):
    severity_color = {"CRITICAL": "red", "HIGH": "orange", "MEDIUM": "#E6B800"}.get(row["severity"], "black")
    return f"""
    <html><body style="font-family:Arial;padding:20px;">
        <h2 style="color:#D32F2F;">Revenue Leakage Alert</h2>
        <hr>
        <p><b>Customer:</b> {row['customer_name']}</p>
        <p><b>Contract ID:</b> {row['contract_id']}</p>
        <p><b>Alert Type:</b> {row['alert_type']}</p>
        <p><b>Severity:</b> <span style="color:{severity_color};font-weight:bold;">{row['severity']}</span></p>
        <p><b>Leakage Amount:</b> ${row['leakage_amount_usd']}</p>
        <p><b>Alert Message:</b></p>
        <div style="background:#F5F5F5;padding:12px;border-left:4px solid #D32F2F;margin-top:10px;">
            {row['alert_message']}
        </div>
        <br><hr>
        <p style="font-size:12px;color:gray;">Alert ID: {row['alert_id']}</p>
        <p style="font-size:12px;color:gray;">Leakage ID: {row['leakage_id']}</p>
        <p style="font-size:12px;color:gray;">Generated From: {ANALYTICS}.alert_log</p>
    </body></html>"""


def send_new_alerts():
    pending = spark.sql(f"""
        SELECT al.alert_id, al.leakage_id, al.customer_name, al.contract_id, al.alert_type,
               al.severity, al.leakage_amount_usd, al.alert_message, al.sent_to
        FROM {ANALYTICS}.alert_log al
        LEFT JOIN {ALERTING}.sent_alerts sa ON al.alert_id = sa.alert_id
        WHERE sa.alert_id IS NULL AND al.status = 'PENDING'
    """).collect()

    if not pending:
        return "No pending alerts."

    smtp_cfg = _smtp_config()
    sent_ids = []

    for row in pending:
        subject = f"CONTRACT ALERT | {row['severity']} | {row['customer_name']}"
        body_html = _build_html_body(row)
        recipient = row["sent_to"] or ALERT_RECIPIENT

        if smtp_cfg and recipient:
            msg = MIMEText(body_html, "html")
            msg["Subject"] = subject
            msg["From"] = smtp_cfg["user"]
            msg["To"] = recipient
            try:
                with smtplib.SMTP(smtp_cfg["host"], smtp_cfg["port"]) as server:
                    server.starttls()
                    server.login(smtp_cfg["user"], smtp_cfg["password"])
                    server.sendmail(smtp_cfg["user"], [recipient], msg.as_string())
            except Exception as e:
                print(f"  [WARN] failed to send alert {row['alert_id']}: {e}")
                continue
        else:
            # Dry-run mode: no SMTP secret scope configured yet -- log instead of failing.
            print(f"  [DRY-RUN] would email {recipient}: {subject}")

        sent_ids.append(row["alert_id"])

    if sent_ids:
        spark.createDataFrame([(i,) for i in sent_ids], ["alert_id"]) \
            .withColumn("sent_at", F.current_timestamp()) \
            .write.mode("append").saveAsTable(f"{ALERTING}.sent_alerts")

    return f"ALERTS SENT: {len(sent_ids)} / {len(pending)} pending"


if __name__ == "__main__" or True:
    print(send_new_alerts())
