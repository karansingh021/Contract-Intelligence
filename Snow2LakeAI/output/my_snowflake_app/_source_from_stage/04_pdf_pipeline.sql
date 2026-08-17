-- PDF pipeline: UDFs for contract classification/loop detection + extraction procedures
-- Co-authored with CoCo

CREATE OR ALTER VERSIONED SCHEMA app;
GRANT USAGE ON SCHEMA app TO APPLICATION ROLE app_user;
GRANT USAGE ON SCHEMA app TO APPLICATION ROLE app_admin;

-- ── Helper: current data mode ─────────────────────────────────────────────
CREATE OR REPLACE FUNCTION app.get_data_mode()
RETURNS STRING LANGUAGE SQL AS
$$ SELECT setting_value FROM config.app_settings WHERE setting_key='DATA_MODE' $$;
GRANT USAGE ON FUNCTION app.get_data_mode() TO APPLICATION ROLE app_user;

-- ── UDF: CONTRACT CLASS DETECTOR (12 categories) ──────────────────────────
CREATE OR REPLACE FUNCTION app.detect_contract_class(
    contract_type STRING, industry STRING, contract_text STRING
)
RETURNS STRING LANGUAGE SQL AS
$$
    CASE
        WHEN CONTAINS(LOWER(COALESCE(contract_type,'')), 'insurance')
          OR CONTAINS(LOWER(COALESCE(contract_text,'')), 'premium')
          OR CONTAINS(LOWER(COALESCE(contract_text,'')), 'policyholder')
        THEN 'Insurance'
        WHEN CONTAINS(LOWER(COALESCE(contract_type,'')), 'nda')
          OR CONTAINS(LOWER(COALESCE(contract_type,'')), 'non-disclosure')
        THEN 'NDA'
        WHEN CONTAINS(LOWER(COALESCE(contract_type,'')), 'employment')
          OR CONTAINS(LOWER(COALESCE(contract_type,'')), 'offer letter')
        THEN 'Employment'
        WHEN CONTAINS(LOWER(COALESCE(contract_type,'')), 'lease')
          OR CONTAINS(LOWER(COALESCE(contract_text,'')), 'landlord')
        THEN 'Lease'
        WHEN CONTAINS(LOWER(COALESCE(contract_type,'')), 'government')
          OR CONTAINS(LOWER(COALESCE(contract_text,'')), 'federal')
        THEN 'Government'
        WHEN CONTAINS(LOWER(COALESCE(contract_type,'')), 'procurement')
          OR CONTAINS(LOWER(COALESCE(contract_type,'')), 'purchase order')
        THEN 'Procurement'
        WHEN CONTAINS(LOWER(COALESCE(industry,'')), 'healthcare')
          OR CONTAINS(LOWER(COALESCE(contract_text,'')), 'hipaa')
        THEN 'Healthcare'
        WHEN CONTAINS(LOWER(COALESCE(industry,'')), 'financial')
          OR CONTAINS(LOWER(COALESCE(contract_text,'')), 'fiduciary')
        THEN 'Financial Services'
        WHEN CONTAINS(LOWER(COALESCE(contract_type,'')), 'saas')
          OR CONTAINS(LOWER(COALESCE(contract_type,'')), 'subscription')
        THEN 'SaaS'
        WHEN CONTAINS(LOWER(COALESCE(industry,'')), 'telecom')
          OR CONTAINS(LOWER(COALESCE(contract_text,'')), 'bandwidth')
        THEN 'Telecom'
        WHEN CONTAINS(LOWER(COALESCE(industry,'')), 'manufacturing')
          OR CONTAINS(LOWER(COALESCE(contract_text,'')), 'supply chain')
        THEN 'Manufacturing'
        ELSE 'Vendor'
    END
$$;

