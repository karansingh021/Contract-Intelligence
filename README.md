# Contract Intelligence · Revenue Leakage AI

**AI-Powered Contract Extraction, Leakage Detection & Revenue Protection**

## Overview

Contract Intelligence automatically detects revenue leakage across your contract portfolio using 6 intelligent rules, and can extract structured data directly from your contract PDFs using Snowflake Cortex AI — all without leaving Snowflake.

## Three Ways to Use This App

| Mode | How it works | Best for |
|---|---|---|
| **Demo** | Pre-loaded 130+ sample contracts | Exploring the app instantly |
| **Consumer Tables** | Bind your structured Snowflake tables | You already have contract data in Snowflake |
| **Consumer PDF** | Upload PDFs → Cortex AI extracts fields | Contracts are in PDF/scanned documents |

## Leakage Detection Rules

| Rule | Type | Description |
|---|---|---|
| R01 | SLA Breach Penalty | Actual turnaround hours > contracted SLA hours → penalty exposure |
| R02 | Q4 Bonus Unclaimed | Turnaround < bonus threshold in Oct–Dec → unclaimed bonus owed |
| R03 | Billing Mismatch | Billed amount ≠ quantity × contracted unit rate |
| R04 | Overage Unbilled | Overage units recorded but not invoiced |
| R05 | Delivery SLA Breach | Delivery % below 100% → shortfall penalty |
| R06 | Defect Rate Breach | Defect % > 0 → quality penalty |

## PDF Pipeline (Consumer PDF Mode)

1. Create a stage in your account and upload contract PDFs
2. Bind the stage to this app
3. Click **Run PDF Extraction** — Cortex `PARSE_DOCUMENT` + `COMPLETE` (Mistral-Large2) extract 25+ fields per contract
4. Click **Run Leakage Detection** — the rule engine runs on your extracted contracts

Extracted fields include: contract type, SLA hours, penalty %, annual value, auto-renewal flags, loop detection, risk scoring, and more.

## Consumer Table Schema

### Contracts
`CONTRACT_ID, CUSTOMER_ID, ANNUAL_VALUE_USD, PENALTY_PCT, SLA_HOURS, UNIT_RATE_USD, CONTRACTED_UNITS, OVERAGE_RATE_USD, BONUS_PCT, BONUS_THRESHOLD_HRS, CONTRACT_TYPE, CONTRACT_START, CONTRACT_END`

### Customers  
`CUSTOMER_ID, CUSTOMER_NAME, INDUSTRY, SEGMENT, REGION, COUNTRY`

### Billing Transactions
`TRANSACTION_ID, CONTRACT_ID, CUSTOMER_ID, TRANSACTION_DATE, BILLED_AMOUNT, UNIT_PRICE, QUANTITY, PAYMENT_STATUS, INVOICE_NUMBER`

### Operational Events
`EVENT_ID, CONTRACT_ID, CUSTOMER_ID, EVENT_TYPE, EVENT_DATE, TURNAROUND_HOURS, REPORTED_VALUE, DELIVERY_PCT, DEFECT_PCT, OVERAGE_UNITS, UPTIME_PCT, STATUS`

## Application Roles

| Role | Access |
|---|---|
| `app_user` | View dashboards, run detection, read analytics |
| `app_admin` | All of app_user + switch modes, bind references, run PDF pipeline |

## Support

Contact the app provider through the Snowflake Marketplace listing page.
