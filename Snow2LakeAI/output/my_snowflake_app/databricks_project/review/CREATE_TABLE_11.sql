RAW_SQL RAW_SQL -- â”€â”€ Consumer CRM staging table â”€â”€
CREATE TABLE IF NOT EXISTS raw.consumer_customers_local (
    CUSTOMER_ID         VARCHAR(50)    NOT NULL,
    CUSTOMER_NAME       VARCHAR(200)   NOT NULL,
    INDUSTRY            VARCHAR(50),
    SEGMENT             VARCHAR(30),
    REGION              VARCHAR(50),
    COUNTRY             VARCHAR(50)    DEFAULT 'US',
    ACCOUNT_MANAGER     VARCHAR(100),
    ARR_USD             NUMBER(18,2),
    RISK_SCORE          NUMBER(4,1),
    SF_ACCOUNT_ID       VARCHAR(20),
    LOAD_TIMESTAMP      TIMESTAMP_TZ   DEFAULT CURRENT_TIMESTAMP(),
    RECORD_SOURCE       VARCHAR(100)   DEFAULT 'CRM_IMPORT'
)