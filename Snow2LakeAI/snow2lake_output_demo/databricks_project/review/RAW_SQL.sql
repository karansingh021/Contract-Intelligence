-- CDC Setup: Delta Change Data Feed (CDF)
ALTER TABLE source_table SET TBLPROPERTIES (delta.enableChangeDataFeed = true);