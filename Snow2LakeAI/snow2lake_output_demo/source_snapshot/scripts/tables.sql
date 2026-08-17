CREATE OR REPLACE TABLE customers (
    customer_id NUMBER,
    customer_name VARCHAR(200),
    region VARCHAR(50),
    signup_date TIMESTAMP_NTZ
);

CREATE OR REPLACE TABLE sales (
    sale_id NUMBER,
    customer_id NUMBER,
    amount NUMBER(12,2),
    sale_date TIMESTAMP_NTZ,
    metadata VARIANT
);

INSERT INTO sales (sale_id, customer_id, amount, sale_date)
VALUES (1, 100, 15000.00, CURRENT_TIMESTAMP());
