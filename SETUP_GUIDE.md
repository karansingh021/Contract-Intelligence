# Contract Intelligence & Revenue Leakage Prevention — Databricks Setup Guide

Ported from the Snowflake MVP. Plug-and-play design: everything reads from **one Unity
Catalog Volume** — no external stages, no storage integrations, no hardcoded cloud creds.

## 0. Prerequisites

- A Databricks workspace with **Unity Catalog** enabled, and permission to create a catalog.
- A running **SQL Warehouse** (any size — Serverless recommended) for the Streamlit app.
- A **Foundation Model API** serving endpoint available in your workspace (check under
  *Serving* in the left nav). Default assumed: `databricks-meta-llama-3-3-70b-instruct`.
  If your workspace exposes a different name, you'll pass it as a widget/env var — nothing
  is hardcoded.
- A cluster or SQL warehouse with internet access is **not** required — this design never
  reaches outside your workspace except to the LLM serving endpoint (which is internal).

## 1. Import the code into your workspace

Upload this whole folder into a Databricks **Repo** (Repos → Add Repo → "existing files"),
or import each `.py` file as a notebook via Workspace → Import. Every module top-of-file
comment tells you what it ports from the original Snowflake scripts.

```
00_setup/00_config.py                              <- run first, always
01_ingestion/01_ddl_raw_tables.py
01_ingestion/02_billing_customer_ops_ingestion.py
02_ai_extraction/01_pdf_ocr_and_chunking.py
02_ai_extraction/02_llm_extraction_and_quality_pass.py
02_ai_extraction/03_build_master_and_contracts.py
03_rule_engine/00_ddl_analytics_tables.py
03_rule_engine/01_rule_views.py
03_rule_engine/02_generate_leakage.py
04_gold_views/01_gold_views.py
05_alerting/01_send_alerts.py
06_orchestration/databricks.yml                    <- optional: Databricks Workflow (Asset Bundle)
07_app/app.py, db.py, landingpage.py, dashboard.py, requirements.txt   <- plain Streamlit workspace app
```

## 2. Drop your source files into a Volume

Run `00_setup/00_config.py` once with default widgets — it creates the catalog, schemas,
and an empty Volume, and prints the exact path. Then drop your files in, mirroring the
original S3 layout:

```
/Volumes/contract_intelligence/raw/landing/contracts/pdf/*.pdf
/Volumes/contract_intelligence/raw/landing/erp/csv/VBRK_*.csv
/Volumes/contract_intelligence/raw/landing/erp/csv/VBRP_*.csv
/Volumes/contract_intelligence/raw/landing/crm/json/*.json
/Volumes/contract_intelligence/raw/landing/ops/json/*.json
```

You can also point the `volume_path` widget at any *existing* Volume with this layout —
nothing requires the auto-created one.

## 3. Run the pipeline (in order)

Attach each notebook to a cluster (DBR 15.4 LTS or later; ML runtime not required) and run
top-to-bottom, or deploy `06_orchestration/databricks.yml` as a Databricks Workflow and let
it run the whole DAG on a schedule (replaces the Snowflake 15-minute `TASK`).

| Step | Notebook | What it does |
|---|---|---|
| 1 | `01_ddl_raw_tables.py` | Creates all Delta tables in the `raw` schema |
| 2 | `02_billing_customer_ops_ingestion.py` | Loads CUSTOMERS / BILLING_TRANSACTIONS / OPERATIONAL_EVENTS from the Volume |
| 3 | `01_pdf_ocr_and_chunking.py` | OCRs PDFs (pdfplumber + pytesseract fallback), builds RAW_CONTRACT_PDFS + CONTRACT_TEXT_CHUNKS |
| 4 | `02_llm_extraction_and_quality_pass.py` | Calls the LLM per chunk (`ai_query`), then re-runs all 7 SQL quality fixes (duration, TCV, contract class, risk, review reason, loop detection) |
| 5 | `03_build_master_and_contracts.py` | Dedupes chunk-level extractions into one row per contract |
| 6 | `00_ddl_analytics_tables.py` | Creates LEAKAGE_EVENTS / ALERT_LOG / CREDIT_NOTES |
| 7 | `01_rule_views.py` | Creates the 6 rule views + LEAKAGE_REGISTER |
| 8 | `02_generate_leakage.py` | Materializes leakage, drafts alerts + credit notes (idempotent — safe to re-run) |
| 9 | `01_gold_views.py` | Creates the 4 dashboard-facing GOLD views |
| 10 | `01_send_alerts.py` | Emails pending alerts (dry-run/log mode until you configure SMTP secrets) |

