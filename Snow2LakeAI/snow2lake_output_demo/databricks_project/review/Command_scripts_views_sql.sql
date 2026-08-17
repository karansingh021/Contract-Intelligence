RAW_SQL RAW_SQL CREATE OR REPLACE MATERIALIZED VIEW high_value_customers AS
SELECT customer_id, SUM(amount) AS lifetime_value
FROM sales
GROUP BY customer_id
HAVING SUM(amount) > 100000