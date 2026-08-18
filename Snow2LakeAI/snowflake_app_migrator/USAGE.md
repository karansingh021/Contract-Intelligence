# Quick Start Guide - Snowflake App Migrator

## Installation

```bash
cd /Workspace/Users/<your-email>/Snow2LakeAI/snowflake_app_migrator
pip install pyyaml snowflake-connector-python databricks-sdk
```

## Basic Usage

### 1. Analyze a Local Snowflake App

```bash
python app_migrator_cli.py \
  --input /path/to/snowflake/app \
  --analyze-only \
  --report analysis.json
```

This will:
- ✅ Scan all Python and SQL files
- ✅ Detect Streamlit/API patterns
- ✅ Identify Snowpark usage
- ✅ Assess migration complexity
- ✅ Generate recommendations

### 2. Full Migration (Local Directory)

```bash
python app_migrator_cli.py \
  --input /path/to/snowflake/app \
  --output ./databricks_app
```

This will:
- ✅ Analyze the app
- ✅ Convert all source files
- ✅ Generate app.yaml and app.py
- ✅ Create Unity Catalog setup scripts
- ✅ Produce deployment README

### 3. Download from Snowflake Stage and Migrate

First, create a config file (copy from `config.example.json`):

```bash
cp config.example.json config.json
# Edit config.json with your Snowflake credentials
```

Then run:

```bash
python app_migrator_cli.py \
  --snowflake-stage @APP_PACKAGE_STAGE \
  --snowflake-config config.json \
  --output ./databricks_app
```

This will:
- ✅ Download app files from Snowflake stage
- ✅ Analyze and convert
- ✅ Generate Databricks App structure

## Python API

### Programmatic Usage

```python
from snowflake_app_migrator import SnowflakeAppAnalyzer, DatabricksAppConverter

# Analyze
analyzer = SnowflakeAppAnalyzer()
analysis = analyzer.analyze("/path/to/snowflake/app")

print(f"App: {analysis.app_name}")
print(f"Complexity: {analysis.migration_complexity}")
print(f"Has Streamlit: {analysis.has_streamlit}")

# Print detailed analysis
analyzer.print_summary()

# Convert
converter = DatabricksAppConverter()
db_app = converter.convert(analysis, output_dir="./databricks_app")

print(f"✅ Databricks App created: {db_app.app_path}")
```

### Custom Analysis

```python
from snowflake_app_migrator import SnowflakeAppAnalyzer

analyzer = SnowflakeAppAnalyzer()
analysis = analyzer.analyze("/path/to/app")

# Check specific patterns
if analysis.has_streamlit:
    print("🎯 Streamlit app detected")
    print(f"   Pages: {len(analysis.streamlit_pages)}")

if analysis.snowpark_usage:
    print("\n⚙️ Snowpark Features Used:")
    for feature, count in analysis.snowpark_usage.items():
        print(f"   {feature}: {count} times")

# Review migration complexity
print(f"\n📊 Migration Complexity: {analysis.migration_complexity.upper()}")

if analysis.warnings:
    print("\n⚠️ Warnings:")
    for warning in analysis.warnings:
        print(f"   • {warning}")
```

## Common Scenarios

### Scenario 1: Streamlit App with Snowpark

**Input**: Snowflake Native App with `streamlit_app.py` using Snowpark DataFrames

**Command**:
```bash
python app_migrator_cli.py \
  --input ./my_streamlit_app \
  --output ./databricks_streamlit_app
```

**Output**:
- `app.yaml` configured for Streamlit runtime
- `src/streamlit_app.py` with:
  - `snowflake.connector` → `databricks.sql`
  - `session.table()` → `spark.table()`
  - Updated connection patterns
- `requirements.txt` with `streamlit` and `databricks-sql-connector`

### Scenario 2: API App with SQL Procedures

**Input**: Flask API with stored procedures in `setup.sql`

