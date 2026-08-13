# Databricks notebook source
# ================================================================================================
# MODULE 04 — LLM CONTRACT EXTRACTION + SQL QUALITY PASS
# Ports: 01_PDF_EXTRACTION.sql STEP 10 (EXTRACT_CONTRACT_CHUNKS_AI) — Pass 1 (LLM), Pass 2
# (SQL quality computation), Pass 3 (loop signals / review reason) — and the UDFs from
# STEP 4-7 (DETECT_CONTRACT_CLASS, DETECT_LOOP_SIGNALS, BUILD_LOOP_SUMMARY, BUILD_REVIEW_REASON).
#
# LLM CALL: Snowflake used SNOWFLAKE.CORTEX.COMPLETE('llama3.1-70b', prompt). On Databricks we
# use the SQL built-in `ai_query()` against a Foundation Model API serving endpoint (set via
# the `llm_endpoint` widget in 00_config, default: databricks-meta-llama-3-3-70b-instruct).
# The prompt text is IDENTICAL to the original (all 7 root-cause fixes preserved verbatim).
# ================================================================================================

# MAGIC %run ../00_setup/00_config

# COMMAND ----------

import json
from pyspark.sql import functions as F
from pyspark.sql.types import *

RAW = f"{CATALOG}.{RAW_SCHEMA}"

EXTRACTION_PROMPT = """You are an enterprise contract intelligence AI. You process ANY type of contract.

STRICT OUTPUT RULES:
1. Return ONLY valid raw JSON — no markdown, no preamble, no comments.
2. Booleans: exactly true or false (lowercase, never quoted).
3. Numbers: digits only — no $ % , symbols.
4. Dates: YYYY-MM-DD format or empty string "".
5. Output exactly ONE JSON object.

=== CONTRACT TYPE RECOGNITION ===
This system processes: Insurance, Telecom, SaaS, Vendor, Procurement,
Healthcare, Financial Services, NDA, Employment, Lease, Government, Manufacturing.
Adjust your field extraction based on the contract type you detect.
Not all fields apply to all types — leave inapplicable fields blank ("").

=== FIELD EXTRACTION GUIDE ===
CONTRACT_ID: codes like CON-XXXX, MSA-XXXX, Agreement No., Reference No., Policy No.
CUSTOMER_ID: Customer ID, Client ID, Account No., Subscriber ID. LEAVE "" if absent.
CUSTOMER_NAME: full legal name of buyer / client / insured / lessee.
VENDOR_NAME: full legal name of provider / insurer / lessor / seller.
INDUSTRY: Healthcare | Telecom | Manufacturing | SaaS | Financial Services | Other.
CONTRACT_TYPE: exact type stated in document header.

=== DATE & DURATION (ALWAYS POPULATE) ===
contract_start_date: "effective as of", "commences on", "effective date".
contract_end_date:   "expires on", "valid through", "termination date", "initial term ends".
contract_duration_days: COMPUTE using (end_date - start_date) in days.
  If both dates visible: calculate and return the number. Example: 2024-09-01 to 2025-09-28 = 392.
  If only one date: leave "".

=== FINANCIAL VALUES (ALWAYS POPULATE) ===
annual_value_usd: annual contract value, annual recurring revenue, yearly premium.
  For insurance: annual premium. For SaaS: ARR. For telecom: annual service fee.
total_contract_value_usd: total value over full contract term.
  If not explicit: ESTIMATE = annual_value_usd x (contract_duration_days / 365).
  Example: ACV=1200000, duration=730 days -> TCV = 1200000 x 2 = 2400000.
  Always return a number if annual_value_usd and dates are both available.

=== LOOP / RENEWAL DETECTION (REQUIRED) ===
has_repeated_clauses: Set TRUE if you detect ANY of:
  - "automatically renews" / "auto-renewal" / "evergreen"
  - "renews unless terminated" / "renewal unless notice given"
  - "subject to quarterly review" / "annual review cycle"
  - "recurring monthly obligation" / "rolling contract period"
  - Duplicate clause paragraphs (same text appearing more than once)
  - Circular references (Clause X references Clause Y which references X)
  - Repeated SHALL/MUST obligations identical in substance

loop_detection_summary: Describe what you found. Examples:
  "Auto-renewal clause present -- renews annually unless 60-day notice given"
  "Recurring payment obligation: monthly invoicing throughout term"
  "Section 4.2 duplicated verbatim in Section 8.1"
  Leave "NO LOOP DETECTED" if has_repeated_clauses = false.

repeated_clause_count: Count distinct loop/repeat instances found.
  Examples: 1 auto-renewal = 1; 1 auto-renewal + 1 duplicate clause = 2.
  Return 0 if has_repeated_clauses = false.

=== SCORING RUBRICS (REQUIRED -- NEVER BLANK) ===
extraction_confidence (0.0-1.0): Start 1.0. Deduct -0.15 per missing critical field.
ocr_quality_score (0.0-1.0): 1.0=clear, 0.7=minor issues, 0.4=heavy errors, 0.0=unreadable.
data_completeness_score (0.0-1.0): non-empty critical fields / 6.
risk_level: HIGH if ACV>10M or unlimited_liability. MEDIUM if ACV 1M-10M. LOW otherwise.
needs_human_review: true if risk=HIGH, date conflict, financial anomaly, OCR<0.5, or loops.
review_reason: semicolon-separated list of all reasons. Never blank when needs_human_review=true.
review_priority: HIGH/MEDIUM/LOW matching risk_level. "" when no review needed.
review_category: LEGAL/FINANCE/SLA/OCR -- most critical category.
contract_summary: REQUIRED 2-4 sentences: parties, value, term, key obligations.

=== JSON SCHEMA ===
{"contract_id":"","customer_id":"","customer_name":"","vendor_name":"","contract_type":"","industry":"","status":"","contract_start_date":"","contract_end_date":"","auto_renewal_date":"","termination_notice_days":"","contract_duration_days":"","annual_value_usd":"","total_contract_value_usd":"","contract_currency":"","unit_rate_usd":"","contracted_units":"","overage_rate_usd":"","payment_terms":"","sla_hours":"","penalty_percent":"","bonus_percent":"","bonus_threshold_hrs":"","delivery_sla_percent":"","defect_sla_pct":"","governing_law":"","has_auto_renewal":false,"has_unlimited_liability":false,"has_indemnification":false,"has_termination_clause":false,"has_confidentiality_clause":false,"has_governing_law":false,"has_payment_terms":false,"has_sla_terms":false,"renewal_flag":false,"risk_level":"","contract_summary":"","needs_human_review":false,"review_reason":"","review_priority":"","review_category":"","extraction_confidence":"","ocr_quality_score":"","data_completeness_score":"","missing_critical_fields":false,"date_conflict_flag":false,"financial_anomaly_flag":false,"ocr_corruption_flag":false,"duplicate_contract_flag":false,"has_repeated_clauses":false,"loop_detection_summary":"","repeated_clause_count":0}

CONTRACT TEXT:
"""

