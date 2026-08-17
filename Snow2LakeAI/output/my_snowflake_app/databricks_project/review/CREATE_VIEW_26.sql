RAW_SQL RAW_SQL -- Leakage by rule
CREATE OR REPLACE VIEW gold.by_rule AS
SELECT
    rule_id, rule_name, leakage_type, data_mode,
    COUNT(*)                       AS event_count,
    SUM(leakage_amount_usd)        AS total_usd,
    ROUND(AVG(leakage_amount_usd),2) AS avg_usd,
    MAX(leakage_amount_usd)        AS max_usd
FROM analytics.leakage_events
GROUP BY 1,2,3,4
ORDER BY total_usd DESC