-- ── UDF: LOOP SIGNAL DETECTOR ─────────────────────────────────────────────
CREATE OR REPLACE FUNCTION app.detect_loop_signals(
    has_auto_renewal BOOLEAN, renewal_flag BOOLEAN, has_sla_terms BOOLEAN,
    payment_terms STRING, duration_days INTEGER, contracted_units INTEGER,
    contract_end_date DATE, annual_value_usd NUMBER, contract_type STRING
)
RETURNS VARIANT LANGUAGE SQL AS
$$
    OBJECT_CONSTRUCT(
        'auto_renewal', COALESCE(has_auto_renewal, FALSE),
        'renewal_flag', COALESCE(renewal_flag, FALSE),
        'evergreen_clause', IFF(contract_end_date IS NULL AND COALESCE(has_auto_renewal,FALSE), TRUE, FALSE),
        'recurring_payment', IFF(
            CONTAINS(LOWER(COALESCE(payment_terms,'')), 'monthly')
            OR CONTAINS(LOWER(COALESCE(payment_terms,'')), 'quarterly')
            OR CONTAINS(LOWER(COALESCE(payment_terms,'')), 'recurring'), TRUE, FALSE),
        'periodic_sla_review', IFF(COALESCE(has_sla_terms,FALSE) AND COALESCE(has_auto_renewal,FALSE), TRUE, FALSE),
        'rolling_period', IFF(COALESCE(duration_days,0) > 730 AND COALESCE(has_auto_renewal,FALSE), TRUE, FALSE),
        'high_value_renewal_risk', IFF(COALESCE(annual_value_usd,0) >= 5000000 AND COALESCE(has_auto_renewal,FALSE), TRUE, FALSE),
        'subscription_loop', IFF(
            CONTAINS(LOWER(COALESCE(contract_type,'')), 'subscription')
            OR CONTAINS(LOWER(COALESCE(contract_type,'')), 'usage based'), TRUE, FALSE)
    )::VARIANT
$$;

-- ── UDF: LOOP SUMMARY TEXT BUILDER ────────────────────────────────────────
CREATE OR REPLACE FUNCTION app.build_loop_summary(loop_signals VARIANT, termination_days INTEGER)
RETURNS STRING LANGUAGE SQL AS
$$
    CASE
        WHEN loop_signals IS NULL THEN 'NO LOOP DETECTED'
        WHEN loop_signals:auto_renewal::BOOLEAN = FALSE
         AND loop_signals:renewal_flag::BOOLEAN = FALSE
         AND loop_signals:recurring_payment::BOOLEAN = FALSE
         AND loop_signals:subscription_loop::BOOLEAN = FALSE
        THEN 'NO LOOP DETECTED'
        ELSE TRIM(CONCAT_WS('; ',
            IFF(loop_signals:auto_renewal::BOOLEAN = TRUE,
                CONCAT('Auto-renewal clause detected',
                    IFF(COALESCE(termination_days,0) > 0,
                        CONCAT(' with ', termination_days::STRING, '-day notice required'), '')), NULL),
            IFF(loop_signals:evergreen_clause::BOOLEAN = TRUE,
                'Evergreen clause: no fixed end date', NULL),
            IFF(loop_signals:recurring_payment::BOOLEAN = TRUE,
                'Recurring payment obligation detected', NULL),
            IFF(loop_signals:high_value_renewal_risk::BOOLEAN = TRUE,
                'HIGH VALUE: auto-renewal on contract >= USD 5M', NULL),
            IFF(loop_signals:subscription_loop::BOOLEAN = TRUE,
                'Subscription/usage-based — inherently recurring', NULL)
        ))
    END
$$;

-- ── UDF: REVIEW REASON BUILDER ────────────────────────────────────────────
CREATE OR REPLACE FUNCTION app.build_review_reason(
    annual_value_usd NUMBER, has_unlimited_liability BOOLEAN,
    has_auto_renewal BOOLEAN, termination_days INTEGER,
    contract_id STRING, customer_name STRING, contract_type STRING,
    contract_start_date DATE, contract_end_date DATE,
    unit_rate_usd NUMBER, contracted_units INTEGER,
    penalty_percent NUMBER, extraction_confidence FLOAT,
    risk_level STRING, loop_detection_summary STRING
)
RETURNS STRING LANGUAGE SQL AS
$$
    NULLIF(TRIM(CONCAT_WS('; ',
        IFF(COALESCE(annual_value_usd,0) >= 10000000,
            'High-value contract: >= USD 10M', NULL),
        IFF(COALESCE(has_unlimited_liability, FALSE) = TRUE,
            'Unlimited liability clause — legal review required', NULL),
        IFF(COALESCE(has_auto_renewal, FALSE) = TRUE,
            CONCAT('Auto-renewal clause present',
                IFF(COALESCE(termination_days,0) > 0,
                    CONCAT(' — requires ', termination_days::STRING, ' days notice'), '')), NULL),
        IFF(contract_id IS NULL, 'Missing: CONTRACT_ID', NULL),
        IFF(customer_name IS NULL, 'Missing: CUSTOMER_NAME', NULL),
        IFF(contract_start_date IS NULL, 'Missing: CONTRACT_START_DATE', NULL),
        IFF(contract_end_date IS NULL, 'Missing: CONTRACT_END_DATE', NULL),
        IFF(COALESCE(penalty_percent, 0) > 15,
            CONCAT('High penalty: ', penalty_percent::STRING, '%'), NULL),
        IFF(COALESCE(extraction_confidence, 1) < 0.5,
            'Low extraction confidence — manual review recommended', NULL),
        IFF(loop_detection_summary IS NOT NULL
            AND loop_detection_summary <> 'NO LOOP DETECTED',
            CONCAT('Loop: ', loop_detection_summary), NULL)
    )), '')
