RAW_SQL RAW_SQL -- â”€â”€ UDF: REVIEW REASON BUILDER â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
            'Unlimited liability clause â€” legal review required', NULL),
        IFF(COALESCE(has_auto_renewal, FALSE) = TRUE,
            CONCAT('Auto-renewal clause present',
                IFF(COALESCE(termination_days,0) > 0,
                    CONCAT(' â€” requires ', termination_days::STRING, ' days notice'), '')), NULL),
        IFF(contract_id IS NULL, 'Missing: CONTRACT_ID', NULL),
        IFF(customer_name IS NULL, 'Missing: CUSTOMER_NAME', NULL),
        IFF(contract_start_date IS NULL, 'Missing: CONTRACT_START_DATE', NULL),
        IFF(contract_end_date IS NULL, 'Missing: CONTRACT_END_DATE', NULL),
        IFF(COALESCE(penalty_percent, 0) > 15,
            CONCAT('High penalty: ', penalty_percent::STRING, '%'), NULL),
        IFF(COALESCE(extraction_confidence, 1) < 0.5,
            'Low extraction confidence â€” manual review recommended', NULL),
        IFF(loop_detection_summary IS NOT NULL
            AND loop_detection_summary <> 'NO LOOP DETECTED',
            CONCAT('Loop: ', loop_detection_summary), NULL)
    )), '')
$$