# Databricks notebook source
# ================================================================================================
# MODULE 01 — RAW LAYER DDL (Delta / Unity Catalog)
# Ports: 01_PDF_EXTRACTION.sql (STEP 3) + 02_BILLING_CUSTOMER_TRANSACTIONS_DATA_INGESTION.sql (STEP 1B)
#
# Snowflake -> Databricks type mapping used throughout this port:
#   VARCHAR(n)/STRING   -> STRING
#   NUMBER(p,s)         -> DECIMAL(p,s)
#   NUMBER / INTEGER    -> BIGINT / INT
#   FLOAT               -> DOUBLE
#   BOOLEAN             -> BOOLEAN
#   DATE                -> DATE
#   TIMESTAMP_TZ        -> TIMESTAMP
#   VARIANT             -> STRING (JSON text; query with from_json/get_json_object/:  path ops
#                          are done in PySpark/SQL with get_json_object or schema_of_json)
#   UUID_STRING()        -> uuid()          (Databricks SQL built-in)
#   DEFAULT CURRENT_TIMESTAMP() -> set explicitly at write time (current_timestamp()) instead
#                                   of a column DEFAULT, for broad DBR-version compatibility.
# ================================================================================================

# MAGIC %run ../00_setup/00_config

# COMMAND ----------

RAW = f"{CATALOG}.{RAW_SCHEMA}"