$$;

GRANT USAGE ON FUNCTION app.detect_contract_class(STRING,STRING,STRING) TO APPLICATION ROLE app_user;
GRANT USAGE ON FUNCTION app.detect_loop_signals(BOOLEAN,BOOLEAN,BOOLEAN,STRING,INTEGER,INTEGER,DATE,NUMBER,STRING) TO APPLICATION ROLE app_user;
GRANT USAGE ON FUNCTION app.build_loop_summary(VARIANT,INTEGER) TO APPLICATION ROLE app_user;
GRANT USAGE ON FUNCTION app.build_review_reason(NUMBER,BOOLEAN,BOOLEAN,INTEGER,STRING,STRING,STRING,DATE,DATE,NUMBER,INTEGER,NUMBER,FLOAT,STRING,STRING) TO APPLICATION ROLE app_user;

-- ══════════════════════════════════════════════════════════════════════════════
-- PROCEDURE: LOAD RAW PDFS
-- Strategy: Copy PDFs from consumer stage to app-internal stage using
-- COPY FILES, then use DIRECTORY() and PARSE_DOCUMENT() on the internal stage.
-- ══════════════════════════════════════════════════════════════════════════════
CREATE OR REPLACE PROCEDURE app.load_raw_pdfs()
RETURNS STRING
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python')
HANDLER = 'run'
AS
$$
import json