# ------------------------------------------------------------------------------------------
# PASS 1 — LLM EXTRACTION via ai_query()
# ------------------------------------------------------------------------------------------
spark.sql(f"TRUNCATE TABLE {RAW}.contract_ai_extractions" if spark.catalog.tableExists(f"{RAW}.contract_ai_extractions") else "SELECT 1")

chunks_view = f"{RAW}.contract_text_chunks"
llm_call_sql = f"""
CREATE OR REPLACE TEMP VIEW _chunk_llm_response AS
SELECT
    c.*,
    ai_query(
        '{LLM_ENDPOINT}',
        CONCAT('{EXTRACTION_PROMPT.replace("'", "''")}', c.chunk_text)
    ) AS raw_llm_response
FROM {chunks_view} c
WHERE c.ocr_status = 'SUCCESS'
"""
spark.sql(llm_call_sql)

llm_df = spark.table("_chunk_llm_response")

# ------------------------------------------------------------------------------------------
# Parse the LLM's JSON text response defensively (models occasionally wrap JSON in prose or
# markdown fences despite instructions -- strip those before parsing, same defensive posture
# as Snowflake's TRY_PARSE_JSON).
# ------------------------------------------------------------------------------------------
def _extract_json(raw):
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    candidate = text[start:end + 1]
    try:
        json.loads(candidate)
        return candidate
    except Exception:
        return None

extract_json_udf = F.udf(_extract_json, StringType())
llm_df = llm_df.withColumn("parsed_json_text", extract_json_udf(F.col("raw_llm_response")))

