RAW_SQL RAW_SQL -- â”€â”€ UDF: LOOP SUMMARY TEXT BUILDER â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
                'Subscription/usage-based â€” inherently recurring', NULL)
        ))
    END
$$