def run(session):
    # Get consumer stage from config
    rows = session.sql(
        "SELECT setting_value FROM config.app_settings WHERE setting_key='CONSUMER_STAGE'"
    ).collect()
    if not rows or not rows[0][0]:
        return "LOAD_RAW_PDFS: No consumer stage configured. Call CONFIG.SET_DATA_STAGE('<db.schema.stage>') first."
    consumer_stage = rows[0][0]

    try:
        session.sql(f"""
            COPY FILES INTO @raw.pdf_processing_stage/contracts/
            FROM @{consumer_stage}/contracts/
            PATTERN = '.*[.]pdf'
        """).collect()
    except Exception as e:
        err_msg = str(e)
        if 'does not exist' in err_msg.lower() or 'not authorized' in err_msg.lower():
            return f"LOAD_RAW_PDFS: Cannot access stage @{consumer_stage}. Ensure you have granted READ, WRITE on the stage to this application. Error: {err_msg[:150]}"
        if 'does not match any' in err_msg.lower() or 'no file' in err_msg.lower():
            return "LOAD_RAW_PDFS: 0 PDFs found in /contracts/ folder."
        return f"Error copying PDFs: {err_msg[:200]}"

    session.sql("ALTER STAGE raw.pdf_processing_stage REFRESH").collect()

    session.sql("""
        DELETE FROM raw.consumer_raw_pdfs
        WHERE FILE_NAME NOT IN (
            SELECT RELATIVE_PATH FROM DIRECTORY(@raw.pdf_processing_stage)
            WHERE RELATIVE_PATH ILIKE 'contracts/%.pdf'
        )
    """).collect()

    session.sql("""
        DELETE FROM raw.consumer_text_chunks
        WHERE FILE_NAME NOT IN (SELECT FILE_NAME FROM raw.consumer_raw_pdfs)
    """).collect()
    session.sql("""
        DELETE FROM raw.consumer_ai_extractions
        WHERE FILE_NAME NOT IN (SELECT FILE_NAME FROM raw.consumer_raw_pdfs)
    """).collect()
    session.sql("""
        DELETE FROM raw.consumer_master_contracts
        WHERE SOURCE_FILE NOT IN (SELECT FILE_NAME FROM raw.consumer_raw_pdfs)
          AND SOURCE_FILE IS NOT NULL
    """).collect()

    session.sql("""
        INSERT INTO raw.consumer_raw_pdfs (
            FILE_NAME, FILE_SIZE, LAST_MODIFIED, FILE_URL,
            OCR_TEXT, PARSED_JSON,
            DOCUMENT_PAGE_COUNT, DOCUMENT_PAGE_COUNT_ESTIMATED, DOCUMENT_PAGE_COUNT_FINAL,
            TEXT_CHAR_COUNT, TEXT_DENSITY_SCORE, IS_LIKELY_SCANNED,
            OCR_ENGINE_VERSION, OCR_STATUS, PIPELINE_RUN_ID
        )
        SELECT
            RELATIVE_PATH, SIZE, LAST_MODIFIED,
            BUILD_SCOPED_FILE_URL(@raw.pdf_processing_stage, RELATIVE_PATH),
            OCR_RESULT:content::STRING,
            LAYOUT_RESULT,
            ARRAY_SIZE(LAYOUT_RESULT:pages),
            GREATEST(CEIL(LENGTH(OCR_RESULT:content::STRING) / 800.0), 1),
            COALESCE(ARRAY_SIZE(LAYOUT_RESULT:pages),
                GREATEST(CEIL(LENGTH(OCR_RESULT:content::STRING) / 800.0), 1)),
            LENGTH(OCR_RESULT:content::STRING),
            LEAST(LENGTH(OCR_RESULT:content::STRING)
                / GREATEST(COALESCE(ARRAY_SIZE(LAYOUT_RESULT:pages),1) * 800.0, 1), 1.0),
            IFF(LENGTH(OCR_RESULT:content::STRING)
                / GREATEST(COALESCE(ARRAY_SIZE(LAYOUT_RESULT:pages),1) * 800.0, 1) < 0.4, TRUE, FALSE),
            'Snowflake Document AI v1',
            CASE WHEN OCR_RESULT:content IS NOT NULL AND LENGTH(TRIM(OCR_RESULT:content::STRING)) > 0
                 THEN 'SUCCESS' ELSE 'FAILED' END,
            UUID_STRING()
        FROM (
            SELECT RELATIVE_PATH, SIZE, LAST_MODIFIED,
                SNOWFLAKE.CORTEX.PARSE_DOCUMENT(
                    @raw.pdf_processing_stage, RELATIVE_PATH,
                    OBJECT_CONSTRUCT('mode', 'OCR')) AS OCR_RESULT,
                SNOWFLAKE.CORTEX.PARSE_DOCUMENT(
                    @raw.pdf_processing_stage, RELATIVE_PATH,
                    OBJECT_CONSTRUCT('mode', 'LAYOUT')) AS LAYOUT_RESULT
            FROM DIRECTORY(@raw.pdf_processing_stage)
            WHERE RELATIVE_PATH ILIKE 'contracts/%.pdf'
              AND RELATIVE_PATH NOT IN (SELECT FILE_NAME FROM raw.consumer_raw_pdfs)
        ) SRC
    """).collect()

    n = session.sql("SELECT COUNT(*) AS n FROM raw.consumer_raw_pdfs").collect()[0]["N"]
    new_count = session.sql("""
        SELECT COUNT(*) AS n FROM raw.consumer_raw_pdfs 
        WHERE INGESTION_TIMESTAMP > DATEADD('minute', -5, CURRENT_TIMESTAMP())
    """).collect()[0]["N"]
    return f"LOAD_RAW_PDFS: {n} total ({new_count} new, {n - new_count} cached)."
$$;

