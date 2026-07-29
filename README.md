# Contract Intelligence · Revenue Leakage AI

**AI-Powered Contract Extraction, Multi-Format Data Ingestion & Revenue Protection**

## Overview

Contract Intelligence automatically detects revenue leakage across your contract portfolio using 6 intelligent rules. It ingests data from your enterprise systems in their native formats — contract PDFs, CRM JSON, ERP CSV, and operational event JSON — all without leaving Snowflake.

## Two Modes of Operation

| Mode | How it works | Best for |
|---|---|---|
| **Demo** | Pre-loaded 130+ sample contracts with full analytics | Exploring the app instantly — no setup needed |
| **Your Data** | Upload your enterprise data files to a Snowflake stage | Running leakage detection on your real contracts |

## Consumer Data Ingestion (Your Data Mode)

The app processes **4 enterprise data sources** in their native formats from a single Snowflake stage:

| Source | Format | Stage Path | Description |
|--------|--------|------------|-------------|
| **Contract Details** | PDF | `/contracts/*.pdf` | Contract documents — Cortex AI extracts terms, SLA parameters, penalty rates, unit pricing, and risk indicators |
| **CRM Data** | JSON | `/crm/*.json` | Customer relationships from Salesforce, HubSpot, Dynamics, etc. |
| **ERP Data** | CSV | `/erp/*.csv` | Billing transactions and financials from SAP, Oracle, NetSuite, etc. |
| **OPS Data** | JSON | `/ops/*.json` | Operational events from monitoring, ticketing, or IoT systems |

### Getting Started with Your Data

1. **Install the app** — permissions and references are requested automatically via the in-app setup wizard
2. **Grant privileges** — the app prompts you to grant `CREATE WAREHOUSE` and `EXECUTE TASK`
3. **Bind a warehouse** — select a warehouse for processing
4. **Bind a stage** — select or create an internal stage for your data files
5. **Upload your files** — organize files into `/contracts/`, `/crm/`, `/erp/`, `/ops/` subfolders
6. **Run Ingestion Pipeline** — processes all file types automatically
7. **Run Leakage Detection** — the 6-rule engine analyzes your data

### Expected Data Fields

**CRM JSON** — array of objects:
```json
[
  {
    "customer_id": "CUST-001",
    "customer_name": "Acme Corp",
    "industry": "Manufacturing",
    "segment": "Enterprise",
    "region": "North America",
    "country": "US"
  }
]
```

**ERP CSV** — with header row:
```csv
transaction_id,contract_id,customer_id,transaction_date,billed_amount,unit_price,quantity,payment_status,invoice_number
TXN-001,CTR-001,CUST-001,2024-03-15,15000.00,150.00,100,PAID,INV-2024-0342
```

**OPS JSON** — array of objects:
```json
[
  {
    "event_id": "EVT-001",
    "contract_id": "CTR-001",
    "customer_id": "CUST-001",
    "event_type": "SLA_REVIEW",
    "event_date": "2024-03-20",
    "turnaround_hours": 52.5,
    "delivery_pct": 95.2,
    "defect_pct": 1.3,
    "overage_units": 150
  }
]
```

*Column names are flexible — use the in-app Column Mapping UI to map your fields.*

## Column Mapping (Flexible Schema)

The app does **not** require exact column names. After uploading your files:

1. Click **Detect Fields** — the app reads your file headers/keys automatically
2. Use the dropdown mapping UI to map each of your fields to the app's expected fields
3. Click **Save Mappings** — the pipeline remembers your configuration

Example: If your CRM system exports `client_number` instead of `customer_id`:

```
Your Field        →  App Field
──────────────────────────────
client_number     →  CUSTOMER_ID
company_name      →  CUSTOMER_NAME
vertical          →  INDUSTRY
```

The app also handles data type coercion automatically:
- Numbers with commas/currency symbols (`"$15,000.00"`) → clean NUMBER
- Various date formats (`"03/15/2024"`, `"2024-03-15"`) → DATE
- Missing/null values → graceful NULLs (won't crash the pipeline)

## Leakage Detection Rules

| Rule | Type | Description |
|---|---|---|
| R01 | SLA Breach Penalty | Actual turnaround hours > contracted SLA hours |
| R02 | Q4 Bonus Unclaimed | Turnaround < bonus threshold in Oct-Dec |
| R03 | Billing Mismatch | Billed amount != quantity x contracted unit rate |
| R04 | Overage Unbilled | Overage units recorded but not invoiced |
| R05 | Delivery SLA Breach | Delivery % below contracted threshold |
| R06 | Defect Rate Breach | Defect % exceeds quality threshold |

## Application Roles

| Role | Access |
|---|---|
| `app_user` | View dashboards, read analytics |
| `app_admin` | All of app_user + switch modes, run pipeline, run detection |

## Permissions & References

The app uses the **Snowflake Permissions SDK** to request everything it needs on first launch:

| Type | What | Why |
|------|------|-----|
| Privilege | `CREATE WAREHOUSE` | Dedicated compute for pipeline |
| Privilege | `EXECUTE TASK` | Scheduled detection tasks |
| Privilege | `SNOWFLAKE.CORTEX_USER` | Access Snowflake Cortex functions for AI tasks |
| Reference | Data Stage (STAGE) | Where you upload PDF/JSON/CSV files |
| Reference | Warehouse (WAREHOUSE) | Processing compute |

## Snowflake Cortex AI

For **PDF extraction** and the **AI Assistant**, this application uses the following Snowflake Cortex LLM models:
*   **`mistral-large`**: Drives the conversational AI Assistant dialog.
*   **`llama3.1-70b`**: Powering the PDF text ingestion and key term extraction pipeline.

Consumers should ensure these models are available in their Snowflake account region. The `SNOWFLAKE.CORTEX_USER` privilege is requested automatically via the app permissions configuration UI in Snowsight.

> **Note:** Cortex AI may not be available in standard Trial Accounts without an upgrade.

## Support

For questions or support, contact support@synthlake.com.
