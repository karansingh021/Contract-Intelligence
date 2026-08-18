# Getting Started with Snowflake Native App Migrator

Welcome! This specialized tool helps you migrate Snowflake Native Applications to Databricks Apps.

## ⚡ Quick Start (5 minutes)

### 1. Run the Demo

The fastest way to see the migrator in action:

```bash
cd /Workspace/Users/<your-email>/Snow2LakeAI/snowflake_app_migrator
python demo.py
```

This will:
- ✅ Analyze the example Snowflake app in `example_snowflake_app/`
- ✅ Convert it to Databricks App format
- ✅ Generate output in `demo_output/`
- ✅ Show you exactly what was transformed

### 2. Review the Output

```bash
cd demo_output
ls -la
cat README.md  # Read the deployment guide
```

You'll see:
```
demo_output/
├── app.yaml                  # Databricks App config
├── app.py                    # Entry point
├── requirements.txt          # Dependencies
├── README.md                 # Deployment instructions
├── src/
│   └── streamlit_app.py      # Converted Streamlit app
├── databricks/
│   └── unity_catalog_setup.sql
└── tests/
```

### 3. Compare Original vs Converted

**Original (Snowflake):**
```python
# example_snowflake_app/streamlit_app.py
import snowflake.connector
from snowflake.snowpark import Session

conn = snowflake.connector.connect(...)
session = get_snowpark_session()
df = session.table("sales_data").filter(...).to_pandas()
```

**Converted (Databricks):**
```python
# demo_output/src/streamlit_app.py
from databricks import sql
from pyspark.sql import SparkSession

conn = get_db_connection()  # Helper function added
df = spark.table("sales_data").filter(...).toPandas()
```

## 🛠️ Migrate Your Own App

### Option 1: Local Snowflake App

If you have a Snowflake Native App directory locally:

```bash
python app_migrator_cli.py \
  --input /path/to/your/snowflake/app \
  --output ./my_databricks_app
```

### Option 2: Download from Snowflake Stage

If your app is in a Snowflake stage:

1. **Create config file:**
```bash
cp config.example.json config.json
# Edit config.json with your Snowflake credentials
```

2. **Run migration:**
```bash
python app_migrator_cli.py \
  --snowflake-stage @YOUR_APP_STAGE \
  --snowflake-config config.json \
  --output ./my_databricks_app
```

### Option 3: Analyze First

Not sure about complexity? Analyze first:

```bash
python app_migrator_cli.py \
  --input /path/to/snowflake/app \
  --analyze-only \
  --report analysis.json
```

Review `analysis.json` to understand:
- Migration complexity (low/medium/high)
- What components will be converted
- Potential issues and warnings
- Recommended approach

## 📖 What Gets Converted?

| Snowflake Component | Databricks Equivalent | Auto-Converted? |
|---------------------|------------------------|------------------|
| **manifest.yml** | app.yaml | ✅ Yes |
| **Streamlit UI** | Streamlit on Databricks | ✅ Yes |
| **Snowpark DataFrames** | PySpark DataFrames | ✅ Yes |
| **snowflake.connector** | databricks.sql | ✅ Yes |
| **SQL Views** | SQL Views | ✅ Yes |
| **UDFs (SQL)** | SQL UDFs | ⚠️ Review needed |
| **Stored Procedures** | Python UDFs | ⚠️ Review needed |
| **Privileges** | UC Grants | ⚠️ Manual mapping |

## 🔍 Understanding the Analysis

When you run the analyzer, you'll see:

```
============================================================
 SNOWFLAKE NATIVE APP ANALYSIS
============================================================
 App Name:           example_snowflake_app
 App Path:           /path/to/app
 Migration Complexity: MEDIUM
============================================================

📊 COMPONENTS:
   Python files:       1
   SQL files:          1
   Streamlit pages:    1
   Has API:            No
   Stored Procedures:  Yes
   UDFs:               Yes

🔧 SNOWPARK USAGE:
   from snowflake.snowpark: 2 occurrences
   session.table(: 1 occurrences

📦 DEPENDENCIES:
   • pandas
   • snowflake-connector-python
   • snowflake-snowpark-python
   • streamlit

⚠️  WARNINGS:
   • Stored procedures detected - may need rewrite

💡 RECOMMENDATIONS:
   ✓ Streamlit app detected - use Databricks Apps Streamlit runtime
   ✓ Replace snowflake.connector with databricks.sql.connect
   ⚠ Stored procedures detected - consider converting to Python UDFs
   ✓ Replace snowflake-snowpark-python with pyspark
============================================================
```

### Complexity Levels

**LOW (Score ≤ 5):**
- Simple Streamlit app
- Basic SQL queries
- No Snowpark usage
- ⌛ Estimated effort: 1-2 hours

**MEDIUM (Score 6-12):**
- Streamlit + Snowpark
- Some UDFs
- Moderate SQL complexity
- ⌛ Estimated effort: 1-2 days

**HIGH (Score > 12):**
- Complex stored procedures
- Heavy Snowpark usage
- Advanced SQL features
- ⌛ Estimated effort: 1 week+

## 🧠 Architecture

### Migration Pipeline

