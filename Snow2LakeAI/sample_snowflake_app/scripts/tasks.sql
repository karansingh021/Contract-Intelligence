CREATE OR REPLACE STAGE sales_stage;

CREATE OR REPLACE STREAM sales_stream ON TABLE sales;

CREATE OR REPLACE TASK nightly_sales_rollup
    SCHEDULE = 'USING CRON 0 2 * * * UTC'
AS
    CALL process_sales();
