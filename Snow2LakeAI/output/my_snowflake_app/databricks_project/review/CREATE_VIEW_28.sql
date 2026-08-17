RAW_SQL RAW_SQL -- â”€â”€ Compatibility views referenced by dashboard.py â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
CREATE OR REPLACE VIEW gold.leakage_register AS
    SELECT * FROM analytics.leakage_events