```
┌─────────────────────────────┐
│ Snowflake Native App    │
│                           │
│ ├─ manifest.yml          │
│ ├─ streamlit_app.py      │
│ ├─ setup.sql             │
│ └─ requirements.txt      │
└─────────────────────────────┘
         ↓
         ↓ app_analyzer.py
         ↓ (Scans structure, detects patterns)
         ↓
┌─────────────────────────────┐
│ AppAnalysis Object      │
│                           │
│ • Components            │
│ • Complexity            │
│ • Dependencies          │
│ • Recommendations       │
└─────────────────────────────┘
         ↓
         ↓ app_converter.py
         ↓ (Transforms code, generates files)
         ↓
┌─────────────────────────────┐
│ Databricks App           │
│                           │
│ ├─ app.yaml              │
│ ├─ app.py                │
│ ├─ src/streamlit_app.py  │
│ ├─ databricks/*.sql      │
│ └─ requirements.txt      │
└─────────────────────────────┘
```

### Key Transformations

**1. Connector Updates:**
```python
# Before
import snowflake.connector
conn = snowflake.connector.connect(...)

# After
from databricks import sql
conn = sql.connect(
    server_hostname=os.environ["DATABRICKS_SERVER_HOSTNAME"],
    http_path=os.environ["DATABRICKS_HTTP_PATH"],
    access_token=os.environ["DATABRICKS_TOKEN"]
)
```

**2. Snowpark → PySpark:**
```python
# Before
from snowflake.snowpark import Session
df = session.table("sales").filter(...)

# After
from pyspark.sql import SparkSession
df = spark.table("sales").filter(...)
```

**3. Configuration:**
```yaml
# Before (manifest.yml)
manifest_version: 1
version:
  name: 1.0.0

# After (app.yaml)
name: my_app
streamlit:
  app_file: src/streamlit_app.py
```

## 🛡️ Best Practices

### 1. Test in Stages

```bash
# Stage 1: Analyze
python app_migrator_cli.py --input ./app --analyze-only

# Stage 2: Convert
python app_migrator_cli.py --input ./app --output ./db_app

# Stage 3: Test locally
cd db_app && streamlit run src/streamlit_app.py

# Stage 4: Deploy
databricks apps deploy
```

### 2. Review Before Deploying

Always review:
- ✅ `src/streamlit_app.py` - Check all connector changes
- ✅ `databricks/*.sql` - Verify SQL syntax
- ✅ `app.yaml` - Confirm permissions
- ✅ `requirements.txt` - Ensure all deps listed

### 3. Handle Complex Procedures Manually

For complex stored procedures:
1. Review the generated Python UDF template
2. Test the logic separately
3. Validate outputs match Snowflake
4. Consider breaking into smaller functions

### 4. Use Version Control

```bash
git init db_app
cd db_app
git add .
git commit -m "Initial Databricks App migration"
```

## 📚 Additional Resources

- **[README.md](README.md)** - Complete documentation
- **[USAGE.md](USAGE.md)** - Detailed usage examples
- **[config.example.json](config.example.json)** - Configuration template
- **[example_snowflake_app/](example_snowflake_app/)** - Sample app to migrate

## 🎯 Real-World Examples

### Example 1: Simple Dashboard

```bash
# Your app: streamlit_app.py + a few SQL queries
python app_migrator_cli.py --input ./my_dashboard --output ./db_dashboard

# Result: Ready to deploy in ~1 hour
# • Streamlit UI: 95% auto-converted
# • SQL queries: Need minor syntax review
# • Complexity: LOW
```

### Example 2: Analytics Platform

```bash
# Your app: Multi-page Streamlit + Snowpark + stored procedures
python app_migrator_cli.py --input ./analytics --output ./db_analytics

# Result: Needs 2-3 days of work
# • Streamlit pages: Auto-converted
# • Snowpark code: Auto-converted, test thoroughly
# • Stored procedures: Template generated, needs implementation
# • Complexity: MEDIUM-HIGH
```

## ❓ FAQ

**Q: Will my app work immediately after migration?**
A: Simple Streamlit apps often work with minimal changes. Complex apps need review and testing.

**Q: What about Snowflake-specific features (VARIANT, FLATTEN)?**
A: These require manual conversion. The migrator flags them for review.

**Q: Can I migrate incrementally?**
A: Yes! Migrate and test one component at a time.

**Q: How do I handle authentication?**
A: Set environment variables or use Databricks secrets. See the generated README.

**Q: What if migration fails?**
A: Check warnings in the analysis. Some apps need manual intervention.

## 🚀 Next Steps

1. **Run the demo** to see it in action
2. **Analyze your app** to understand complexity
3. **Start with a test app** (not production)
4. **Review the output** carefully
5. **Deploy and test** in a dev workspace
6. **Iterate** based on findings

## 👋 Need Help?

Check the generated `README.md` in your output directory for app-specific guidance.

For general questions, refer to:
- [Databricks Apps Documentation](https://docs.databricks.com/en/dev-tools/databricks-apps/)
- [Databricks Community Forums](https://community.databricks.com/)

---

**Ready to get started?**

```bash
python demo.py  # Run the demo!
```