llm_schema = StructType([
    StructField("contract_id", StringType()), StructField("customer_id", StringType()),
    StructField("customer_name", StringType()), StructField("vendor_name", StringType()),
    StructField("contract_type", StringType()), StructField("industry", StringType()),
    StructField("status", StringType()),
    StructField("contract_start_date", StringType()), StructField("contract_end_date", StringType()),
    StructField("auto_renewal_date", StringType()), StructField("termination_notice_days", StringType()),
    StructField("contract_duration_days", StringType()),
    StructField("annual_value_usd", StringType()), StructField("total_contract_value_usd", StringType()),
    StructField("contract_currency", StringType()),
    StructField("unit_rate_usd", StringType()), StructField("contracted_units", StringType()),
    StructField("overage_rate_usd", StringType()), StructField("payment_terms", StringType()),
    StructField("sla_hours", StringType()), StructField("penalty_percent", StringType()),
    StructField("bonus_percent", StringType()), StructField("bonus_threshold_hrs", StringType()),
    StructField("delivery_sla_percent", StringType()), StructField("defect_sla_pct", StringType()),
    StructField("governing_law", StringType()),
    StructField("has_auto_renewal", BooleanType()), StructField("has_unlimited_liability", BooleanType()),
    StructField("has_indemnification", BooleanType()), StructField("has_termination_clause", BooleanType()),
    StructField("has_confidentiality_clause", BooleanType()), StructField("has_governing_law", BooleanType()),
    StructField("has_payment_terms", BooleanType()), StructField("has_sla_terms", BooleanType()),
    StructField("renewal_flag", BooleanType()),
    StructField("risk_level", StringType()), StructField("contract_summary", StringType()),
    StructField("needs_human_review", BooleanType()), StructField("review_reason", StringType()),
    StructField("review_priority", StringType()), StructField("review_category", StringType()),
    StructField("extraction_confidence", StringType()), StructField("ocr_quality_score", StringType()),
    StructField("data_completeness_score", StringType()),
    StructField("missing_critical_fields", BooleanType()), StructField("date_conflict_flag", BooleanType()),
    StructField("financial_anomaly_flag", BooleanType()), StructField("ocr_corruption_flag", BooleanType()),
    StructField("duplicate_contract_flag", BooleanType()),
    StructField("has_repeated_clauses", BooleanType()), StructField("loop_detection_summary", StringType()),
    StructField("repeated_clause_count", StringType()),
])

parsed = llm_df.withColumn("j", F.from_json(F.col("parsed_json_text"), llm_schema))


def _nz(colname):
    """NULLIF(TRIM(x), '') equivalent."""
    c = F.trim(F.col(f"j.{colname}"))
    return F.when((c == "") | c.isNull(), None).otherwise(c)


def _num(colname):
    return F.regexp_replace(F.col(f"j.{colname}"), ",", "").cast("decimal(18,4)")


