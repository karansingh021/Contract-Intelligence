-- Unified ingestion pipeline: processes PDF, JSON, CSV from consumer stage using stored path
-- Co-authored with CoCo

-- ── File formats ──────────────────────────────────────────────────────────
CREATE FILE FORMAT IF NOT EXISTS app.json_format
    TYPE = 'JSON'
    STRIP_OUTER_ARRAY = FALSE
    IGNORE_UTF8_ERRORS = TRUE;

CREATE FILE FORMAT IF NOT EXISTS app.csv_format
    TYPE = 'CSV'
    SKIP_HEADER = 1
    FIELD_OPTIONALLY_ENCLOSED_BY = '"'
    TRIM_SPACE = TRUE
    ERROR_ON_COLUMN_COUNT_MISMATCH = FALSE;

CREATE FILE FORMAT IF NOT EXISTS app.csv_header_format
    TYPE = 'CSV'
    SKIP_HEADER = 0
    FIELD_DELIMITER = NONE
    RECORD_DELIMITER = '\n';

-- ── Helper: detect JSON field names from consumer stage ───────────────────
CREATE OR REPLACE PROCEDURE app.detect_json_fields(file_pattern STRING)
RETURNS STRING
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python')
HANDLER = 'run'
AS
$$
import json
def run(session, file_pattern):
    try:
        rows = session.sql("SELECT setting_value FROM config.app_settings WHERE setting_key='CONSUMER_STAGE'").collect()
        if not rows or not rows[0][0]:
            return json.dumps({"error": "No consumer stage configured"})
        stage = rows[0][0]
        # Handle both single JSON objects and arrays of objects
        # If top-level is array, flatten the first element; if object, flatten directly
        result = session.sql(f"""
            SELECT DISTINCT f.key
            FROM (
                SELECT CASE
                    WHEN IS_ARRAY(PARSE_JSON($1)) THEN GET(PARSE_JSON($1), 0)
                    ELSE PARSE_JSON($1)
                END AS obj
                FROM @{stage} (FILE_FORMAT => 'app.json_format', PATTERN => '{file_pattern}')
                LIMIT 1
            ) s,
            LATERAL FLATTEN(INPUT => s.obj) f
            WHERE f.key IS NOT NULL
        """).collect()
        return json.dumps([r["KEY"] for r in result if r["KEY"] is not None])
    except Exception as e:
        return json.dumps({"error": str(e)[:200]})
$$;
GRANT USAGE ON PROCEDURE app.detect_json_fields(STRING) TO APPLICATION ROLE app_admin;

-- ── Helper: detect CSV field names from consumer stage ────────────────────
CREATE OR REPLACE PROCEDURE app.detect_csv_fields(file_pattern STRING)
RETURNS STRING
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python')
HANDLER = 'run'
AS
$$
import json
def run(session, file_pattern):
    try:
        rows = session.sql("SELECT setting_value FROM config.app_settings WHERE setting_key='CONSUMER_STAGE'").collect()
        if not rows or not rows[0][0]:
            return json.dumps({"error": "No consumer stage configured"})
        stage = rows[0][0]
        result = session.sql(f"""
            SELECT $1 AS header_row
            FROM @{stage} (FILE_FORMAT => 'app.csv_header_format', PATTERN => '{file_pattern}')
            LIMIT 1
        """).collect()
        if result and result[0]["HEADER_ROW"]:
            headers = [h.strip().strip('"') for h in result[0]["HEADER_ROW"].split(",")]
            return json.dumps(headers)
    except Exception as e:
        return json.dumps({"error": str(e)[:200]})
    return "[]"
$$;
GRANT USAGE ON PROCEDURE app.detect_csv_fields(STRING) TO APPLICATION ROLE app_admin;

-- ── UNIFIED INGESTION PIPELINE ────────────────────────────────────────────
CREATE OR REPLACE PROCEDURE app.run_ingestion_pipeline()
RETURNS STRING
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python')
HANDLER = 'run'
AS
$$
import json

