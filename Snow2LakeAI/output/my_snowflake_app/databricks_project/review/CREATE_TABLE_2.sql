RAW_SQL RAW_SQL -- â”€â”€ Column Mappings table (flexible schema support) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
CREATE TABLE IF NOT EXISTS config.column_mappings (
    reference_name  VARCHAR(100),
    app_column      VARCHAR(100),
    consumer_column VARCHAR(100),
    updated_at      TIMESTAMP_TZ DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT pk_col_map PRIMARY KEY (reference_name, app_column)
)