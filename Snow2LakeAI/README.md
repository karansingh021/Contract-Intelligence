# Snow2Lake AI

Databricks-native Snowflake application migration accelerator.

## What this build does

- Connects to Snowflake using the Snowflake Python connector.
- Lists and downloads application source files from a Snowflake stage using `LIST` + `GET`.
- Scans staged SQL/Python/configuration files.
- Uses deterministic scripts first for SQL/DDL and safe Snowpark patterns.
- Uses Databricks SQL `ai_query()` for complex AI-assisted code migration.
- Re-checks generated Python for Spark anti-patterns such as `collect()`, `toPandas()`, and SQL-in-loop.
- Generates a local Databricks Asset Bundle skeleton and migration review artifacts.
- Produces JSON/HTML migration reports.
- Provides a Streamlit front end for connection setup, stage scan, migration, and output browsing.

Databricks `ai_query()` is the AI interface used by this project. It invokes an existing Databricks model-serving endpoint from SQL and supports structured output; current Databricks documentation describes it as a general-purpose AI function. It requires the appropriate supported/serverless SQL environment and endpoint/model configuration. 

## Run

```bash
python -m venv .venv
.venv\\Scripts\\activate        # Windows
# source .venv/bin/activate       # Linux/macOS
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Stage flow

1. Enter Snowflake connection information.
2. Enter the stage reference, e.g. `@APP_PACKAGE_STAGE`.
3. Click **Test Snowflake**.
4. Click **Scan Stage** to run `LIST` and display the source inventory.
5. Enter Databricks SQL Warehouse details and AI model name.
6. Click **Test Databricks SQL**.
7. Click **Migrate Stage**.
8. Outputs are written to the selected local output directory.

## Security

Credentials are held in Streamlit session state only. They are not written into generated source files or reports. For production deployment, use secret management instead of typing tokens into the UI.

## AI model

Default model: `databricks-gpt-oss-20b`. Make it configurable because model availability depends on the workspace/region and current Databricks offerings.

## Output

```text
<output>/
  stage_inventory.json
  migration_report.json
  migration_report.html
  databricks_project/
    databricks.yml
    resources/jobs.yml
    sql/
    src/pyspark/
    app/
    review/
  source_snapshot/
```

The source snapshot is retained for auditability; generated target files are separated under `databricks_project/`.
