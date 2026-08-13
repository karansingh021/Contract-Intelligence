# Databricks notebook source
# ================================================================================================
# MODULE 05 — BUILD_MASTER_CONTRACTS + BUILD_CONTRACTS
# Ports: 01_PDF_EXTRACTION.sql STEP 11 (BUILD_MASTER_CONTRACTS) and STEP 12 (BUILD_CONTRACTS)
#
# One row per CONTRACT_ID: chunk-level extractions are deduplicated/aggregated using the same
# rules as the Snowflake procedure (MAX() for scalar fields, boolean-OR for flags, first
# non-empty loop summary, LISTAGG(DISTINCT ...) -> collect_set + array_join for text lists).
# ================================================================================================

# MAGIC %run ../00_setup/00_config

# COMMAND ----------

from pyspark.sql import functions as F

RAW = f"{CATALOG}.{RAW_SCHEMA}"

extractions = spark.table(f"{RAW}.contract_ai_extractions").filter(
    F.col("contract_id").isNotNull() & (F.trim(F.col("contract_id")) != "")
).withColumn("contract_id", F.trim(F.col("contract_id")))

if extractions.count() == 0:
    print("No CONTRACT_AI_EXTRACTIONS rows with a CONTRACT_ID yet — run module 04 first.")
else:
    grouped = extractions.groupBy("contract_id")

    # loop signal type names -> mirrors the LISTAGG(DISTINCT ...) in the Snowflake procedure
    signal_names = (F.when(F.col("has_repeated_clauses"),
        F.array_join(F.array_except(F.array(
            F.when(F.col("has_auto_renewal"), F.lit("auto_renewal")),
            F.when(F.col("renewal_flag") & ~F.col("has_auto_renewal"), F.lit("renewal_flag")),
            F.when(F.lower(F.coalesce(F.col("payment_terms"), F.lit(""))).rlike("monthly|quarterly|recurring"),
                   F.lit("recurring_payment")),
        ), F.array(F.lit(None).cast("string"))), ",")))

    master = grouped.agg(
        F.max("customer_id").alias("customer_id"),
        F.max("customer_name").alias("customer_name"),
        F.max("vendor_name").alias("vendor_name"),
        F.max("industry").alias("industry"),
        F.max("contract_type").alias("contract_type"),
        F.max("contract_class").alias("contract_class"),
        F.max("status").alias("status"),
        F.max("contract_start_date").alias("contract_start_date"),
        F.max("contract_end_date").alias("contract_end_date"),
        F.max("auto_renewal_date").alias("auto_renewal_date"),
        F.max("termination_notice_days").alias("termination_notice_days"),
        F.max("effective_month").alias("effective_month"),
        F.max("contract_duration_days").alias("contract_duration_days"),
        F.max("duration_source").alias("duration_source"),
        F.max("annual_value_usd").alias("annual_value_usd"),
        F.max("total_contract_value_usd").alias("total_contract_value_usd"),
        F.max("tcv_estimation_method").alias("tcv_estimation_method"),
        F.max("contract_currency").alias("contract_currency"),
        F.max("unit_rate_usd").alias("unit_rate_usd"),
        F.max("contracted_units").alias("contracted_units"),
        F.max("overage_rate_usd").alias("overage_rate_usd"),
        F.max("payment_terms").alias("payment_terms"),
        F.max("sla_hours").alias("sla_hours"),
        F.max("penalty_percent").alias("penalty_percent"),
        F.max("bonus_percent").alias("bonus_percent"),
        F.max("bonus_threshold_hrs").alias("bonus_threshold_hrs"),
        F.max("delivery_sla_percent").alias("delivery_sla_percent"),
        F.max("defect_sla_pct").alias("defect_sla_pct"),
        F.max("governing_law").alias("governing_law"),

        F.max(F.col("has_auto_renewal").cast("int")).cast("boolean").alias("has_auto_renewal"),
        F.max(F.col("has_unlimited_liability").cast("int")).cast("boolean").alias("has_unlimited_liability"),
        F.max(F.col("has_indemnification").cast("int")).cast("boolean").alias("has_indemnification"),
        F.max(F.col("has_termination_clause").cast("int")).cast("boolean").alias("has_termination_clause"),
        F.max(F.col("has_confidentiality_clause").cast("int")).cast("boolean").alias("has_confidentiality_clause"),
        F.max(F.col("has_governing_law").cast("int")).cast("boolean").alias("has_governing_law"),
        F.max(F.col("has_payment_terms").cast("int")).cast("boolean").alias("has_payment_terms"),
        F.max(F.col("has_sla_terms").cast("int")).cast("boolean").alias("has_sla_terms"),
        F.max(F.col("renewal_flag").cast("int")).cast("boolean").alias("renewal_flag"),

        F.max(F.when(F.col("risk_level") == "HIGH", 2).when(F.col("risk_level") == "MEDIUM", 1).otherwise(0))
         .alias("_risk_rank"),
        F.max("contract_summary").alias("contract_summary"),

        F.max(F.col("needs_human_review").cast("int")).cast("boolean").alias("needs_human_review"),
        F.array_join(F.array_distinct(F.collect_list(
            F.when((F.col("review_reason").isNotNull()) & (F.col("review_reason") != ""), F.col("review_reason")))),
            "; ").alias("review_reason"),
        F.max(F.when(F.col("review_priority") == "HIGH", 3).when(F.col("review_priority") == "MEDIUM", 2)
              .when(F.col("needs_human_review"), 1).otherwise(0)).alias("_review_rank"),
        F.max("review_category").alias("review_category"),

        F.max("extraction_confidence").alias("extraction_confidence"),
        F.max("ocr_quality_score").alias("ocr_quality_score"),
        F.max("data_completeness_score").alias("data_completeness_score"),

        F.max(F.col("missing_critical_fields").cast("int")).cast("boolean").alias("missing_critical_fields"),
        F.max(F.col("date_conflict_flag").cast("int")).cast("boolean").alias("date_conflict_flag"),
        F.max(F.col("financial_anomaly_flag").cast("int")).cast("boolean").alias("financial_anomaly_flag"),
        F.max(F.col("ocr_corruption_flag").cast("int")).cast("boolean").alias("ocr_corruption_flag"),
        F.max(F.col("duplicate_contract_flag").cast("int")).cast("boolean").alias("duplicate_contract_flag"),

        F.max(F.col("has_repeated_clauses").cast("int")).cast("boolean").alias("has_repeated_clauses"),
        F.max(F.when((F.col("loop_detection_summary") != "NO LOOP DETECTED") & (F.col("loop_detection_summary") != ""),
                      F.col("loop_detection_summary"))).alias("_first_real_loop_summary"),
        F.array_join(F.array_distinct(F.collect_list(signal_names)), "; ").alias("loop_signals_summary"),
        F.max("repeated_clause_count").alias("repeated_clause_count"),

        F.max("document_page_count").alias("document_page_count"),
        F.max("file_name").alias("source_file"),
        F.max("extracted_by_model").alias("extracted_by_model"),
        F.max("ocr_engine_version").alias("ocr_engine_version"),
        F.max("pipeline_run_id").alias("pipeline_run_id"),
    )

    master = (master
        .withColumn("risk_level", F.when(F.col("_risk_rank") == 2, "HIGH")
                                    .when(F.col("_risk_rank") == 1, "MEDIUM").otherwise("LOW"))
        .withColumn("review_priority", F.when(F.col("_review_rank") == 3, "HIGH")
                                         .when(F.col("_review_rank") == 2, "MEDIUM")
                                         .when(F.col("_review_rank") == 1, "LOW").otherwise(F.lit(None)))
        .withColumn("loop_detection_summary", F.coalesce(F.col("_first_real_loop_summary"), F.lit("NO LOOP DETECTED")))
        .withColumn("page_range",
            F.when(F.col("document_page_count").isNull(), F.lit(None))
             .when(F.col("document_page_count") == 1, F.lit("Page 1 of 1"))
             .otherwise(F.concat(F.lit("Pages 1-"), F.col("document_page_count").cast("string"),
                                  F.lit(" of "), F.col("document_page_count").cast("string"))))
        .withColumn("load_timestamp", F.current_timestamp())
        .drop("_risk_rank", "_review_rank", "_first_real_loop_summary"))

    master.write.mode("overwrite").saveAsTable(f"{RAW}.master_contracts")
    print(f"MASTER_CONTRACTS written: {master.count()} distinct contracts")

    # ---------------------------------------------------------------------------------------
    # BUILD_CONTRACTS — final normalized table consumed by the rule engine (module 06)
    # ---------------------------------------------------------------------------------------
    contracts = (spark.table(f"{RAW}.master_contracts")
        .filter(F.col("contract_id").isNotNull() & (F.trim(F.col("contract_id")) != ""))
        .select(
            F.col("contract_id"), F.col("customer_id"), F.col("customer_name"), F.col("industry"),
            F.col("contract_type"), F.col("contract_class"),
            F.col("contract_start_date").alias("contract_start"),
            F.col("contract_end_date").alias("contract_end"),
            F.col("contract_duration_days"), F.col("annual_value_usd"), F.col("total_contract_value_usd"),
            F.coalesce(F.col("status"), F.lit("ACTIVE")).alias("status"),
            F.col("sla_hours"), F.col("penalty_percent").alias("penalty_pct"),
            F.col("bonus_percent").alias("bonus_pct"), F.col("bonus_threshold_hrs"),
            F.col("unit_rate_usd"), F.col("contracted_units"), F.col("overage_rate_usd"),
            F.col("delivery_sla_percent").alias("delivery_sla_pct"), F.col("defect_sla_pct"),
            F.col("document_page_count"), F.col("page_range"), F.col("loop_detection_summary"),
            F.current_timestamp().alias("load_timestamp"),
            F.lit("MASTER_CONTRACTS_PIPELINE").alias("record_source"),
        )
        # CONTRACT_START / CONTRACT_END are NOT NULL in the target schema
        .filter(F.col("contract_start").isNotNull() & F.col("contract_end").isNotNull()
                & F.col("annual_value_usd").isNotNull()))

    contracts.write.mode("overwrite").saveAsTable(f"{RAW}.contracts")
    print(f"CONTRACTS written: {contracts.count()} rows "
          f"(rows dropped for missing start/end/ACV are visible only in MASTER_CONTRACTS)")