Steps 3-5 only do work if there are new/changed PDFs; steps 6-9 are cheap SQL and safe to
re-run on every schedule tick.

## 4. (Optional) Configure email alerting

Alerting works in dry-run/print mode out of the box. To actually send email, create a
secret scope once from the Databricks CLI:

```bash
databricks secrets create-scope contract-intel-alerts
databricks secrets put-secret contract-intel-alerts smtp-host
databricks secrets put-secret contract-intel-alerts smtp-port
databricks secrets put-secret contract-intel-alerts smtp-user
databricks secrets put-secret contract-intel-alerts smtp-password
```

## 5. Run the Streamlit dashboard (plain workspace app, no Databricks Apps needed)

```bash
cd 07_app
pip install -r requirements.txt

export DATABRICKS_HOST="https://<your-workspace>.cloud.databricks.com"
export DATABRICKS_TOKEN="dapi********************************"           # Settings -> Developer -> Access tokens
export DATABRICKS_HTTP_PATH="/sql/1.0/warehouses/<warehouse_id>"          # SQL Warehouses -> your warehouse -> Connection details
export DATABRICKS_CATALOG="contract_intelligence"
export DATABRICKS_LLM_ENDPOINT="databricks-meta-llama-3-3-70b-instruct"

streamlit run app.py
```

This works identically whether you run it from your laptop, a Databricks cluster web
terminal, or any VM that can reach the workspace — it's a normal Streamlit app talking to
your SQL Warehouse over `databricks-sql-connector`. If you forget to export the env vars,
the app shows a sidebar form to fill them in at runtime instead of crashing.

## 6. Re-running / idempotency

Every module is safe to re-run: DDL uses `CREATE TABLE IF NOT EXISTS` / `CREATE OR REPLACE
VIEW`, ingestion overwrites its target table, and `GENERATE_LEAKAGE` uses `MERGE` +
anti-join `INSERT`s so nothing duplicates.

## 7. Mapping cheat-sheet (Snowflake → Databricks)

| Snowflake | Databricks |
|---|---|
| Database / Schema | Unity Catalog / Schema (same 3-level namespace) |
| External Stage + Storage Integration | Unity Catalog Volume (plug-and-play, any cloud) |
| `AI_PARSE_DOCUMENT` | `pdfplumber` (+ `pytesseract` OCR fallback) |
| `SNOWFLAKE.CORTEX.COMPLETE` | `ai_query()` against a Foundation Model API serving endpoint |
| `VARIANT` | `STRING` (JSON text) + `from_json`/`get_json_object` |
| SQL UDFs (`DETECT_CONTRACT_CLASS`, etc.) | Python UDFs (`F.udf(...)`) — same logic, easier to unit test |
| Stored Procedures (`GENERATE_LEAKAGE`, etc.) | Plain Python functions callable from a notebook, a Job task, or the Streamlit app |
| `TASK` (scheduled) | Databricks Workflow / Job (see `06_orchestration/databricks.yml`) |
| `NOTIFICATION INTEGRATION` + `SYSTEM$SEND_EMAIL` | `smtplib` + Databricks secret scope |
| Streamlit-in-Snowflake (`get_active_session()`) | Plain Streamlit + `databricks-sql-connector` |
