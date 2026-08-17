RAW_SQL RAW_SQL -- â”€â”€ UDF: LOOP SIGNAL DETECTOR â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
$$