extractions = (parsed
    .select(
        F.col("file_name"), F.col("chunk_id"), F.col("document_page_count"),
        F.length(F.col("chunk_text")).alias("chunk_character_count"),
        F.lit("VOLUME:/contracts/pdf/").alias("source_stage"),
        F.col("first_page"), F.col("last_page"), F.col("page_range"),
        F.current_timestamp().alias("load_timestamp"),
        F.col("parsed_json_text").alias("ai_response"),

        _nz("contract_id").alias("contract_id"),
        _nz("customer_id").alias("customer_id"),
        _nz("customer_name").alias("customer_name"),
        _nz("vendor_name").alias("vendor_name"),
        _nz("contract_type").alias("contract_type"),
        _nz("industry").alias("industry"),
        F.coalesce(_nz("status"), F.lit("ACTIVE")).alias("status"),

        F.to_date(F.col("j.contract_start_date")).alias("contract_start_date"),
        F.to_date(F.col("j.contract_end_date")).alias("contract_end_date"),
        F.to_date(F.col("j.auto_renewal_date")).alias("auto_renewal_date"),
        F.col("j.termination_notice_days").cast("int").alias("termination_notice_days"),
        F.date_trunc("MONTH", F.to_date(F.col("j.contract_start_date"))).cast("date").alias("effective_month"),
        F.col("j.contract_duration_days").cast("int").alias("contract_duration_days"),

        _num("annual_value_usd").cast("decimal(18,2)").alias("annual_value_usd"),
        _num("total_contract_value_usd").cast("decimal(18,2)").alias("total_contract_value_usd"),
        _nz("contract_currency").alias("contract_currency"),
        _num("unit_rate_usd").cast("decimal(18,4)").alias("unit_rate_usd"),
        F.col("j.contracted_units").cast("int").alias("contracted_units"),
        _num("overage_rate_usd").cast("decimal(18,4)").alias("overage_rate_usd"),
        _nz("payment_terms").alias("payment_terms"),
        F.col("j.sla_hours").cast("decimal(10,2)").alias("sla_hours"),
        F.col("j.penalty_percent").cast("decimal(10,2)").alias("penalty_percent"),
        F.col("j.bonus_percent").cast("decimal(10,2)").alias("bonus_percent"),
        F.col("j.bonus_threshold_hrs").cast("decimal(10,2)").alias("bonus_threshold_hrs"),
        F.col("j.delivery_sla_percent").cast("decimal(10,2)").alias("delivery_sla_percent"),
        F.col("j.defect_sla_pct").cast("decimal(10,2)").alias("defect_sla_pct"),
        _nz("governing_law").alias("governing_law"),

        F.coalesce(F.col("j.has_auto_renewal"), F.lit(False)).alias("has_auto_renewal"),
        F.coalesce(F.col("j.has_unlimited_liability"), F.lit(False)).alias("has_unlimited_liability"),
        F.coalesce(F.col("j.has_indemnification"), F.lit(False)).alias("has_indemnification"),
        F.coalesce(F.col("j.has_termination_clause"), F.lit(False)).alias("has_termination_clause"),
        F.coalesce(F.col("j.has_confidentiality_clause"), F.lit(False)).alias("has_confidentiality_clause"),
        F.coalesce(F.col("j.has_governing_law"), F.lit(False)).alias("has_governing_law"),
        F.coalesce(F.col("j.has_payment_terms"), F.lit(False)).alias("has_payment_terms"),
        F.coalesce(F.col("j.has_sla_terms"), F.lit(False)).alias("has_sla_terms"),
        F.coalesce(F.col("j.renewal_flag"), F.lit(False)).alias("renewal_flag"),

        _nz("risk_level").alias("risk_level"),
        _nz("contract_summary").alias("contract_summary"),
        F.coalesce(F.col("j.needs_human_review"), F.lit(False)).alias("needs_human_review"),
        _nz("review_reason").alias("review_reason"),
        _nz("review_priority").alias("review_priority"),
        _nz("review_category").alias("review_category"),

        F.col("j.extraction_confidence").cast("double").alias("extraction_confidence"),
        F.col("j.ocr_quality_score").cast("double").alias("ocr_quality_score"),
        F.col("j.data_completeness_score").cast("double").alias("data_completeness_score"),

        F.coalesce(F.col("j.missing_critical_fields"), F.lit(False)).alias("missing_critical_fields_llm"),
        F.coalesce(F.col("j.date_conflict_flag"), F.lit(False)).alias("date_conflict_flag_llm"),
        F.coalesce(F.col("j.financial_anomaly_flag"), F.lit(False)).alias("financial_anomaly_flag_llm"),
        F.coalesce(F.col("j.ocr_corruption_flag"), F.lit(False)).alias("ocr_corruption_flag_llm"),
        F.coalesce(F.col("j.duplicate_contract_flag"), F.lit(False)).alias("duplicate_contract_flag"),

        F.coalesce(F.col("j.has_repeated_clauses"), F.lit(False)).alias("has_repeated_clauses"),
        _nz("loop_detection_summary").alias("loop_detection_summary"),
        F.coalesce(F.col("j.repeated_clause_count").cast("int"), F.lit(0)).alias("repeated_clause_count"),

        F.lit(LLM_ENDPOINT).alias("extracted_by_model"),
        F.col("ocr_engine_version"),
        F.col("pipeline_run_id"),
        F.current_timestamp().alias("pipeline_execution_ts"),
        F.lit("PDF_CONTRACT_PIPELINE").alias("record_source"),
        F.substring(F.col("chunk_text"), 1, 1000).alias("raw_ocr_text_sample"),
        F.md5(F.col("chunk_text")).alias("chunk_hash"),
        F.when(F.col("parsed_json_text").isNull(), "FAILED")
         .when(_nz("contract_id").isNull(), "PARTIAL_SUCCESS")
         .otherwise("SUCCESS").alias("ai_processing_status"),
        F.when(F.col("parsed_json_text").isNull(), F.lit("Invalid JSON from LLM")).alias("error_message"),
    ))

print(f"PASS 1 (LLM extraction) complete: {extractions.count()} chunk-level extractions")

# ------------------------------------------------------------------------------------------
# PASS 2 — SQL QUALITY COMPUTATION (contract class, duration fallback, TCV fallback,
# quality/risk scoring, review priority/category) — same thresholds as the Snowflake UPDATE.
# ------------------------------------------------------------------------------------------