**Command**:
```bash
python app_migrator_cli.py \
  --input ./my_api_app \
  --output ./databricks_api_app
```

**Output**:
- `app.yaml` configured for Flask
- `app.py` with Flask routes
- `databricks/*.sql` files for review
- Notes on converting stored procedures to Python UDFs

### Scenario 3: Data Analytics Dashboard

**Input**: Multi-page Streamlit dashboard with complex SQL views

**Command**:
```bash
python app_migrator_cli.py \
  --input ./analytics_dashboard \
  --output ./databricks_dashboard \
  --report migration_report.json
```

**Output**:
- Multi-page Streamlit structure preserved
- All SQL views converted and placed in `databricks/`
- Detailed migration report in JSON

## Output Structure

After migration, you'll get:

```
databricks_app/
├── app.yaml                    # Databricks App config
├── app.py                      # Entry point
├── requirements.txt            # Dependencies
├── README.md                   # Deployment guide
├── src/                        # Application code
│   ├── streamlit_app.py       # Main Streamlit file (if applicable)
│   ├── pages/                 # Multi-page Streamlit (if applicable)
│   │   ├── 1_📊_Dashboard.py
│   │   └── 2_📈_Analytics.py
│   └── utils/                 # Helper modules
├── databricks/                 # Databricks-specific
│   ├── unity_catalog_setup.sql # UC setup script
│   └── init_scripts/          # Init scripts
└── tests/                      # Test placeholders
```

## Deployment Steps

After migration:

### 1. Review Generated Files

```bash
cd databricks_app
cat README.md  # Read deployment instructions
cat app.yaml   # Verify app configuration
```

### 2. Set Up Environment

```bash
export DATABRICKS_SERVER_HOSTNAME="your-workspace.cloud.databricks.com"
export DATABRICKS_HTTP_PATH="/sql/1.0/warehouses/xxxxx"
export DATABRICKS_TOKEN="your-token"
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Set Up Unity Catalog (if needed)

```bash
databricks sql execute -f databricks/unity_catalog_setup.sql
```

### 5. Test Locally (for Streamlit)

```bash
streamlit run src/streamlit_app.py
```

### 6. Deploy to Databricks

```bash
databricks apps deploy
```

## Troubleshooting

### Issue: "Module not found" errors

**Solution**: Check `requirements.txt` and ensure all dependencies are listed.

```bash
pip install -r requirements.txt
```

### Issue: SQL conversion errors

**Solution**: Review `databricks/*.sql` files. Snowflake-specific syntax (VARIANT, FLATTEN, etc.) needs manual adjustment.

### Issue: Snowpark → PySpark conversion issues

**Solution**: The converter handles basic patterns. For complex Snowpark code, review `src/` files and:
- Replace `session.table()` with `spark.table()`
- Replace `session.sql()` with `spark.sql()`
- Update UDF decorators: `@udf` → `@udf(returnType=...)`

### Issue: Permission errors after deployment

**Solution**: Review Unity Catalog grants in `databricks/unity_catalog_setup.sql` and adjust for your workspace.

## Advanced Options

### Generate Analysis Report Only

```bash
python app_migrator_cli.py \
  --input ./snowflake_app \
  --analyze-only \
  --report analysis.json
```

Then review `analysis.json` to understand migration complexity before proceeding.

### Custom App Name

```bash
python app_migrator_cli.py \
  --input ./snowflake_app \
  --output ./databricks_app \
  --app-name my_custom_app_name
```

## Support

For issues or questions:
- Review the [README.md](README.md) for detailed architecture
- Check generated `README.md` in output directory for app-specific guidance
- Consult [Databricks Apps documentation](https://docs.databricks.com/en/dev-tools/databricks-apps/)

## Examples

See the `examples/` directory for sample migrations:
- `examples/simple_streamlit/` - Basic Streamlit app
- `examples/api_app/` - Flask API with database queries
- `examples/analytics_dashboard/` - Multi-page dashboard with complex SQL