# ----------------------------------------------------------------------------------------------
# 1A. PDF / AI EXTRACTION PIPELINE TABLES  (was 01_PDF_EXTRACTION.sql STEP 3)
# ----------------------------------------------------------------------------------------------

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {RAW}.raw_contract_pdfs (
    file_name                       STRING,
    file_size                       BIGINT,
    last_modified                   TIMESTAMP,
    file_url                        STRING,
    ocr_text                        STRING,
    parsed_json                     STRING COMMENT 'JSON text (was VARIANT in Snowflake)',
    document_page_count             INT COMMENT 'Layout-derived (NULL for scans)',
    document_page_count_estimated   INT COMMENT 'CEIL(chars/800)',
    document_page_count_final       INT COMMENT 'Best available: layout else estimated',
    text_char_count                 INT,
    text_density_score              DOUBLE,
    is_likely_scanned               BOOLEAN,
    ocr_engine_version               STRING,
    ocr_status                      STRING,
    pipeline_run_id                 STRING,
    record_source                   STRING,
    ingestion_timestamp              TIMESTAMP
) USING DELTA
""")

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {RAW}.contract_text_chunks (
    file_name                STRING,
    pipeline_run_id          STRING,
    source_document_id       STRING,
    chunk_id                 INT,
    chunk_text                STRING,
    chunk_size                INT,
    chunk_token_estimate      INT,
    chunk_sequence_start      INT,
    chunk_sequence_end        INT,
    total_chunks               INT,
    document_page_count       INT,
    first_page                 INT COMMENT 'Estimated first PDF page this chunk covers',
    last_page                  INT COMMENT 'Estimated last PDF page this chunk covers',
    page_range                 STRING COMMENT 'e.g. "Page 2-3 of 5"',
    text_density_score        DOUBLE,
    ocr_engine_version         STRING,
    ocr_status                 STRING,
    is_final_chunk             BOOLEAN,
    is_truncated                BOOLEAN,
    needs_rechunking           BOOLEAN,
    load_timestamp              TIMESTAMP
) USING DELTA
""")

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {RAW}.contract_ai_extractions (
    file_name                       STRING,
    chunk_id                        INT,
    document_page_count             INT,
    chunk_character_count            INT,
    source_stage                    STRING,
    first_page                      INT,
    last_page                       INT,
    page_range                      STRING,
    load_timestamp                   TIMESTAMP,
    ai_response                      STRING COMMENT 'raw JSON text returned by the LLM',

    contract_id                     STRING,
    customer_id                     STRING,
    customer_name                   STRING,
    vendor_name                     STRING,
    contract_type                   STRING,
    contract_class                  STRING COMMENT 'Insurance|Telecom|SaaS|Healthcare|Financial|NDA|Vendor|Procurement|Manufacturing|Government|Employment|Lease|Other',
    industry                        STRING,
    status                          STRING,

    contract_start_date             DATE,
    contract_end_date               DATE,
    auto_renewal_date                DATE,
    termination_notice_days          INT,
    effective_month                  DATE,
    contract_duration_days           INT,
    duration_source                  STRING COMMENT 'LLM | SQL_DATEDIFF | SQL_ESTIMATED',

    annual_value_usd                 DECIMAL(18,2),
    total_contract_value_usd         DECIMAL(18,2),
    tcv_estimation_method             STRING COMMENT 'EXPLICIT | ACV_x_DURATION | NULL',
    contract_currency                 STRING,
    unit_rate_usd                     DECIMAL(18,4),
    contracted_units                  INT,
    overage_rate_usd                  DECIMAL(18,4),
    payment_terms                     STRING,

    sla_hours                        DECIMAL(10,2),
    penalty_percent                   DECIMAL(10,2),
    bonus_percent                     DECIMAL(10,2),
    bonus_threshold_hrs               DECIMAL(10,2),
    delivery_sla_percent              DECIMAL(10,2),
    defect_sla_pct                    DECIMAL(10,2),

    governing_law                     STRING,
    has_auto_renewal                  BOOLEAN,
    has_unlimited_liability           BOOLEAN,
    has_indemnification               BOOLEAN,
    has_termination_clause            BOOLEAN,
    has_confidentiality_clause        BOOLEAN,
    has_governing_law                 BOOLEAN,
    has_payment_terms                 BOOLEAN,
    has_sla_terms                     BOOLEAN,
    renewal_flag                      BOOLEAN,

    risk_level                        STRING,
    contract_summary                  STRING,
    needs_human_review                BOOLEAN,
    review_reason                     STRING,
    review_priority                   STRING,
    review_category                   STRING,

    extraction_confidence              DOUBLE,
    ocr_quality_score                  DOUBLE,
    data_completeness_score            DOUBLE,

    missing_critical_fields_llm        BOOLEAN,
    date_conflict_flag_llm             BOOLEAN,
    financial_anomaly_flag_llm         BOOLEAN,
    ocr_corruption_flag_llm            BOOLEAN,
    duplicate_contract_flag            BOOLEAN,

    missing_critical_fields            BOOLEAN,
    date_conflict_flag                 BOOLEAN,
    financial_anomaly_flag             BOOLEAN,
    ocr_corruption_flag                BOOLEAN,

    has_repeated_clauses               BOOLEAN,
    loop_detection_summary             STRING,
    repeated_clause_count              INT,
    loop_signals                       STRING COMMENT 'JSON text: auto_renewal, evergreen, recurring_payment, etc.',

    extracted_by_model                 STRING,
    ocr_engine_version                 STRING,
    pipeline_run_id                    STRING,
    pipeline_execution_ts               TIMESTAMP,
    record_source                      STRING,
    raw_ocr_text_sample                 STRING,
    chunk_hash                          STRING,
    ai_processing_status                STRING,
    error_message                       STRING
) USING DELTA
""")

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {RAW}.master_contracts (
    contract_id                     STRING NOT NULL,
    customer_id                     STRING,
    customer_name                   STRING,
    vendor_name                     STRING,
    industry                        STRING,
    contract_type                   STRING,
    contract_class                  STRING,
    status                          STRING,

    contract_start_date             DATE,
    contract_end_date               DATE,
    auto_renewal_date                DATE,
    termination_notice_days          INT,
    effective_month                  DATE,
    contract_duration_days           INT,
    duration_source                  STRING,

    annual_value_usd                 DECIMAL(18,2),
    total_contract_value_usd         DECIMAL(18,2),
    tcv_estimation_method             STRING,
    contract_currency                 STRING,
    unit_rate_usd                     DECIMAL(18,4),
    contracted_units                  INT,
    overage_rate_usd                  DECIMAL(18,4),
    payment_terms                     STRING,

    sla_hours                        DECIMAL(10,2),
    penalty_percent                   DECIMAL(10,2),
    bonus_percent                     DECIMAL(10,2),
    bonus_threshold_hrs               DECIMAL(10,2),
    delivery_sla_percent              DECIMAL(10,2),
    defect_sla_pct                    DECIMAL(10,2),
    governing_law                     STRING,
    has_auto_renewal                  BOOLEAN,
    has_unlimited_liability           BOOLEAN,
    has_indemnification               BOOLEAN,
    has_termination_clause            BOOLEAN,
    has_confidentiality_clause        BOOLEAN,
    has_governing_law                 BOOLEAN,
    has_payment_terms                 BOOLEAN,
    has_sla_terms                     BOOLEAN,
    renewal_flag                      BOOLEAN,

    risk_level                        STRING,
    contract_summary                  STRING,
    needs_human_review                BOOLEAN,
    review_reason                     STRING,
    review_priority                   STRING,
    review_category                   STRING,

    extraction_confidence              DOUBLE,
    ocr_quality_score                  DOUBLE,
    data_completeness_score            DOUBLE,

    missing_critical_fields            BOOLEAN,
    date_conflict_flag                 BOOLEAN,
    financial_anomaly_flag             BOOLEAN,
    ocr_corruption_flag                BOOLEAN,
    duplicate_contract_flag            BOOLEAN,

    has_repeated_clauses               BOOLEAN,
    loop_detection_summary             STRING,
    loop_signals_summary                STRING,
    repeated_clause_count              INT,

    document_page_count                INT,
    page_range                         STRING,

    source_file                        STRING,
    extracted_by_model                 STRING,
    ocr_engine_version                 STRING,
    pipeline_run_id                    STRING,
    load_timestamp                      TIMESTAMP
) USING DELTA
""")

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {RAW}.contracts (
    contract_id                     STRING NOT NULL,
    customer_id                     STRING,
    customer_name                   STRING,
    industry                        STRING,
    contract_type                   STRING,
    contract_class                  STRING,
    contract_start                  DATE NOT NULL,
    contract_end                    DATE NOT NULL,
    contract_duration_days           INT,
    annual_value_usd                 DECIMAL(18,2) NOT NULL,
    total_contract_value_usd         DECIMAL(18,2),
    status                           STRING,
    sla_hours                        DECIMAL(8,2),
    penalty_pct                      DECIMAL(5,2),
    bonus_pct                        DECIMAL(5,2),
    bonus_threshold_hrs              DECIMAL(8,2),
    unit_rate_usd                    DECIMAL(18,4),
    contracted_units                 INT,
    overage_rate_usd                 DECIMAL(18,4),
    delivery_sla_pct                 DECIMAL(5,2),
    defect_sla_pct                   DECIMAL(5,2),
    document_page_count              INT,
    page_range                       STRING,
    loop_detection_summary           STRING,
    load_timestamp                    TIMESTAMP,
    record_source                    STRING
) USING DELTA
""")

# ----------------------------------------------------------------------------------------------
# 1B. BILLING / CUSTOMER / OPERATIONAL EVENTS TABLES (was 02_BILLING_..._INGESTION.sql STEP 1B)
# ----------------------------------------------------------------------------------------------

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {RAW}.customers (
    customer_id         STRING NOT NULL,
    customer_name       STRING NOT NULL,
    industry             STRING,
    segment              STRING,
    region                STRING,
    country               STRING,
    account_manager       STRING,
    arr_usd               DECIMAL(18,2),
    risk_score             DECIMAL(4,1),
    sf_account_id          STRING,
    load_timestamp          TIMESTAMP,
    record_source           STRING
) USING DELTA
""")

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {RAW}.billing_transactions (
    transaction_id       STRING NOT NULL,
    contract_id          STRING NOT NULL,
    customer_id          STRING NOT NULL,
    invoice_number        STRING,
    transaction_date      DATE NOT NULL,
    billing_period         STRING NOT NULL,
    service_type           STRING,
    quantity                DECIMAL(12,4),
    unit_price               DECIMAL(18,4),
    billed_amount            DECIMAL(18,2) NOT NULL,
    payment_status           STRING,
    sap_document_type        STRING,
    sap_company_code         STRING,
    load_timestamp             TIMESTAMP,
    record_source             STRING
) USING DELTA
""")

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {RAW}.operational_events (
    event_id             STRING NOT NULL,
    contract_id          STRING NOT NULL,
    customer_id          STRING NOT NULL,
    event_type            STRING NOT NULL,
    event_date             DATE NOT NULL,
    start_timestamp         TIMESTAMP,
    end_timestamp            TIMESTAMP,
    turnaround_hours          DECIMAL(8,2),
    procedure_code             STRING,
    service_code                STRING,
    quantity                     DECIMAL(12,4),
    reported_value                DECIMAL(18,2),
    delivery_pct                   DECIMAL(5,2),
    defect_pct                      DECIMAL(5,2),
    units_ordered                    INT,
    uptime_pct                        DECIMAL(7,4),
    user_count                         INT,
    overage_units                       INT,
    status                               STRING,
    load_timestamp                        TIMESTAMP,
    record_source                        STRING
) USING DELTA
""")

print("RAW layer tables created/verified in", RAW)
