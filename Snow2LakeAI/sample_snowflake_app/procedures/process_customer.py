"""Snowflake Python Stored Procedure: process_customer.

Pure Snowpark DataFrame operations, no row-by-row processing. This is
the case that should be safe for deterministic Snowpark -> PySpark
API mapping, with no AI assistance required.
"""

from snowflake.snowpark import Session
from snowflake.snowpark.functions import col


def process_customer(session: Session) -> None:
    customers = session.table("customers")
    sales = session.table("sales")

    joined = customers.join(sales, customers["customer_id"] == sales["customer_id"])
    summary = (
        joined
        .filter(col("amount") > 0)
        .group_by("region")
        .agg({"amount": "sum"})
    )

    summary.write.save_as_table("region_summary")
