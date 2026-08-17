RAW_SQL RAW_SQL -- Leakage by industry (includes portfolio value and leakage % from original)
CREATE OR REPLACE VIEW gold.by_industry AS
SELECT
    cu.industry,
    COUNT(DISTINCT c.contract_id)                          AS contracts,
    COALESCE(SUM(c.annual_value_usd), 0)                   AS portfolio_usd,
    COALESCE(SUM(le.leakage_amount_usd), 0)                AS leakage_usd,
    ROUND(
        COALESCE(SUM(le.leakage_amount_usd), 0)
        / NULLIF(SUM(c.annual_value_usd), 0) * 100, 2
    )                                                      AS leakage_pct,
    COUNT(DISTINCT le.event_ref)                           AS events
FROM raw.consumer_master_contracts c
JOIN raw.consumer_customers_local cu ON cu.customer_id = c.customer_id
LEFT JOIN analytics.leakage_events le ON le.contract_id = c.contract_id
GROUP BY cu.industry