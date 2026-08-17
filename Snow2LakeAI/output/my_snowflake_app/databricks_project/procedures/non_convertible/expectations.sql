# AGENTIC PIPELINE FAILED after 4 attempts.
# Original Snowflake source preserved below for manual migration:
# ────────────────────────────────────────────────────────────
# RAW_SQL -- NOTE: Using CREATE OR REPLACE to ensure schema matches procedure expectations
# CREATE OR REPLACE TABLE raw.consumer_ai_extractions (
#     FILE_NAME                  STRING,
#     CHUNK_ID                   NUMBER,
#     PIPELINE_RUN_ID            STRING,
#     EXTRACTION_RAW             STRING,
#     EXTRACTION_STATUS          STRING,
#     LOAD_TIMESTAMP             TIMESTAMP_TZ DEFAULT CURRENT_TIMESTAMP()
# )