RAW_SQL RAW_SQL -- Portfolio-level KPI (mode-aware: uses DEMO contracts or CONSUMER contracts)
CREATE OR REPLACE VIEW gold.portfolio_kpi AS
SELECT
    COUNT(DISTINCT le.contract_id)                         AS total_contracts,
    COALESCE(SUM(le.leakage_amount_usd), 0)                AS total_leakage_usd,
    COUNT(DISTINCT le.event_ref)                           AS total_leakage_events,
    COUNT(CASE WHEN le.severity = 'CRITICAL' THEN 1 END)  AS critical_events,
    COUNT(CASE WHEN le.severity = 'HIGH' THEN 1 END)      AS high_events,
    COUNT(CASE WHEN le.severity = 'MEDIUM' THEN 1 END)    AS medium_events,
    COUNT(CASE WHEN le.severity = 'LOW' THEN 1 END)       AS low_events
FROM analytics.leakage_events le