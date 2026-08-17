# Databricks Project Object Inventory

This file lists all migrated objects segregated by object group and convertibility status.

## Tables

### ✅ Convertible (Automated/Direct)
*No objects found in this group.*

### ⚠️ Manual Review Required / Complex
*No objects found in this group.*

## Views

### ✅ Convertible (Automated/Direct)
*No objects found in this group.*

### ⚠️ Manual Review Required / Complex
*No objects found in this group.*

## Procedures

### ✅ Convertible (Automated/Direct)
- **process_customer** (Target: `PYSPARK_FUNCTION`) - (Manual Actions: Confirm Spark session ('spark') is correctly injected in the target environment.)

### ⚠️ Manual Review Required / Complex
- **process_sales** (Target: `UNKNOWN`) - (Warnings: Databricks AI provider not connected — agentic pipeline skipped.; Manual Actions: Configure Databricks SQL AI to enable automated migration.)

## Other App Objects (Workflows, Configs, Apps)

- **Command_scripts\tables.sql** (`UNKNOWN` -> `DATABRICKS_SQL`)
- **Command_scripts\tables.sql** (`UNKNOWN` -> `DATABRICKS_SQL`)
- **Command_scripts\tables.sql** (`UNKNOWN` -> `DATABRICKS_SQL`)
- **RAW_SQL** (`STAGE` -> `DATABRICKS_VOLUME`)
- **RAW_SQL** (`STREAM` -> `DATABRICKS_CHANGE_DATA_FEED`)
- **RAW_SQL** (`TASK` -> `DATABRICKS_WORKFLOW`)
- **Command_scripts\views.sql** (`UNKNOWN` -> `DATABRICKS_SQL`)
- **Command_scripts\views.sql** (`UNKNOWN` -> `DATABRICKS_SQL`)
- **Command_scripts\views.sql** (`UNKNOWN` -> `DATABRICKS_SQL`)
- **app** (`STREAMLIT_APP` -> `DATABRICKS_APP_STREAMLIT`)