def detect_contract_class(contract_type, industry, text):
    ct = (contract_type or "").lower()
    ind = (industry or "").lower()
    tx = (text or "").lower()
    if any(k in ct for k in ("insurance", "policy")) or any(k in tx for k in ("premium", "policyholder", "insured")):
        return "Insurance"
    if any(k in ct for k in ("nda", "non-disclosure", "confidentiality")) or "confidential information" in tx:
        return "NDA"
    if any(k in ct for k in ("employment", "offer letter")) or any(k in tx for k in ("compensation package", "at-will employment")):
        return "Employment"
    if any(k in ct for k in ("government", "federal", "far clause")) or "federal acquisition" in tx:
        return "Government"
    if any(k in ct for k in ("lease", "rental")) or any(k in tx for k in ("lessor", "lessee")):
        return "Lease"
    if "healthcare" in ind or any(k in ct for k in ("managed care", "provider services", "payer")) or any(k in tx for k in ("hipaa", "clinical")):
        return "Healthcare"
    if "financial" in ind or any(k in ct for k in ("custody", "data license")) or any(k in tx for k in ("fiduciary", "custodian")):
        return "Financial"
    if "saas" in ind or any(k in ct for k in ("subscription", "enterprise license", "usage based")) or any(k in tx for k in ("software as a service", "seat license")):
        return "SaaS"
    if "telecom" in ind or any(k in ct for k in ("network sla", "managed services")) or any(k in tx for k in ("uptime", "bandwidth")):
        return "Telecom"
    if "manufacturing" in ind or any(k in ct for k in ("supply agreement", "oem agreement", "components")) or any(k in tx for k in ("defect rate", "bill of materials")):
        return "Manufacturing"
    if any(k in ct for k in ("vendor", "procurement", "purchase order")):
        return "Vendor"
    return "Other"


detect_contract_class_udf = F.udf(detect_contract_class, StringType())

quality_df = (extractions
    .withColumn("raw_pdf_density",
        F.lit(None).cast("double"))  # joined below
)

raw_pdf_density = spark.table(f"{RAW}.raw_contract_pdfs").select(
    F.col("file_name"), F.col("text_density_score"), F.col("text_char_count"), F.col("ocr_text"),
    F.col("is_likely_scanned"))

q = extractions.join(raw_pdf_density, on="file_name", how="left")

n_critical = (
    F.col("contract_id").isNotNull().cast("int") + F.col("customer_name").isNotNull().cast("int") +
    F.col("contract_type").isNotNull().cast("int") + F.col("contract_start_date").isNotNull().cast("int") +
    F.col("contract_end_date").isNotNull().cast("int") + F.col("annual_value_usd").isNotNull().cast("int")
)
duration_expr = F.datediff(F.col("contract_end_date"), F.col("contract_start_date"))