-- ── PROCEDURE: CREATE TEXT CHUNKS ─────────────────────────────────────────
CREATE OR REPLACE PROCEDURE app.create_text_chunks()
RETURNS STRING LANGUAGE SQL AS
$$
BEGIN
    INSERT INTO raw.consumer_text_chunks (
        FILE_NAME, PIPELINE_RUN_ID, CHUNK_ID, CHUNK_TEXT, CHUNK_SIZE,
        CHUNK_TOKEN_ESTIMATE, CHUNK_SEQUENCE_START, CHUNK_SEQUENCE_END,
        TOTAL_CHUNKS, DOCUMENT_PAGE_COUNT,
        FIRST_PAGE, LAST_PAGE, PAGE_RANGE, TEXT_DENSITY_SCORE,
        IS_FINAL_CHUNK, IS_TRUNCATED, NEEDS_RECHUNKING
    )
    SELECT
        FILE_NAME, PIPELINE_RUN_ID, CHUNK_ID, CHUNK_TEXT, CHUNK_SIZE,
        CEIL(CHUNK_SIZE / 4),
        CHUNK_SEQ_START, CHUNK_SEQ_END,
        MAX(CHUNK_ID) OVER (PARTITION BY FILE_NAME),
        DOCUMENT_PAGE_COUNT,
        GREATEST(CEIL(CHUNK_SEQ_START::FLOAT / NULLIF(DOC_CHAR_COUNT::FLOAT / NULLIF(DOCUMENT_PAGE_COUNT,1),0))::INTEGER, 1),
        LEAST(CEIL(CHUNK_SEQ_END::FLOAT / NULLIF(DOC_CHAR_COUNT::FLOAT / NULLIF(DOCUMENT_PAGE_COUNT,1),0))::INTEGER, DOCUMENT_PAGE_COUNT),
        CONCAT('Pages ', GREATEST(CEIL(CHUNK_SEQ_START::FLOAT / NULLIF(DOC_CHAR_COUNT::FLOAT / NULLIF(DOCUMENT_PAGE_COUNT,1),0))::INTEGER,1)::STRING,
            '-', LEAST(CEIL(CHUNK_SEQ_END::FLOAT / NULLIF(DOC_CHAR_COUNT::FLOAT / NULLIF(DOCUMENT_PAGE_COUNT,1),0))::INTEGER, DOCUMENT_PAGE_COUNT)::STRING,
            ' of ', DOCUMENT_PAGE_COUNT::STRING),
        LEAST(CHUNK_SIZE / GREATEST(DOCUMENT_PAGE_COUNT * 800.0, 1), 1.0),
        IFF(CHUNK_ID = MAX(CHUNK_ID) OVER (PARTITION BY FILE_NAME), TRUE, FALSE),
        IFF(CHUNK_SIZE >= 3990, TRUE, FALSE),
        IFF(CEIL(CHUNK_SIZE / 4) > 3000, TRUE, FALSE)
    FROM (
        SELECT
            R.FILE_NAME, R.PIPELINE_RUN_ID,
            GREATEST(R.DOCUMENT_PAGE_COUNT_FINAL, 1) AS DOCUMENT_PAGE_COUNT,
            GREATEST(R.TEXT_CHAR_COUNT, 1) AS DOC_CHAR_COUNT,
            G.SEQ + 1 AS CHUNK_ID,
            SUBSTR(R.OCR_TEXT, (G.SEQ * 4000) + 1, 4000) AS CHUNK_TEXT,
            LENGTH(SUBSTR(R.OCR_TEXT, (G.SEQ * 4000) + 1, 4000)) AS CHUNK_SIZE,
            (G.SEQ * 4000) + 1 AS CHUNK_SEQ_START,
            LEAST((G.SEQ * 4000) + 4000, LENGTH(R.OCR_TEXT)) AS CHUNK_SEQ_END
        FROM raw.consumer_raw_pdfs R,
        LATERAL (SELECT SEQ4() AS SEQ FROM TABLE(GENERATOR(ROWCOUNT => 1000))) G
        WHERE UPPER(COALESCE(R.OCR_STATUS,'FAILED')) = 'SUCCESS'
          AND R.OCR_TEXT IS NOT NULL AND LENGTH(TRIM(R.OCR_TEXT)) > 0
          AND (G.SEQ * 4000) < LENGTH(R.OCR_TEXT)
          AND R.FILE_NAME NOT IN (SELECT DISTINCT FILE_NAME FROM raw.consumer_text_chunks)
    ) FINAL_CHUNKS;
    RETURN 'CREATE_TEXT_CHUNKS: ' || (SELECT COUNT(*) FROM raw.consumer_text_chunks) || ' chunks.';
END;
$$;

-- ── PROCEDURE: EXTRACT WITH AI ────────────────────────────────────────────
CREATE OR REPLACE PROCEDURE app.extract_contract_chunks_ai()
RETURNS STRING LANGUAGE SQL AS
$$
DECLARE
    extraction_prompt STRING;
