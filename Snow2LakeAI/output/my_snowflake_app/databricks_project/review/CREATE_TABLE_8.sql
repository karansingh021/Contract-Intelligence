RAW_SQL RAW_SQL -- â”€â”€ Consumer PDF pipeline tables â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
CREATE TABLE IF NOT EXISTS raw.consumer_raw_pdfs (
    FILE_NAME                      STRING,
    FILE_SIZE                      NUMBER,
    LAST_MODIFIED                  TIMESTAMP_TZ,
    FILE_URL                       STRING,
    OCR_TEXT                       STRING,
    PARSED_JSON                    VARIANT,
    DOCUMENT_PAGE_COUNT            NUMBER,
    DOCUMENT_PAGE_COUNT_ESTIMATED  NUMBER,
    DOCUMENT_PAGE_COUNT_FINAL      NUMBER,
    TEXT_CHAR_COUNT                NUMBER,
    TEXT_DENSITY_SCORE             FLOAT,
    IS_LIKELY_SCANNED              BOOLEAN,
    OCR_ENGINE_VERSION             STRING,
    OCR_STATUS                     STRING,
    PIPELINE_RUN_ID                STRING,
    INGESTION_TIMESTAMP            TIMESTAMP_TZ DEFAULT CURRENT_TIMESTAMP()
)