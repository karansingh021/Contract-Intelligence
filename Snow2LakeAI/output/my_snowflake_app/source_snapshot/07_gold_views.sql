-- Gold views for dashboard KPIs and Streamlit object registration
-- Co-authored with CoCo

CREATE SCHEMA IF NOT EXISTS gold;
GRANT USAGE ON SCHEMA gold TO APPLICATION ROLE app_user;
GRANT USAGE ON SCHEMA gold TO APPLICATION ROLE app_admin;

-- Portfolio-level KPI (mode-aware: uses DEMO contracts or CONSUMER contracts)
CREATE OR REPLACE VIEW gold.portfolio_kpi AS
SELECT
    COUNT(DISTINCT le.contract_id)                         AS total_contracts,
    COALESCE(SUM(le.leakage_amount_usd), 0)                AS total_leakage_usd,
    COUNT(DISTINCT le.event_ref)                           AS total_leakage_events,
    COUNT(CASE WHEN le.severity = 'CRITICAL' THEN 1 END)  AS critical_events,
    COUNT(CASE WHEN le.severity = 'HIGH' THEN 1 END)      AS high_events,
    COUNT(CASE WHEN le.severity = 'MEDIUM' THEN 1 END)    AS medium_events,
    COUNT(CASE WHEN le.severity = 'LOW' THEN 1 END)       AS low_events
FROM analytics.leakage_events le;

-- Leakage by industry (includes portfolio value and leakage % from original)
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
GROUP BY cu.industry;

-- Leakage by rule
CREATE OR REPLACE VIEW gold.by_rule AS
SELECT
    rule_id, rule_name, leakage_type, data_mode,
    COUNT(*)                       AS event_count,
    SUM(leakage_amount_usd)        AS total_usd,
    ROUND(AVG(leakage_amount_usd),2) AS avg_usd,
    MAX(leakage_amount_usd)        AS max_usd
FROM analytics.leakage_events
GROUP BY 1,2,3,4
ORDER BY total_usd DESC;

-- Leakage by customer
CREATE OR REPLACE VIEW gold.by_customer AS
SELECT
    customer_name, industry, contract_id,
    COUNT(DISTINCT event_ref) AS events,
    SUM(leakage_amount_usd) AS total_leakage_usd,
    MAX(severity) AS worst_severity,
    LISTAGG(DISTINCT leakage_type, ' | ') WITHIN GROUP (ORDER BY leakage_type) AS leakage_types
FROM analytics.leakage_events
GROUP BY 1,2,3
ORDER BY total_leakage_usd DESC;

GRANT SELECT ON ALL VIEWS IN SCHEMA gold TO APPLICATION ROLE app_user;
GRANT SELECT ON ALL VIEWS IN SCHEMA gold TO APPLICATION ROLE app_admin;

-- ── Compatibility views referenced by dashboard.py ────────────────────────
CREATE OR REPLACE VIEW gold.leakage_register AS
    SELECT * FROM analytics.leakage_events;

CREATE OR REPLACE VIEW gold.alerts AS
    SELECT * FROM analytics.alert_log;

CREATE OR REPLACE VIEW gold.credit_notes AS
    SELECT * FROM analytics.credit_notes;

GRANT SELECT ON VIEW gold.leakage_register TO APPLICATION ROLE app_user;
GRANT SELECT ON VIEW gold.alerts TO APPLICATION ROLE app_user;
GRANT SELECT ON VIEW gold.credit_notes TO APPLICATION ROLE app_user;

-- ── Load demo results on install (from SHARED_DATA pre-computed results) ──────
CREATE OR REPLACE PROCEDURE app.load_demo_results()
RETURNS STRING LANGUAGE SQL AS
$$
BEGIN
    LET current_mode STRING;
    SELECT setting_value INTO :current_mode FROM config.app_settings WHERE setting_key='DATA_MODE';
    IF (current_mode = 'DEMO') THEN
        BEGIN
            -- Load pre-computed demo results from shared data
            DELETE FROM analytics.leakage_events WHERE data_mode = 'DEMO';
            INSERT INTO analytics.leakage_events
                SELECT * FROM SHARED_DATA.DEMO_LEAKAGE_EVENTS;

            DELETE FROM analytics.alert_log WHERE leakage_id IN
                (SELECT leakage_id FROM analytics.leakage_events WHERE data_mode = 'DEMO');
            INSERT INTO analytics.alert_log
                SELECT * FROM SHARED_DATA.DEMO_ALERT_LOG;

            DELETE FROM analytics.credit_notes WHERE leakage_id IN
                (SELECT leakage_id FROM analytics.leakage_events WHERE data_mode = 'DEMO');
            INSERT INTO analytics.credit_notes
                SELECT * FROM SHARED_DATA.DEMO_CREDIT_NOTES;

            RETURN 'Demo results loaded: ' ||
                (SELECT COUNT(*) FROM analytics.leakage_events WHERE data_mode = 'DEMO') || ' events.';
        EXCEPTION WHEN OTHER THEN
            -- Fallback: run rule engine against demo views
            BEGIN
                CALL app.run_leakage_detection();
            EXCEPTION WHEN OTHER THEN
                RETURN 'Demo data not available — use Consumer mode.';
            END;
        END;
    END IF;
    RETURN 'Demo results loaded.';
END;
$$;
GRANT USAGE ON PROCEDURE app.load_demo_results() TO APPLICATION ROLE app_admin;

BEGIN
    CALL app.load_demo_results();
EXCEPTION WHEN OTHER THEN NULL;
END;

-- ── Streamlit registration ────────────────────────────────────────────────
CREATE OR REPLACE STREAMLIT app.revenue_leakage_dashboard
    FROM '/streamlit'
    MAIN_FILE = '/streamlit_app.py';

GRANT USAGE ON STREAMLIT app.revenue_leakage_dashboard TO APPLICATION ROLE app_user;
GRANT USAGE ON STREAMLIT app.revenue_leakage_dashboard TO APPLICATION ROLE app_admin;