BEGIN
    extraction_prompt := 'You are an enterprise contract intelligence AI. IMPORTANT: Return ONLY the raw JSON object. Do NOT include any text, explanation, markdown formatting, or code blocks. Start your response with { and end with }. Booleans: true/false. Numbers: digits only. Dates: YYYY-MM-DD or "".
JSON SCHEMA: {"contract_id":"","customer_id":"","customer_name":"","vendor_name":"","contract_type":"","industry":"","status":"","contract_start_date":"","contract_end_date":"","termination_notice_days":"","contract_duration_days":"","annual_value_usd":"","total_contract_value_usd":"","unit_rate_usd":"","contracted_units":"","overage_rate_usd":"","payment_terms":"","sla_hours":"","penalty_percent":"","bonus_percent":"","bonus_threshold_hrs":"","delivery_sla_percent":"","defect_sla_pct":"","has_auto_renewal":false,"has_unlimited_liability":false,"has_sla_terms":false,"renewal_flag":false,"risk_level":"","needs_human_review":false,"review_reason":"","extraction_confidence":"","has_repeated_clauses":false,"loop_detection_summary":"","repeated_clause_count":0}';

    INSERT INTO raw.consumer_ai_extractions (
        FILE_NAME, CHUNK_ID, PIPELINE_RUN_ID, EXTRACTION_RAW, EXTRACTION_STATUS
    )
    SELECT
        FILE_NAME, CHUNK_ID, PIPELINE_RUN_ID,
        SNOWFLAKE.CORTEX.COMPLETE('mistral-large2',
            :extraction_prompt || '\n\nCONTRACT TEXT:\n' || CHUNK_TEXT
        ),
        'PASS_1'
    FROM raw.consumer_text_chunks
    WHERE (FILE_NAME, CHUNK_ID) NOT IN (
        SELECT FILE_NAME, CHUNK_ID FROM raw.consumer_ai_extractions
    );

    -- Clean up markdown code block wrappers from LLM output
    UPDATE raw.consumer_ai_extractions
    SET EXTRACTION_RAW = TRIM(REGEXP_SUBSTR(EXTRACTION_RAW, '\\{[\\s\\S]*\\}'))
    WHERE EXTRACTION_STATUS = 'PASS_1'
      AND TRY_PARSE_JSON(EXTRACTION_RAW) IS NULL
      AND EXTRACTION_RAW LIKE '%{%}%';

    RETURN 'EXTRACT_AI: ' || (SELECT COUNT(*) FROM raw.consumer_ai_extractions) || ' extractions.';
END;
$$;

