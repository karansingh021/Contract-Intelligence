CREATE OR REPLACE VIEW sales_summary AS
SELECT
    customer_id,
    SUM(amount) AS total_amount,
    NVL(COUNT(*), 0) AS num_sales
FROM sales
GROUP BY customer_id;

CREATE OR REPLACE SECURE VIEW customer_secure_view AS
SELECT customer_id, customer_name, region
FROM customers
WHERE region = CURRENT_ROLE();

CREATE OR REPLACE MATERIALIZED VIEW high_value_customers AS
SELECT customer_id, SUM(amount) AS lifetime_value
FROM sales
GROUP BY customer_id
HAVING SUM(amount) > 100000;