q = (q
    .withColumn("contract_class", detect_contract_class_udf(
        F.col("contract_type"), F.col("industry"), F.col("raw_ocr_text_sample")))

    .withColumn("contract_duration_days",
        F.when((F.col("contract_duration_days").isNotNull()) & (F.col("contract_duration_days") > 0),
               F.col("contract_duration_days"))
         .when(F.col("contract_start_date").isNotNull() & F.col("contract_end_date").isNotNull(),
               duration_expr)
         .when(F.col("effective_month").isNotNull() & F.col("contract_end_date").isNotNull(),
               F.datediff(F.col("contract_end_date"), F.col("effective_month")))
         .otherwise(F.lit(None).cast("int")))

    .withColumn("duration_source",
        F.when((F.col("contract_duration_days").isNotNull()) & (F.col("contract_duration_days") > 0)
               & F.col("contract_start_date").isNull(), F.lit("LLM"))
         .when(F.col("contract_start_date").isNotNull() & F.col("contract_end_date").isNotNull(), F.lit("SQL_DATEDIFF"))
         .when(F.col("effective_month").isNotNull() & F.col("contract_end_date").isNotNull(), F.lit("SQL_ESTIMATED"))
         .otherwise(F.lit("LLM")))

    .withColumn("total_contract_value_usd",
        F.when((F.col("total_contract_value_usd").isNotNull()) & (F.col("total_contract_value_usd") > 0),
               F.col("total_contract_value_usd"))
         .when((F.col("annual_value_usd").isNotNull()) & (F.col("annual_value_usd") > 0)
               & F.col("contract_start_date").isNotNull() & F.col("contract_end_date").isNotNull()
               & (duration_expr > 0),
               F.round(F.col("annual_value_usd") * (duration_expr / F.lit(365.0)), 2))
         .otherwise(F.lit(None).cast("decimal(18,2)")))

    .withColumn("tcv_estimation_method",
        F.when((F.col("total_contract_value_usd").isNotNull()) & (F.col("total_contract_value_usd") > 0), "EXPLICIT")
         .when(F.col("annual_value_usd").isNotNull() & F.col("contract_start_date").isNotNull()
               & F.col("contract_end_date").isNotNull(), "ACV_x_DURATION")
         .otherwise(F.lit(None).cast("string")))

    .withColumn("missing_critical_fields", n_critical < 6)
    .withColumn("date_conflict_flag",
        (F.col("contract_start_date").isNotNull() & F.col("contract_end_date").isNotNull()
         & (F.col("contract_end_date") <= F.col("contract_start_date")))
        | (F.col("contract_start_date").isNotNull() & F.col("contract_end_date").isNotNull()
           & (duration_expr > 3650)))
    .withColumn("financial_anomaly_flag",
        (F.col("annual_value_usd").isNotNull() & ((F.col("annual_value_usd") < 1000) | (F.col("annual_value_usd") > 10000000000)))
        | (F.col("annual_value_usd").isNotNull() & F.col("unit_rate_usd").isNotNull() & F.col("contracted_units").isNotNull()
           & (F.col("annual_value_usd") > 0)
           & ((F.abs((F.col("unit_rate_usd") * F.col("contracted_units") * 12) - F.col("annual_value_usd")) / F.col("annual_value_usd")) > 0.30)))
    .withColumn("ocr_corruption_flag", F.coalesce(F.col("text_density_score"), F.lit(0.0)) < 0.35)
    .withColumn("data_completeness_score", F.round(n_critical.cast("double") / 6.0, 3))
    .withColumn("ocr_quality_score",
        F.when(F.coalesce(F.col("ocr_quality_score"), F.lit(0.0)) > 0, F.col("ocr_quality_score"))
         .otherwise(F.least(
             F.coalesce(F.col("text_density_score"), F.lit(0.5)) * 0.4
             + F.when(F.col("is_likely_scanned"), 0.15).otherwise(0.30)
             + F.lit(0.15),
             F.lit(1.0))))
    .withColumn("extraction_confidence",
        F.round(
            F.coalesce(F.when(F.col("extraction_confidence") != 0, F.col("extraction_confidence")),
                       F.round(n_critical.cast("double") / 6.0, 3)) * 0.4
            + F.round(n_critical.cast("double") / 6.0, 3) * 0.4
            + F.coalesce(F.least(F.col("text_density_score"), F.lit(1.0)), F.lit(0.5)) * 0.2,
            3))
    .withColumn("risk_level",
        F.when((F.col("annual_value_usd") >= 10000000) | (F.col("has_unlimited_liability"))
               | ((~F.col("has_termination_clause")) & F.col("contract_type").isNotNull())
               | ((n_critical.cast("double") / 6.0) < 0.5) | (F.col("risk_level") == "HIGH"), "HIGH")
         .when(((F.col("annual_value_usd") >= 1000000) & (F.col("annual_value_usd") < 10000000))
               | (F.col("has_sla_terms") & F.col("sla_hours").isNull()) | (F.col("risk_level") == "MEDIUM"), "MEDIUM")
         .otherwise("LOW"))
    .withColumn("needs_human_review",
        (F.col("annual_value_usd") >= 10000000) | F.col("has_unlimited_liability")
        | F.col("contract_id").isNull() | F.col("customer_name").isNull()
        | F.col("contract_start_date").isNull() | F.col("contract_end_date").isNull()
        | F.col("annual_value_usd").isNull()
        | (F.col("contract_start_date").isNotNull() & F.col("contract_end_date").isNotNull()
           & (F.col("contract_end_date") <= F.col("contract_start_date")))
        | (F.col("contract_start_date").isNotNull() & F.col("contract_end_date").isNotNull() & (duration_expr > 3650))
        | (F.col("annual_value_usd").isNotNull() & ((F.col("annual_value_usd") < 1000) | (F.col("annual_value_usd") > 10000000000)))
        | (F.col("annual_value_usd").isNotNull() & F.col("unit_rate_usd").isNotNull() & F.col("contracted_units").isNotNull()
           & (F.col("annual_value_usd") > 0)
           & ((F.abs((F.col("unit_rate_usd") * F.col("contracted_units") * 12) - F.col("annual_value_usd")) / F.col("annual_value_usd")) > 0.30))
        | F.coalesce(F.col("has_auto_renewal"), F.lit(False))
        | F.coalesce(F.col("needs_human_review"), F.lit(False)))
    .withColumn("review_priority",
        F.when((F.col("annual_value_usd") >= 10000000) | F.col("has_unlimited_liability") | (F.col("review_priority") == "HIGH"), "HIGH")
         .when((F.col("annual_value_usd") >= 1000000) | F.col("contract_id").isNull() | F.col("customer_name").isNull()
               | F.col("contract_start_date").isNull() | (F.col("review_priority") == "MEDIUM"), "MEDIUM")
         .when(F.col("needs_human_review"), "LOW")
         .otherwise(F.col("review_priority")))
    .withColumn("review_category",
        F.when(F.col("has_unlimited_liability") | F.coalesce(F.col("has_repeated_clauses"), F.lit(False)), "LEGAL")
         .when((F.col("annual_value_usd") >= 10000000)
               | (F.col("annual_value_usd").isNotNull() & F.col("unit_rate_usd").isNotNull() & F.col("contracted_units").isNotNull()
                  & (F.col("annual_value_usd") > 0)
                  & ((F.abs((F.col("unit_rate_usd") * F.col("contracted_units") * 12) - F.col("annual_value_usd")) / F.col("annual_value_usd")) > 0.30)),
               "FINANCE")
         .when(F.col("contract_id").isNull() | F.col("customer_name").isNull() | F.col("contract_start_date").isNull(), "OCR")
         .when(F.col("has_sla_terms") & F.col("sla_hours").isNull(), "SLA")
         .otherwise(F.coalesce(F.col("review_category"), F.lit("OCR"))))
    .drop("text_density_score", "text_char_count", "ocr_text", "is_likely_scanned")
)