-- ── PROCEDURE: BUILD MASTER CONTRACTS ─────────────────────────────────────
CREATE OR REPLACE PROCEDURE app.build_master_contracts()
RETURNS STRING LANGUAGE SQL AS
$$
BEGIN
    TRUNCATE TABLE raw.consumer_master_contracts;
    INSERT INTO raw.consumer_master_contracts (
        CONTRACT_ID, CUSTOMER_ID, CUSTOMER_NAME, VENDOR_NAME, CONTRACT_TYPE, INDUSTRY, STATUS,
        CONTRACT_START_DATE, CONTRACT_END_DATE, TERMINATION_NOTICE_DAYS, CONTRACT_DURATION_DAYS,
        ANNUAL_VALUE_USD, TOTAL_CONTRACT_VALUE_USD, UNIT_RATE_USD, CONTRACTED_UNITS, OVERAGE_RATE_USD,
        PAYMENT_TERMS, SLA_HOURS, PENALTY_PCT, BONUS_PCT, BONUS_THRESHOLD_HRS,
        DELIVERY_SLA_PCT, DEFECT_SLA_PCT,
        HAS_AUTO_RENEWAL, HAS_UNLIMITED_LIABILITY, HAS_SLA_TERMS, RENEWAL_FLAG,
        RISK_LEVEL, NEEDS_HUMAN_REVIEW, REVIEW_REASON, EXTRACTION_CONFIDENCE,
        HAS_REPEATED_CLAUSES, LOOP_DETECTION_SUMMARY, REPEATED_CLAUSE_COUNT,
        SOURCE_FILE
    )
    SELECT
        TRIM(PARSED:contract_id::STRING),
        TRIM(PARSED:customer_id::STRING),
        TRIM(PARSED:customer_name::STRING),
        TRIM(PARSED:vendor_name::STRING),
        TRIM(PARSED:contract_type::STRING),
        TRIM(PARSED:industry::STRING),
        TRIM(PARSED:status::STRING),
        TRY_TO_DATE(PARSED:contract_start_date::STRING),
        TRY_TO_DATE(PARSED:contract_end_date::STRING),
        TRY_TO_NUMBER(PARSED:termination_notice_days::STRING),
        TRY_TO_NUMBER(PARSED:contract_duration_days::STRING),
        TRY_TO_NUMBER(PARSED:annual_value_usd::STRING, 18, 2),
        TRY_TO_NUMBER(PARSED:total_contract_value_usd::STRING, 18, 2),
        TRY_TO_NUMBER(PARSED:unit_rate_usd::STRING, 18, 4),
        TRY_TO_NUMBER(PARSED:contracted_units::STRING),
        TRY_TO_NUMBER(PARSED:overage_rate_usd::STRING, 18, 4),
        TRIM(PARSED:payment_terms::STRING),
        TRY_TO_NUMBER(PARSED:sla_hours::STRING, 8, 2),
        TRY_TO_NUMBER(PARSED:penalty_percent::STRING, 5, 2),
        TRY_TO_NUMBER(PARSED:bonus_percent::STRING, 5, 2),
        TRY_TO_NUMBER(PARSED:bonus_threshold_hrs::STRING, 8, 2),
        TRY_TO_NUMBER(PARSED:delivery_sla_percent::STRING, 5, 2),
        TRY_TO_NUMBER(PARSED:defect_sla_pct::STRING, 5, 2),
        PARSED:has_auto_renewal::BOOLEAN,
        PARSED:has_unlimited_liability::BOOLEAN,
        PARSED:has_sla_terms::BOOLEAN,
        PARSED:renewal_flag::BOOLEAN,
        TRIM(PARSED:risk_level::STRING),
        PARSED:needs_human_review::BOOLEAN,
        TRIM(PARSED:review_reason::STRING),
        TRY_TO_NUMBER(PARSED:extraction_confidence::STRING, 3, 2),
        PARSED:has_repeated_clauses::BOOLEAN,
        TRIM(PARSED:loop_detection_summary::STRING),
        TRY_TO_NUMBER(PARSED:repeated_clause_count::STRING),
        FILE_NAME
    FROM (
        SELECT FILE_NAME, CHUNK_ID,
            TRY_PARSE_JSON(EXTRACTION_RAW) AS PARSED
        FROM raw.consumer_ai_extractions
        WHERE EXTRACTION_STATUS = 'PASS_1'
    ) cleaned
    WHERE PARSED IS NOT NULL
      AND TRIM(PARSED:contract_id::STRING) IS NOT NULL
      AND TRIM(PARSED:contract_id::STRING) <> ''
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY TRIM(PARSED:contract_id::STRING)
        ORDER BY FILE_NAME, CHUNK_ID
    ) = 1;

    -- ── SQL ENRICHMENT PASS ──────────────────────────────────────────────────
    UPDATE raw.consumer_master_contracts
    SET CONTRACT_DURATION_DAYS = DATEDIFF('day', CONTRACT_START_DATE, CONTRACT_END_DATE)
    WHERE CONTRACT_DURATION_DAYS IS NULL
      AND CONTRACT_START_DATE IS NOT NULL
      AND CONTRACT_END_DATE IS NOT NULL
      AND CONTRACT_END_DATE > CONTRACT_START_DATE;

    UPDATE raw.consumer_master_contracts
    SET TOTAL_CONTRACT_VALUE_USD = ROUND(ANNUAL_VALUE_USD * (CONTRACT_DURATION_DAYS / 365.0), 2)
    WHERE TOTAL_CONTRACT_VALUE_USD IS NULL
      AND ANNUAL_VALUE_USD IS NOT NULL AND ANNUAL_VALUE_USD > 0
      AND CONTRACT_DURATION_DAYS IS NOT NULL AND CONTRACT_DURATION_DAYS > 0;

    UPDATE raw.consumer_master_contracts
    SET HAS_REPEATED_CLAUSES = TRUE,
        REPEATED_CLAUSE_COUNT = GREATEST(COALESCE(REPEATED_CLAUSE_COUNT, 0), 1)
    WHERE (HAS_AUTO_RENEWAL = TRUE OR RENEWAL_FLAG = TRUE
           OR CONTAINS(LOWER(COALESCE(PAYMENT_TERMS,'')), 'monthly')
           OR CONTAINS(LOWER(COALESCE(PAYMENT_TERMS,'')), 'quarterly')
           OR CONTAINS(LOWER(COALESCE(PAYMENT_TERMS,'')), 'recurring'))
      AND COALESCE(HAS_REPEATED_CLAUSES, FALSE) = FALSE;

    UPDATE raw.consumer_master_contracts
    SET LOOP_DETECTION_SUMMARY = app.build_loop_summary(
            app.detect_loop_signals(
                HAS_AUTO_RENEWAL, RENEWAL_FLAG, HAS_SLA_TERMS,
                PAYMENT_TERMS, CONTRACT_DURATION_DAYS, CONTRACTED_UNITS,
                CONTRACT_END_DATE, ANNUAL_VALUE_USD, CONTRACT_TYPE
            ),
            TERMINATION_NOTICE_DAYS
        )
    WHERE LOOP_DETECTION_SUMMARY IS NULL
       OR LOOP_DETECTION_SUMMARY = ''
       OR LOOP_DETECTION_SUMMARY = 'NO LOOP DETECTED';

    UPDATE raw.consumer_master_contracts
    SET REVIEW_REASON = app.build_review_reason(
            ANNUAL_VALUE_USD, HAS_UNLIMITED_LIABILITY, HAS_AUTO_RENEWAL,
            TERMINATION_NOTICE_DAYS, CONTRACT_ID, CUSTOMER_NAME, CONTRACT_TYPE,
            CONTRACT_START_DATE, CONTRACT_END_DATE,
            UNIT_RATE_USD, CONTRACTED_UNITS, PENALTY_PCT,
            EXTRACTION_CONFIDENCE, RISK_LEVEL, LOOP_DETECTION_SUMMARY
        )
    WHERE (REVIEW_REASON IS NULL OR REVIEW_REASON = '')
      AND NEEDS_HUMAN_REVIEW = TRUE;

    -- Enrich CUSTOMER_ID from CRM table by matching customer name
    UPDATE raw.consumer_master_contracts mc
    SET CUSTOMER_ID = cu.CUSTOMER_ID
    FROM raw.consumer_customers_local cu
    WHERE (mc.CUSTOMER_ID IS NULL OR mc.CUSTOMER_ID = '')
      AND UPPER(TRIM(mc.CUSTOMER_NAME)) = UPPER(TRIM(cu.CUSTOMER_NAME));

    RETURN 'BUILD_MASTER: ' || (SELECT COUNT(*) FROM raw.consumer_master_contracts) || ' contracts (enriched).';