def run(session):
    results = []

    # Get consumer stage from config
    rows = session.sql(
        "SELECT setting_value FROM config.app_settings WHERE setting_key='CONSUMER_STAGE'"
    ).collect()
    if not rows or not rows[0][0]:
        return "Ingestion failed: No consumer stage configured. Call CONFIG.SET_DATA_STAGE('<db.schema.stage>') first."
    stage_ref = rows[0][0]

    # 1. Contract PDFs
    try:
        res = session.sql("CALL app.run_pdf_pipeline()").collect()
        n = session.sql("SELECT COUNT(*) AS n FROM raw.consumer_master_contracts").collect()[0]["N"]
        results.append(f"{n} contracts (PDF)")
    except Exception as e:
        results.append(f"0 contracts (PDF) - {str(e)[:80]}")

    # Helper: get column mappings
    def get_mappings(source_name, default_fields):
        rows = session.sql(f"SELECT app_column, consumer_column FROM config.column_mappings WHERE reference_name = '{source_name}'").collect()
        mappings = {r["APP_COLUMN"]: r["CONSUMER_COLUMN"] for r in rows}
        for field in default_fields:
            if field.upper() not in mappings:
                mappings[field.upper()] = field
        return mappings

    # 2. CRM (individual JSON files — one object per file, e.g. SF_ACCOUNT_*.json)
    # All fields are mappable via UI. Defaults match Salesforce export format.
    # Auto-populated fallbacks: ACCOUNT_MANAGER (random), ARR_USD (random), RISK_SCORE (random), SF_ACCOUNT_ID (derived)
    # Defaults (table-level): LOAD_TIMESTAMP, RECORD_SOURCE
    crm_fields = ["customer_id", "customer_name", "industry", "segment", "region", "country",
                  "account_manager", "arr_usd", "risk_score", "sf_account_id"]
    crm_default_map = {
        "CUSTOMER_ID": "_internal_customer_id", "CUSTOMER_NAME": "Name",
        "INDUSTRY": "_industry_internal", "SEGMENT": "_segment",
        "REGION": "_region", "COUNTRY": "BillingCountry",
        "ACCOUNT_MANAGER": "_account_manager", "ARR_USD": "AnnualRevenue",
        "RISK_SCORE": "_risk_score", "SF_ACCOUNT_ID": "Id"
    }
    try:
        saved_mappings = {}
        try:
            rows = session.sql("SELECT app_column, consumer_column FROM config.column_mappings WHERE reference_name = 'crm'").collect()
            saved_mappings = {r["APP_COLUMN"]: r["CONSUMER_COLUMN"] for r in rows}
        except Exception:
            pass

        # Resolve: user mapping > default map > identity
        def crm_col(app_field):
            key = saved_mappings.get(app_field, crm_default_map.get(app_field, app_field.lower()))
            # Sanitize JSON key: wrap in quotes for safety with special characters
            return '"' + key.replace('"', '\\"') + '"'

        c = {f.upper(): f"t.$1:{crm_col(f.upper())}::STRING" for f in crm_fields}

        sql = f"""INSERT INTO raw.consumer_customers_local
            (CUSTOMER_ID, CUSTOMER_NAME, INDUSTRY, SEGMENT, REGION, COUNTRY,
             ACCOUNT_MANAGER, ARR_USD, RISK_SCORE, SF_ACCOUNT_ID)
            SELECT
                {c['CUSTOMER_ID']},
                {c['CUSTOMER_NAME']},
                COALESCE({c['INDUSTRY']}, t.$1:Industry::STRING, 'Unknown'),
                COALESCE({c['SEGMENT']}, 'Unknown'),
                COALESCE({c['REGION']}, 'Unknown'),
                COALESCE({c['COUNTRY']}, 'US'),
                COALESCE({c['ACCOUNT_MANAGER']}, t.$1:OwnerName::STRING, 'AM_' || UNIFORM(100,999,RANDOM())::STRING),
                COALESCE(TRY_TO_NUMBER({c['ARR_USD']}, 18, 2), UNIFORM(50000,5000000,RANDOM())::NUMBER(18,2)),
                COALESCE(TRY_TO_NUMBER({c['RISK_SCORE']}, 4, 1), ROUND(UNIFORM(10,95,RANDOM())/10, 1)),
                COALESCE({c['SF_ACCOUNT_ID']}, 'SF_' || RIGHT({c['CUSTOMER_ID']}, 8))
            FROM @{stage_ref} (FILE_FORMAT => 'app.json_format', PATTERN => '.*crm/.*[.]json') AS t
            WHERE {c['CUSTOMER_ID']} IS NOT NULL"""
        session.sql("TRUNCATE TABLE raw.consumer_customers_local").collect()
        session.sql(sql).collect()
        n = session.sql("SELECT COUNT(*) AS n FROM raw.consumer_customers_local").collect()[0]["N"]
        results.append(f"{n} customers (CRM)")
    except Exception as e:
        results.append(f"0 customers (CRM) - {str(e)[:80]}")

    # 3. ERP/Billing (CSV — VBRK header table, matching original pipeline)
    # Mappable fields (configurable via UI): contract_id, customer_id, invoice_number,
    #   transaction_date, billed_amount, billing_period_year, billing_period_month,
    #   service_type, payment_status, sap_document_type, sap_company_code
    # Auto-populated: TRANSACTION_ID (UUID), QUANTITY (1), UNIT_PRICE (=BILLED_AMOUNT)
    # Defaults (table-level): LOAD_TIMESTAMP, RECORD_SOURCE
    erp_default_map = {
        "CONTRACT_ID": "_CONTRACT_ID", "CUSTOMER_ID": "KUNAG", "INVOICE_NUMBER": "VBELN",
        "TRANSACTION_DATE": "FKDAT", "BILLED_AMOUNT": "NETWR",
        "BILLING_PERIOD_YEAR": "GJAHR", "BILLING_PERIOD_MONTH": "POPER",
        "SERVICE_TYPE": "_INDUSTRY", "PAYMENT_STATUS": "_HAS_MISMATCH",
        "SAP_DOCUMENT_TYPE": "FKART", "SAP_COMPANY_CODE": "BUKRS"
    }
    erp_fields = [k.lower() for k in erp_default_map.keys()]
    try:
        saved_mappings = {}
        try:
            rows = session.sql("SELECT app_column, consumer_column FROM config.column_mappings WHERE reference_name = 'erp'").collect()
            saved_mappings = {r["APP_COLUMN"]: r["CONSUMER_COLUMN"] for r in rows}
        except Exception:
            pass

        # Resolve: user mapping > default map > identity
        def resolve(app_col):
            return saved_mappings.get(app_col, erp_default_map.get(app_col, app_col)).upper()

        header_rows = session.sql(f"SELECT t.$1 AS h FROM @{stage_ref} (FILE_FORMAT => 'app.csv_header_format', PATTERN => '.*erp/.*[.]csv') AS t LIMIT 1").collect()
        if header_rows and header_rows[0]["H"]:
            headers = [h.strip().strip('"').upper() for h in header_rows[0]["H"].split(",")]
            pos_map = {h: i+1 for i, h in enumerate(headers)}

            # Build positional references using resolved mappings
            def col(app_field):
                csv_col = resolve(app_field)
                p = pos_map.get(csv_col)
                return f"t.${p}::STRING" if p else "NULL"

            sql = f"""INSERT INTO raw.consumer_billing_local
                (TRANSACTION_ID, CONTRACT_ID, CUSTOMER_ID, INVOICE_NUMBER, TRANSACTION_DATE,
                 BILLING_PERIOD, SERVICE_TYPE, QUANTITY, UNIT_PRICE, BILLED_AMOUNT,
                 PAYMENT_STATUS, SAP_DOCUMENT_TYPE, SAP_COMPANY_CODE)
                SELECT
                    UUID_STRING(),
                    {col('CONTRACT_ID')},
                    {col('CUSTOMER_ID')},
                    {col('INVOICE_NUMBER')},
                    COALESCE(TRY_TO_DATE({col('TRANSACTION_DATE')}), TRY_TO_DATE({col('TRANSACTION_DATE')}, 'YYYYMMDD')),
                    COALESCE({col('BILLING_PERIOD_YEAR')} || '-' || LPAD({col('BILLING_PERIOD_MONTH')}, 2, '0'), 'UNKNOWN'),
                    COALESCE({col('SERVICE_TYPE')}, 'GENERAL'),
                    1,
                    TRY_TO_NUMBER(REGEXP_REPLACE({col('BILLED_AMOUNT')}, '[^0-9.-]', ''), 18, 4),
                    TRY_TO_NUMBER(REGEXP_REPLACE({col('BILLED_AMOUNT')}, '[^0-9.-]', ''), 18, 2),
                    CASE WHEN {col('PAYMENT_STATUS')} ILIKE 'TRUE' THEN 'REVIEW' ELSE 'PAID' END,
                    {col('SAP_DOCUMENT_TYPE')},
                    {col('SAP_COMPANY_CODE')}
                FROM @{stage_ref} (FILE_FORMAT => 'app.csv_format', PATTERN => '.*erp/.*[.]csv') AS t"""
            session.sql("TRUNCATE TABLE raw.consumer_billing_local").collect()
            session.sql(sql).collect()
            n = session.sql("SELECT COUNT(*) AS n FROM raw.consumer_billing_local").collect()[0]["N"]
            results.append(f"{n} billing (ERP)")
        else:
            results.append("0 billing (ERP) - no CSV headers found in erp/ folder")
    except Exception as e:
        results.append(f"0 billing (ERP) - {str(e)[:80]}")

    # 4. OPS/Events (individual JSON files — one object per file)
    # ALL fields are mappable via UI. Defaults match the generated data format.
    ops_default_map = {
        "EVENT_ID": "event_id", "CONTRACT_ID": "contract_ref", "CUSTOMER_ID": "customer_ref",
        "EVENT_TYPE": "event_type", "EVENT_DATE": "event_date",
        "START_TIMESTAMP": "start_timestamp", "END_TIMESTAMP": "end_timestamp",
        "TURNAROUND_HOURS": "turnaround_hours", "PROCEDURE_CODE": "procedure_code",
        "SERVICE_CODE": "service_code", "QUANTITY": "quantity",
        "REPORTED_VALUE": "reported_value", "DELIVERY_PCT": "delivery_pct",
        "DEFECT_PCT": "defect_pct", "UNITS_ORDERED": "units_ordered",
        "UPTIME_PCT": "uptime_pct", "USER_COUNT": "user_count",
        "OVERAGE_UNITS": "overage_units", "STATUS": "status",
        "RECORD_SOURCE": "record_source"
    }
    ops_fields = [k.lower() for k in ops_default_map.keys()]
    try:
        saved_mappings = {}
        try:
            rows = session.sql("SELECT app_column, consumer_column FROM config.column_mappings WHERE reference_name = 'ops'").collect()
            saved_mappings = {r["APP_COLUMN"]: r["CONSUMER_COLUMN"] for r in rows}
        except Exception:
            pass

        # Resolve: user mapping > default map > identity
        def ops_key(app_col):
            key = saved_mappings.get(app_col, ops_default_map.get(app_col, app_col.lower()))
            # Sanitize JSON key: wrap in quotes for safety with special characters
            return '"' + key.replace('"', '\\"') + '"'

        sql = f"""INSERT INTO raw.consumer_events_local
            (EVENT_ID, CONTRACT_ID, CUSTOMER_ID, EVENT_TYPE, EVENT_DATE,
             START_TIMESTAMP, END_TIMESTAMP, TURNAROUND_HOURS,
             PROCEDURE_CODE, SERVICE_CODE, QUANTITY,
             REPORTED_VALUE, DELIVERY_PCT, DEFECT_PCT,
             UNITS_ORDERED, UPTIME_PCT, USER_COUNT, OVERAGE_UNITS, STATUS,
             RECORD_SOURCE)
            SELECT
                t.$1:{ops_key('EVENT_ID')}::STRING,
                t.$1:{ops_key('CONTRACT_ID')}::STRING,
                t.$1:{ops_key('CUSTOMER_ID')}::STRING,
                t.$1:{ops_key('EVENT_TYPE')}::STRING,
                TRY_TO_DATE(t.$1:{ops_key('EVENT_DATE')}::STRING),
                TRY_TO_TIMESTAMP_TZ(t.$1:{ops_key('START_TIMESTAMP')}::STRING),
                TRY_TO_TIMESTAMP_TZ(t.$1:{ops_key('END_TIMESTAMP')}::STRING),
                t.$1:{ops_key('TURNAROUND_HOURS')}::NUMBER(8,2),
                t.$1:{ops_key('PROCEDURE_CODE')}::STRING,
                t.$1:{ops_key('SERVICE_CODE')}::STRING,
                t.$1:{ops_key('QUANTITY')}::NUMBER(12,4),
                t.$1:{ops_key('REPORTED_VALUE')}::NUMBER(18,2),
                t.$1:{ops_key('DELIVERY_PCT')}::NUMBER(5,2),
                t.$1:{ops_key('DEFECT_PCT')}::NUMBER(5,2),
                t.$1:{ops_key('UNITS_ORDERED')}::INTEGER,
                t.$1:{ops_key('UPTIME_PCT')}::NUMBER(7,4),
                t.$1:{ops_key('USER_COUNT')}::INTEGER,
                t.$1:{ops_key('OVERAGE_UNITS')}::INTEGER,
                COALESCE(t.$1:{ops_key('STATUS')}::STRING, 'COMPLETED'),
                t.$1:{ops_key('RECORD_SOURCE')}::STRING
            FROM @{stage_ref} (FILE_FORMAT => 'app.json_format', PATTERN => '.*ops/.*[.]json') AS t
            WHERE t.$1:{ops_key('EVENT_ID')} IS NOT NULL"""
        session.sql("TRUNCATE TABLE raw.consumer_events_local").collect()
        session.sql(sql).collect()
        n = session.sql("SELECT COUNT(*) AS n FROM raw.consumer_events_local").collect()[0]["N"]
        results.append(f"{n} events (OPS)")
    except Exception as e:
        results.append(f"0 events (OPS) - {str(e)[:80]}")

    return "Ingestion complete: " + ", ".join(results)
$$;

GRANT USAGE ON PROCEDURE app.run_ingestion_pipeline() TO APPLICATION ROLE app_admin;