print(f"PASS 2 (SQL quality computation) complete: {q.count()} rows")

# ------------------------------------------------------------------------------------------
# PASS 3 — LOOP SIGNALS + LOOP SUMMARY + REVIEW REASON  (DETECT_LOOP_SIGNALS,
# BUILD_LOOP_SUMMARY, BUILD_REVIEW_REASON ported verbatim as Python UDFs)
# ------------------------------------------------------------------------------------------

def detect_loop_signals(has_auto_renewal, renewal_flag, has_sla_terms, payment_terms,
                         termination_days, duration_days, contract_end_date,
                         annual_value_usd, contract_type):
    pt = (payment_terms or "").lower()
    ct = (contract_type or "").lower()
    signals = {
        "auto_renewal": bool(has_auto_renewal),
        "evergreen_clause": bool(has_auto_renewal) and contract_end_date is None,
        "renewal_flag": bool(renewal_flag),
        "recurring_payment": any(k in pt for k in ("monthly", "quarterly", "annual", "recurring")),
        "periodic_sla_review": bool(has_sla_terms) and bool(has_auto_renewal),
        "rolling_period": (duration_days or 0) > 365 and bool(has_auto_renewal),
        "termination_notice_required": (termination_days or 0) > 0,
        "termination_notice_days": termination_days or 0,
        "high_value_renewal_risk": bool(has_auto_renewal) and (annual_value_usd or 0) >= 5000000,
        "subscription_loop": any(k in ct for k in ("subscription", "usage based")),
    }
    return json.dumps(signals)


def build_loop_summary(loop_signals_json, termination_days):
    if not loop_signals_json:
        return "NO LOOP DETECTED"
    s = json.loads(loop_signals_json)
    if not any([s.get("auto_renewal"), s.get("renewal_flag"), s.get("recurring_payment"), s.get("subscription_loop")]):
        return "NO LOOP DETECTED"
    parts = []
    if s.get("auto_renewal"):
        msg = "Auto-renewal clause detected — renews automatically unless terminated"
        if (termination_days or 0) > 0:
            msg += f" with {termination_days}-day written notice required"
        parts.append(msg)
    if s.get("evergreen_clause"):
        parts.append("Evergreen clause: no fixed end date — contract continues indefinitely")
    if s.get("renewal_flag") and not s.get("auto_renewal"):
        parts.append("Renewal flag set — contract eligible for renewal")
    if s.get("recurring_payment"):
        parts.append("Recurring payment obligation detected in payment terms")
    if s.get("periodic_sla_review"):
        parts.append("SLA terms subject to periodic review upon renewal")
    if s.get("rolling_period"):
        parts.append("Multi-year rolling contract period with auto-renewal")
    if s.get("high_value_renewal_risk"):
        parts.append("HIGH VALUE: auto-renewal on contract >= USD 5M — requires active opt-out")
    if s.get("subscription_loop"):
        parts.append("Subscription or usage-based agreement — inherently recurring by structure")
    return "; ".join(parts) if parts else "NO LOOP DETECTED"


