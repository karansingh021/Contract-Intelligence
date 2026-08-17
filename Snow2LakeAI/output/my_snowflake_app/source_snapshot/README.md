# Contract Intelligence · Revenue Leakage AI

**AI-Powered Contract Extraction, Multi-Format Data Ingestion & Revenue Protection**

## Overview

Contract Intelligence automatically detects revenue leakage across your contract portfolio using 6 intelligent rules. It ingests data from your enterprise systems in their native formats — contract PDFs, CRM JSON, ERP CSV, and operational event JSON — all without leaving Snowflake.

## Two Modes of Operation

| Mode | How it works | Best for |
|---|---|---|
| **Demo** | Pre-loaded sample contracts with full analytics | Exploring the app instantly — no setup needed |
| **Your Data** | Upload your enterprise data files to a Snowflake stage | Running leakage detection on your real contracts |

---

## Quick Start Guide

### Step 1: Install the App

Install from the Snowflake Marketplace. The app opens to a setup wizard that guides you through permissions.

### Step 2: Bind a Processing Warehouse

The app will prompt you to select an existing warehouse via the Snowsight reference picker. This warehouse is used for the ingestion pipeline and rule engine.

### Step 3: Grant Access to Your Data Stage

Create an internal Snowflake stage (if you don't already have one) and upload your data files. Then grant the app read access:

```sql
-- Grant the app access to your database, schema, and stage
GRANT USAGE ON DATABASE <your_database> TO APPLICATION CONTRACT_INTEL_APP;
GRANT USAGE ON SCHEMA <your_database>.<your_schema> TO APPLICATION CONTRACT_INTEL_APP;
GRANT READ ON STAGE <your_database>.<your_schema>.<your_stage> TO APPLICATION CONTRACT_INTEL_APP;
```

### Step 4: Select Your Stage in the App

After granting access, open the app. The setup wizard will display a dropdown of all stages the app can access. Select your data stage and click **Save**.

> If you don't see your stage in the dropdown, click **Refresh** after running the GRANT statements.

### Step 5: Grant Cortex AI Access

Grant the Cortex database role to enable PDF extraction and the AI assistant:

```sql
GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO APPLICATION CONTRACT_INTEL_APP;
```

### Step 6: Upload Your Data Files

Upload files to your stage in the following folder structure:

```
your_stage/
├── contracts/    ← PDF contract documents
├── crm/          ← JSON customer relationship data
├── erp/          ← CSV billing/financial transactions
└── ops/          ← JSON operational events
```

Example upload commands:
```sql
PUT file://my_contract.pdf @MY_DB.MY_SCHEMA.MY_STAGE/contracts/ AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
PUT file://customers.json @MY_DB.MY_SCHEMA.MY_STAGE/crm/ AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
PUT file://billing.csv @MY_DB.MY_SCHEMA.MY_STAGE/erp/ AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
PUT file://events.json @MY_DB.MY_SCHEMA.MY_STAGE/ops/ AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
```

### Step 7: Run the Pipeline

1. In the app, switch to **"Your Data"** mode
2. Click **Run Ingestion Pipeline** — processes all file types from your stage
3. Click **Run Leakage Detection** — the 6-rule engine analyzes your data
4. View results in the Executive Dashboard

---

## Complete Setup Example

```sql
-- 1. Create a stage for your data (skip if you already have one)
CREATE STAGE MY_DB.MY_SCHEMA.CONTRACT_DATA
    DIRECTORY = (ENABLE = TRUE)
    ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE');

-- 2. Upload your files
PUT file://contract_001.pdf @MY_DB.MY_SCHEMA.CONTRACT_DATA/contracts/ AUTO_COMPRESS=FALSE;
PUT file://customers.json @MY_DB.MY_SCHEMA.CONTRACT_DATA/crm/ AUTO_COMPRESS=FALSE;
PUT file://billing.csv @MY_DB.MY_SCHEMA.CONTRACT_DATA/erp/ AUTO_COMPRESS=FALSE;
PUT file://events.json @MY_DB.MY_SCHEMA.CONTRACT_DATA/ops/ AUTO_COMPRESS=FALSE;

-- 3. Grant access to the app
GRANT USAGE ON DATABASE MY_DB TO APPLICATION CONTRACT_INTEL_APP;
GRANT USAGE ON SCHEMA MY_DB.MY_SCHEMA TO APPLICATION CONTRACT_INTEL_APP;
GRANT READ ON STAGE MY_DB.MY_SCHEMA.CONTRACT_DATA TO APPLICATION CONTRACT_INTEL_APP;

-- 4. Grant Cortex AI access
GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO APPLICATION CONTRACT_INTEL_APP;

-- 5. Open the app → select your stage from the dropdown → run the pipeline
```

---

## Data Source Formats

The app processes **4 enterprise data sources** from a single stage:

| Source | Format | Stage Subfolder | Description |
|--------|--------|-----------------|-------------|
| **Contract Details** | PDF | `/contracts/` | Cortex AI extracts terms, SLA parameters, penalty rates, pricing |
| **CRM Data** | JSON | `/crm/` | Customer relationships from Salesforce, HubSpot, Dynamics, etc. |
| **ERP Data** | CSV | `/erp/` | Billing transactions from SAP, Oracle, NetSuite, etc. |
| **OPS Data** | JSON | `/ops/` | Operational events from monitoring, ticketing, or IoT systems |

### Expected Fields

**CRM JSON** — one object per file or array of objects:

| Field | Required | Description |
|-------|----------|-------------|
| `customer_id` | Yes | Unique customer identifier |
| `customer_name` | Yes | Full legal company name |
| `industry` | No | Industry vertical |
| `segment` | No | Customer segment |
| `region` | No | Geographic region |
| `country` | No | Country code or name |

**ERP CSV** — with header row:

| Field | Required | Description |
|-------|----------|-------------|
| `contract_id` | Yes | Contract reference |
| `customer_id` | Yes | Matches CRM customer_id |
| `transaction_date` | Yes | Date of transaction (YYYY-MM-DD) |
| `billed_amount` | Yes | Total billed amount in USD |
| `invoice_number` | No | Invoice document number |
| `quantity` | No | Number of units billed |
| `unit_price` | No | Per-unit price |
| `payment_status` | No | PAID, PENDING, OVERDUE |

**OPS JSON** — one object per file or array of objects:

| Field | Required | Description |
|-------|----------|-------------|
| `event_id` | Yes | Unique event identifier |
| `contract_id` | Yes | Contract reference (matches ERP) |
| `customer_id` | Yes | Customer reference (matches CRM) |
| `event_type` | Yes | SLA_REVIEW, DELIVERY, DEFECT_REPORT, etc. |
| `event_date` | Yes | Date of the event (YYYY-MM-DD) |
| `turnaround_hours` | No | Actual turnaround time in hours |
| `delivery_pct` | No | Delivery completion percentage |
| `defect_pct` | No | Defect rate percentage |
| `overage_units` | No | Number of overage units consumed |

**Contract PDFs** — No specific structure required. Cortex AI automatically extracts contract terms, SLA parameters, pricing, and penalty clauses.

> **Flexible schema:** Column names do not need to match exactly. Use the in-app Column Mapping UI to map your fields to the app's expected fields.

---

## Leakage Detection Rules

| Rule | Type | Description |
|---|---|---|
| R01 | SLA Breach Penalty | Actual turnaround hours > contracted SLA hours |
| R02 | Q4 Bonus Unclaimed | Turnaround < bonus threshold in Oct-Dec |
| R03 | Billing Mismatch | Billed amount ≠ quantity × contracted unit rate |
| R04 | Overage Unbilled | Overage units recorded but not invoiced |
| R05 | Delivery SLA Breach | Delivery % below contracted threshold |
| R06 | Defect Rate Breach | Defect % exceeds quality threshold |

---

## Permissions Summary

| Type | Name | Purpose |
|------|------|---------|
| Reference | Warehouse (`WAREHOUSE`) | Processing compute for pipeline and rule engine |
| Database Role | `SNOWFLAKE.CORTEX_USER` | AI-powered PDF extraction and chatbot |
| Grant | `USAGE ON DATABASE` | App reads files from your stage |
| Grant | `USAGE ON SCHEMA` | App reads files from your stage |
| Grant | `READ ON STAGE` | App reads your data files (PDFs, JSON, CSV) |

---

## Snowflake Cortex AI

This application uses the following Snowflake Cortex AI capabilities:

| Function | Used For |
|----------|----------|
| `SNOWFLAKE.CORTEX.PARSE_DOCUMENT` | PDF text extraction (OCR + layout parsing) |
| `SNOWFLAKE.CORTEX.COMPLETE` (mistral-large2) | Contract field extraction and AI assistant |

**Regional availability:** Verify these models are available in your account region. See [Cortex LLM availability](https://docs.snowflake.com/en/user-guide/snowflake-cortex/llm-functions#availability).

---

## Support

For questions or support, contact **accounts@synthlake.com**.
