# Agentic pipeline skipped: Databricks AI not configured.
# Configure Databricks SQL connection to enable AI-assisted migration.
# Original source:
# """Snowflake Python Stored Procedure: process_sales.
# 
# Deliberately contains the anti-pattern called out in the Snow2Lake spec:
# collect() followed by a driver-side row loop instead of a set-based
# DataFrame filter. This is here to exercise the AI-assisted migration
# path and the performance-risk detector.
# """
# 
# from snowflake.snowpark import Session
# 
# 
# def process_sales(session: Session) -> str:
#     df = session.table("sales")
#     rows = df.collect()
# 
#     flagged = []
#     for row in rows:
#         if row["AMOUNT"] > 10000:
#             flagged.append(row["SALE_ID"])
#             session.sql(f"UPDATE sales SET metadata = 'high_value' WHERE sale_id = {row['SALE_ID']}").collect()
# 
#     return f"Flagged {len(flagged)} high-value sales"