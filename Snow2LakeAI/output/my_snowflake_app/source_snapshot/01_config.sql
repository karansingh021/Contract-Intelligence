-- Config schema: roles, settings, column mappings, mode switching, reference callbacks
-- Co-authored with CoCo

-- ════════════════════════════════════════════════════════════════
-- APPLICATION ROLES
-- ════════════════════════════════════════════════════════════════
CREATE APPLICATION ROLE IF NOT EXISTS app_user;
CREATE APPLICATION ROLE IF NOT EXISTS app_admin;

-- ════════════════════════════════════════════════════════════════
-- SCHEMA: CONFIG
-- ════════════════════════════════════════════════════════════════
CREATE OR ALTER VERSIONED SCHEMA config;
GRANT USAGE ON SCHEMA config TO APPLICATION ROLE app_user;
GRANT USAGE ON SCHEMA config TO APPLICATION ROLE app_admin;

-- ── Reference callback (required by manifest references) ─────────────────
CREATE OR REPLACE PROCEDURE config.register_reference(
    ref_name STRING, operation STRING, ref_or_alias STRING
)
RETURNS STRING
LANGUAGE SQL
AS
$$
BEGIN
    CASE (operation)
        WHEN 'ADD' THEN SELECT SYSTEM$SET_REFERENCE(:ref_name, :ref_or_alias);
        WHEN 'REMOVE' THEN SELECT SYSTEM$REMOVE_REFERENCE(:ref_name, :ref_or_alias);
        WHEN 'CLEAR' THEN SELECT SYSTEM$REMOVE_ALL_REFERENCES(:ref_name);
    END CASE;
    RETURN 'Reference ' || ref_name || ' ' || operation || ' OK';
END;
$$;
GRANT USAGE ON PROCEDURE config.register_reference(STRING,STRING,STRING) TO APPLICATION ROLE app_admin;

-- ── App settings table ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS config.app_settings (
    setting_key   VARCHAR(100) PRIMARY KEY,
    setting_value VARCHAR(4000),
    updated_at    TIMESTAMP_TZ DEFAULT CURRENT_TIMESTAMP()
);

INSERT INTO config.app_settings (setting_key, setting_value)
    SELECT 'DATA_MODE', 'DEMO'
    WHERE NOT EXISTS (
        SELECT 1 FROM config.app_settings WHERE setting_key = 'DATA_MODE'
    );

INSERT INTO config.app_settings (setting_key, setting_value)
    SELECT 'CONSUMER_STAGE', NULL
    WHERE NOT EXISTS (
        SELECT 1 FROM config.app_settings WHERE setting_key = 'CONSUMER_STAGE'
    );

GRANT SELECT ON TABLE config.app_settings TO APPLICATION ROLE app_user;
GRANT ALL ON TABLE config.app_settings TO APPLICATION ROLE app_admin;

-- ── Mode-switching procedures ─────────────────────────────────────────────
CREATE OR REPLACE PROCEDURE config.switch_to_demo()
RETURNS STRING LANGUAGE SQL AS
$$
BEGIN
    UPDATE config.app_settings SET setting_value='DEMO', updated_at=CURRENT_TIMESTAMP()
        WHERE setting_key='DATA_MODE';
    RETURN 'Switched to DEMO mode.';
END;
$$;

CREATE OR REPLACE PROCEDURE config.switch_to_consumer()
RETURNS STRING LANGUAGE SQL AS
$$
BEGIN
    UPDATE config.app_settings SET setting_value='CONSUMER', updated_at=CURRENT_TIMESTAMP()
        WHERE setting_key='DATA_MODE';
    RETURN 'Switched to CONSUMER mode — upload your data to get started.';
END;
$$;

GRANT USAGE ON PROCEDURE config.switch_to_demo() TO APPLICATION ROLE app_admin;
GRANT USAGE ON PROCEDURE config.switch_to_consumer() TO APPLICATION ROLE app_admin;

-- ── Data stage configuration ──────────────────────────────────────────────
-- Consumer grants READ/WRITE on their stage to the app, then registers it here.
-- Usage: CALL config.set_data_stage('MY_DB.MY_SCHEMA.MY_STAGE');
CREATE OR REPLACE PROCEDURE config.set_data_stage(stage_fqn STRING)
RETURNS STRING LANGUAGE SQL AS
$$
BEGIN
    MERGE INTO config.app_settings tgt
    USING (SELECT 'CONSUMER_STAGE' AS setting_key, TRIM(:stage_fqn) AS setting_value) src
    ON tgt.setting_key = src.setting_key
    WHEN MATCHED THEN UPDATE SET setting_value = src.setting_value, updated_at = CURRENT_TIMESTAMP()
    WHEN NOT MATCHED THEN INSERT (setting_key, setting_value) VALUES (src.setting_key, src.setting_value);
    RETURN 'Data stage set to: ' || TRIM(stage_fqn) || '. Ensure you have run: GRANT READ, WRITE ON STAGE ' || TRIM(stage_fqn) || ' TO APPLICATION CONTRACT_INTEL_APP;';
END;
$$;
GRANT USAGE ON PROCEDURE config.set_data_stage(STRING) TO APPLICATION ROLE app_admin;

-- ── Column Mappings table (flexible schema support) ────────────────────────
CREATE TABLE IF NOT EXISTS config.column_mappings (
    reference_name  VARCHAR(100),
    app_column      VARCHAR(100),
    consumer_column VARCHAR(100),
    updated_at      TIMESTAMP_TZ DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT pk_col_map PRIMARY KEY (reference_name, app_column)
);
GRANT SELECT ON TABLE config.column_mappings TO APPLICATION ROLE app_user;
GRANT ALL ON TABLE config.column_mappings TO APPLICATION ROLE app_admin;

-- ── Save column mapping procedure ─────────────────────────────────────────
CREATE OR REPLACE PROCEDURE config.set_column_mapping(
    p_reference STRING, p_app_column STRING, p_consumer_column STRING
)
RETURNS STRING LANGUAGE SQL AS
$$
BEGIN
    MERGE INTO config.column_mappings tgt
    USING (SELECT :p_reference AS reference_name, :p_app_column AS app_column, :p_consumer_column AS consumer_column) src
    ON tgt.reference_name = src.reference_name AND tgt.app_column = src.app_column
    WHEN MATCHED THEN UPDATE SET consumer_column = src.consumer_column, updated_at = CURRENT_TIMESTAMP()
    WHEN NOT MATCHED THEN INSERT (reference_name, app_column, consumer_column, updated_at)
        VALUES (src.reference_name, src.app_column, src.consumer_column, CURRENT_TIMESTAMP());
    RETURN 'Mapping saved: ' || p_reference || '.' || p_app_column || ' <- ' || p_consumer_column;
END;
$$;
GRANT USAGE ON PROCEDURE config.set_column_mapping(STRING, STRING, STRING) TO APPLICATION ROLE app_admin;
