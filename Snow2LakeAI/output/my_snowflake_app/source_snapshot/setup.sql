-- Contract Intelligence Native App — Main Setup Orchestrator
-- Co-authored with CoCo
-- ============================================================================
-- Runs at install time AND on every app upgrade.
-- Delegates to sub-scripts for clean modular organization.
-- All sub-scripts are in the same /scripts/ directory on the stage.
-- ============================================================================

EXECUTE IMMEDIATE FROM '01_config.sql';
EXECUTE IMMEDIATE FROM '02_raw_tables.sql';
EXECUTE IMMEDIATE FROM '03_analytics.sql';
EXECUTE IMMEDIATE FROM '04_pdf_pipeline.sql';
EXECUTE IMMEDIATE FROM '05_ingestion.sql';
EXECUTE IMMEDIATE FROM '06_rule_engine.sql';
EXECUTE IMMEDIATE FROM '07_gold_views.sql';
