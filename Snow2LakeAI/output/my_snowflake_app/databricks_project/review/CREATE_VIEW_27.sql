RAW_SQL RAW_SQL -- Leakage by customer
CREATE OR REPLACE VIEW gold.by_customer AS
SELECT
    customer_name, industry, contract_id,
    COUNT(DISTINCT event_ref) AS events,
    SUM(leakage_amount_usd) AS total_leakage_usd,
    MAX(severity) AS worst_severity,
    LISTAGG(DISTINCT leakage_type, ' | ') WITHIN GROUP (ORDER BY leakage_type) AS leakage_types
FROM analytics.leakage_events
GROUP BY 1,2,3
ORDER BY total_leakage_usd DESC