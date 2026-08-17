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
*No objects found in this group.*

### ⚠️ Manual Review Required / Complex
- **expectations** (Target: `DATABRICKS_SQL_PROCEDURE`) - (Warnings: Agentic pipeline trace: Attempt 1: Translation Agent returned no code. | Attempt 2: Translation Agent returned no code. | Attempt 3: Translation Agent returned no code. | Attempt 4: Translation Agent returned no code., SQL parse failed: Invalid expression / Unexpected token. Line 2, Col: 6.
  RAW_SQL -- NOTE: Using CREATE OR REPLACE to ensure schema matches procedure expectations
[4mCREATE[0m OR REPLACE TABLE raw.consumer_ai_extractions (
    FILE_NAME                  STRING,
    CHUNK_ID ; Manual Actions: Manually review and migrate this statement; parser could not build an AST.)

## Other App Objects (Workflows, Configs, Apps)

- **APP_ROLE.app_user** (`GRANT` -> `DATABRICKS_GROUP`)
- **APP_ROLE.app_admin** (`GRANT` -> `DATABRICKS_GROUP`)
- **VERSIONED_SCHEMA.config** (`SCHEMA` -> `DATABRICKS_SCHEMA`)
- **CREATE_TABLE_1** (`UNKNOWN` -> `DATABRICKS_SQL`)
- **CREATE_TABLE_2** (`UNKNOWN` -> `DATABRICKS_SQL`)
- **CREATE_SCHEMA_3** (`UNKNOWN` -> `DATABRICKS_SQL`)
- **CREATE_VIEW_4** (`UNKNOWN` -> `DATABRICKS_SQL`)
- **CREATE_VIEW_5** (`UNKNOWN` -> `DATABRICKS_SQL`)
- **CREATE_VIEW_6** (`UNKNOWN` -> `DATABRICKS_SQL`)
- **CREATE_VIEW_7** (`UNKNOWN` -> `DATABRICKS_SQL`)
- **CREATE_TABLE_8** (`UNKNOWN` -> `DATABRICKS_SQL`)
- **CREATE_TABLE_9** (`UNKNOWN` -> `DATABRICKS_SQL`)
- **CREATE_TABLE_10** (`UNKNOWN` -> `DATABRICKS_SQL`)
- **CREATE_TABLE_11** (`UNKNOWN` -> `DATABRICKS_SQL`)
- **CREATE_TABLE_12** (`UNKNOWN` -> `DATABRICKS_SQL`)
- **CREATE_TABLE_13** (`UNKNOWN` -> `DATABRICKS_SQL`)
- **raw.pdf_processing_stage** (`STAGE` -> `DATABRICKS_VOLUME`)
- **CREATE_SCHEMA_14** (`UNKNOWN` -> `DATABRICKS_SQL`)
- **CREATE_TABLE_15** (`UNKNOWN` -> `DATABRICKS_SQL`)
- **CREATE_TABLE_16** (`UNKNOWN` -> `DATABRICKS_SQL`)
- **CREATE_TABLE_17** (`UNKNOWN` -> `DATABRICKS_SQL`)
- **VERSIONED_SCHEMA.app** (`SCHEMA` -> `DATABRICKS_SCHEMA`)
- **CREATE_FUNCTION_18** (`UNKNOWN` -> `DATABRICKS_SQL`)
- **CREATE_FUNCTION_19** (`UNKNOWN` -> `DATABRICKS_SQL`)
- **CREATE_FUNCTION_20** (`UNKNOWN` -> `DATABRICKS_SQL`)
- **CREATE_FUNCTION_21** (`UNKNOWN` -> `DATABRICKS_SQL`)
- **CREATE_FUNCTION_22** (`UNKNOWN` -> `DATABRICKS_SQL`)
- **app.json_format** (`FILE_FORMAT` -> `DATABRICKS_READ_OPTIONS`)
- **app.csv_format** (`FILE_FORMAT` -> `DATABRICKS_READ_OPTIONS`)
- **app.csv_header_format** (`FILE_FORMAT` -> `DATABRICKS_READ_OPTIONS`)
- **dashboard** (`STREAMLIT_APP` -> `DATABRICKS_APP_STREAMLIT`)
- **CREATE_SCHEMA_23** (`UNKNOWN` -> `DATABRICKS_SQL`)
- **CREATE_VIEW_24** (`UNKNOWN` -> `DATABRICKS_SQL`)
- **CREATE_VIEW_25** (`UNKNOWN` -> `DATABRICKS_SQL`)
- **CREATE_VIEW_26** (`UNKNOWN` -> `DATABRICKS_SQL`)
- **CREATE_VIEW_27** (`UNKNOWN` -> `DATABRICKS_SQL`)
- **CREATE_VIEW_28** (`UNKNOWN` -> `DATABRICKS_SQL`)
- **CREATE_VIEW_29** (`UNKNOWN` -> `DATABRICKS_SQL`)
- **CREATE_VIEW_30** (`UNKNOWN` -> `DATABRICKS_SQL`)
- **streamlit_app** (`STREAMLIT_APP` -> `DATABRICKS_APP_STREAMLIT`)
- **CREATE_STREAMLIT_31** (`UNKNOWN` -> `DATABRICKS_SQL`)
- **landingpage** (`STREAMLIT_APP` -> `DATABRICKS_APP_STREAMLIT`)