def build_review_reason(annual_value_usd, has_unlimited_liability, has_auto_renewal, termination_days,
                         contract_id, customer_name, contract_type, contract_start_date, contract_end_date,
                         governing_law, has_governing_law, unit_rate_usd, contracted_units, penalty_percent,
                         ocr_quality_score, risk_level, loop_detection_summary):
    reasons = []
    acv = annual_value_usd or 0
    if acv >= 10000000:
        reasons.append(f"High-value contract: USD {annual_value_usd:,.0f}")
    elif 1000000 <= acv < 10000000:
        reasons.append("Significant-value contract (USD 1M-10M): requires finance review")
    if has_unlimited_liability:
        reasons.append("Unlimited liability clause detected — legal review required")
    if has_auto_renewal:
        if (termination_days or 0) > 0:
            reasons.append(f"Auto-renewal clause present — termination requires {termination_days} days notice")
        else:
            reasons.append("Auto-renewal clause present — no termination notice period specified")
    if contract_id is None:
        reasons.append("Missing: CONTRACT_ID")
    if customer_name is None:
        reasons.append("Missing: CUSTOMER_NAME")
    if contract_type is None:
        reasons.append("Missing: CONTRACT_TYPE")
    if contract_start_date is None:
        reasons.append("Missing: CONTRACT_START_DATE")
    if contract_end_date is None:
        reasons.append("Missing: CONTRACT_END_DATE")
    if contract_start_date and contract_end_date:
        days = (contract_end_date - contract_start_date).days
        if contract_end_date <= contract_start_date:
            reasons.append("Date conflict: end date is not after start date")
        elif days > 3650:
            reasons.append(f"Unusually long term: {days} days (>10 years)")
    if not has_governing_law or governing_law is None:
        reasons.append("Missing: governing law clause not identified")
    if annual_value_usd and unit_rate_usd and contracted_units and annual_value_usd > 0:
        variance = abs((float(unit_rate_usd) * contracted_units * 12) - float(annual_value_usd)) / float(annual_value_usd)
        if variance > 0.30:
            reasons.append("Financial anomaly: ACV vs unit_rate x units x 12 variance exceeds 30%")
    if penalty_percent and penalty_percent > 15:
        reasons.append(f"High penalty clause: {penalty_percent}% on SLA breach")
    if ocr_quality_score is not None and ocr_quality_score < 0.5:
        reasons.append(f"Low OCR quality score: {round(ocr_quality_score, 2)} — manual review of original PDF recommended")
    if loop_detection_summary and loop_detection_summary not in ("NO LOOP DETECTED", ""):
        reasons.append(f"Contract loop: {loop_detection_summary}")
    joined = "; ".join(reasons).strip()
    return joined if joined else None


detect_loop_signals_udf = F.udf(detect_loop_signals, StringType())
build_loop_summary_udf = F.udf(build_loop_summary, StringType())
build_review_reason_udf = F.udf(build_review_reason, StringType())

final = (q
    .withColumn("loop_signals", detect_loop_signals_udf(
        "has_auto_renewal", "renewal_flag", "has_sla_terms", "payment_terms",
        "termination_notice_days", "contract_duration_days", "contract_end_date",
        "annual_value_usd", "contract_type"))
    .withColumn("loop_detection_summary",
        F.when(F.col("loop_detection_summary").isNotNull() & (F.col("loop_detection_summary") != "")
               & (F.col("loop_detection_summary") != "NO LOOP DETECTED"),
               F.col("loop_detection_summary"))
         .otherwise(build_loop_summary_udf("loop_signals", "termination_notice_days")))
    .withColumn("repeated_clause_count",
        F.when(F.coalesce(F.col("repeated_clause_count"), F.lit(0)) > 0, F.col("repeated_clause_count"))
         .otherwise(
            F.coalesce(F.col("has_auto_renewal").cast("int"), F.lit(0))
            + (F.coalesce(F.col("renewal_flag"), F.lit(False)) & ~F.coalesce(F.col("has_auto_renewal"), F.lit(False))).cast("int")
            + (F.lower(F.coalesce(F.col("payment_terms"), F.lit(""))).rlike("monthly|quarterly|recurring")).cast("int")
            + (F.coalesce(F.col("has_sla_terms"), F.lit(False)) & F.coalesce(F.col("has_auto_renewal"), F.lit(False))).cast("int")
         ))
    .withColumn("has_repeated_clauses",
        F.coalesce(F.col("has_auto_renewal"), F.lit(False)) | F.coalesce(F.col("renewal_flag"), F.lit(False))
        | F.lower(F.coalesce(F.col("payment_terms"), F.lit(""))).rlike("monthly|quarterly|recurring")
        | F.coalesce(F.col("has_repeated_clauses"), F.lit(False)))
    .withColumn("review_reason", build_review_reason_udf(
        "annual_value_usd", "has_unlimited_liability", "has_auto_renewal", "termination_notice_days",
        "contract_id", "customer_name", "contract_type", "contract_start_date", "contract_end_date",
        "governing_law", "has_governing_law", "unit_rate_usd", "contracted_units", "penalty_percent",
        "ocr_quality_score", "risk_level", "loop_detection_summary"))
)

final.write.mode("overwrite").saveAsTable(f"{RAW}.contract_ai_extractions")
print(f"CONTRACT_AI_EXTRACTIONS written: {final.count()} rows")