END;
$$;

-- ── ORCHESTRATOR: RUN PDF PIPELINE ────────────────────────────────────────
CREATE OR REPLACE PROCEDURE app.run_pdf_pipeline()
RETURNS STRING LANGUAGE SQL AS
$$
DECLARE
    msg1 STRING; msg2 STRING; msg3 STRING; msg4 STRING;
BEGIN
    CALL app.load_raw_pdfs();
    SELECT * INTO :msg1 FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()));
    CALL app.create_text_chunks();
    SELECT * INTO :msg2 FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()));
    CALL app.extract_contract_chunks_ai();
    SELECT * INTO :msg3 FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()));
    CALL app.build_master_contracts();
    SELECT * INTO :msg4 FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()));
    RETURN msg1 || ' | ' || msg2 || ' | ' || msg3 || ' | ' || msg4;
END;
$$;

GRANT USAGE ON PROCEDURE app.load_raw_pdfs() TO APPLICATION ROLE app_admin;
GRANT USAGE ON PROCEDURE app.create_text_chunks() TO APPLICATION ROLE app_admin;
GRANT USAGE ON PROCEDURE app.extract_contract_chunks_ai() TO APPLICATION ROLE app_admin;
GRANT USAGE ON PROCEDURE app.build_master_contracts() TO APPLICATION ROLE app_admin;
GRANT USAGE ON PROCEDURE app.run_pdf_pipeline() TO APPLICATION ROLE app_admin;
