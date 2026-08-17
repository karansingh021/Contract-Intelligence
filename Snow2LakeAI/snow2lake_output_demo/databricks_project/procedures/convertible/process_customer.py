# Auto-converted deterministically: Snowpark DataFrame API -> PySpark DataFrame API.
# No driver-side row processing or unsupported patterns were detected in the source,
# so no AI-assisted rewrite was required.
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.functions import col

"""Snowflake Python Stored Procedure: process_customer.

Pure Snowpark DataFrame operations, no row-by-row processing. This is
the case that should be safe for deterministic Snowpark -> PySpark
API mapping, with no AI assistance required.
"""



def process_customer(spark: SparkSession) -> None:
    customers = spark.table("customers")
    sales = spark.table("sales")

    joined = customers.join(sales, customers["customer_id"] == sales["customer_id"])
    summary = (
        joined
        .filter(col("amount") > 0)
        .groupBy("region")
        .agg({"amount": "sum"})
    )

    summary.write.saveAsTable("region_summary")
