-- Snowflake Native App Setup Script

-- Create schema
CREATE SCHEMA IF NOT EXISTS app_schema;

-- Create sales data table
CREATE OR REPLACE TABLE app_schema.sales_data (
    order_id VARCHAR(50),
    customer_id VARCHAR(50),
    product_name VARCHAR(200),
    region VARCHAR(50),
    year INTEGER,
    month INTEGER,
    revenue DECIMAL(18,2),
    order_count INTEGER,
    order_date TIMESTAMP_NTZ
);

-- Create view for monthly aggregates
CREATE OR REPLACE VIEW app_schema.monthly_sales AS
SELECT 
    year,
    month,
    region,
    SUM(revenue) as total_revenue,
    SUM(order_count) as total_orders,
    COUNT(DISTINCT customer_id) as unique_customers
FROM app_schema.sales_data
GROUP BY year, month, region;

-- Create stored procedure for forecasting
CREATE OR REPLACE PROCEDURE app_schema.calculate_sales_forecast(
    forecast_year INTEGER,
    regions VARCHAR
)
RETURNS FLOAT
LANGUAGE SQL
AS
$
DECLARE
    avg_growth FLOAT;
    last_year_sales FLOAT;
    forecast FLOAT;
BEGIN
    -- Calculate average growth rate
    SELECT AVG((current_year.revenue - prior_year.revenue) / prior_year.revenue)
    INTO avg_growth
    FROM (
        SELECT year, SUM(revenue) as revenue
        FROM app_schema.sales_data
        WHERE year >= forecast_year - 3
        GROUP BY year
    ) current_year
    JOIN (
        SELECT year, SUM(revenue) as revenue
        FROM app_schema.sales_data
        WHERE year >= forecast_year - 4
        GROUP BY year
    ) prior_year
    ON current_year.year = prior_year.year + 1;
    
    -- Get last year's sales
    SELECT SUM(revenue)
    INTO last_year_sales
    FROM app_schema.sales_data
    WHERE year = forecast_year - 1
    AND region IN (SELECT value FROM TABLE(SPLIT_TO_TABLE(:regions, ',')));
    
    -- Calculate forecast
    forecast := last_year_sales * (1 + avg_growth);
    
    RETURN forecast;
END;
$;

-- Create UDF for revenue category
CREATE OR REPLACE FUNCTION app_schema.categorize_revenue(revenue FLOAT)
RETURNS VARCHAR
LANGUAGE SQL
AS
$
    CASE 
        WHEN revenue > 100000 THEN 'High'
        WHEN revenue > 50000 THEN 'Medium'
        ELSE 'Low'
    END
$;

-- Grant permissions
GRANT USAGE ON SCHEMA app_schema TO APPLICATION ROLE app_user;
GRANT SELECT ON ALL TABLES IN SCHEMA app_schema TO APPLICATION ROLE app_user;
GRANT SELECT ON ALL VIEWS IN SCHEMA app_schema TO APPLICATION ROLE app_user;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA app_schema TO APPLICATION ROLE app_user;
GRANT EXECUTE ON ALL PROCEDURES IN SCHEMA app_schema TO APPLICATION ROLE app_user;
