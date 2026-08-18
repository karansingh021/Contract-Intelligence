# Snowflake Native App → Databricks App Migrator

Specialized tool for migrating Snowflake Native Applications to Databricks Apps (Apps V2 platform).

## What It Does

### Analyzes Snowflake Native App Structure:
- **manifest.yml** - App metadata, version, privileges
- **setup.sql** - Setup scripts and stored procedures
- **Streamlit apps** - UI code (streamlit_app.py, pages/)
- **UDFs & Stored Procedures** - Application logic
- **Data models** - Tables, views, stages
- **Permissions** - Role-based access control

### Converts to Databricks App Format:
- **app.yaml** - Databricks App configuration
- **app.py** - Main app entry point (Flask/FastAPI)
- **requirements.txt** - Python dependencies
- **Transformed code** - Snowpark → PySpark transformations
- **Unity Catalog** - Data access patterns
- **Serving endpoints** - Model/API serving configuration

### Migration Patterns:

| Snowflake Component | Databricks Equivalent |
|---------------------|------------------------|
| manifest.yml | app.yaml |
| Streamlit app | Streamlit on Databricks App |
| setup.sql | Unity Catalog DDL + init scripts |
| Snowpark procedures | PySpark in app.py |
| NATIVEAPP stage | Workspace files + volumes |
| Application versioning | App versioning |
| Permissions (USAGE, SELECT) | Unity Catalog grants |

## Installation

```bash
cd /Workspace/Users/<your-email>/Snow2LakeAI
pip install -r requirements.txt
```

## Usage

### CLI Mode:

```bash
python snowflake_app_migrator/app_migrator_cli.py \
  --snowflake-stage @APP_STAGE \
  --app-name my_app \
  --output ./output/databricks_app
```

### Python API:

```python
from snowflake_app_migrator.app_analyzer import SnowflakeAppAnalyzer
from snowflake_app_migrator.app_converter import DatabricksAppConverter

# Analyze Snowflake app
analyzer = SnowflakeAppAnalyzer()
app_structure = analyzer.analyze("/path/to/snowflake/app")

# Convert to Databricks
converter = DatabricksAppConverter()
db_app = converter.convert(app_structure, output_dir="./output")

print(f"✅ Databricks App created: {db_app.app_path}")
```

## Migration Workflow

```
┌─────────────────────────────────────────────────────────────┐
│ 1. EXTRACT                                                  │
│    • Download from Snowflake stage (@APP_STAGE)            │
│    • Parse manifest.yml                                     │
│    • Identify app components                                │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. ANALYZE                                                  │
│    • Catalog dependencies                                   │
│    • Map Snowflake privileges → UC grants                  │
│    • Identify Streamlit vs API app                         │
│    • Detect Snowpark usage                                  │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. TRANSFORM                                                │
│    • Convert manifest.yml → app.yaml                        │
│    • Transform Snowpark → PySpark                           │
│    • Adapt Streamlit code for Databricks                   │
│    • Rewrite SQL (Snowflake → Databricks SQL)              │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. GENERATE                                                 │
│    • Create app.yaml                                        │
│    • Write app.py entry point                               │
│    • Generate requirements.txt                              │
│    • Create Unity Catalog setup scripts                    │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. VALIDATE & DEPLOY                                        │
│    • Run validation checks                                  │
│    • Generate migration report                              │
│    • Deploy with: databricks apps deploy                   │
└─────────────────────────────────────────────────────────────┘
```

## Output Structure

```
output/
├── app.yaml                    # Databricks App config
├── app.py                      # Main entry point
├── requirements.txt            # Python dependencies
├── README.md                   # Deployment instructions
├── src/                        # Application code
│   ├── streamlit_app.py        # Streamlit UI (if applicable)
│   ├── api/                    # API routes (if API app)
│   └── utils/                  # Shared utilities
├── databricks/                 # Databricks-specific
│   ├── unity_catalog_setup.sql # UC tables/views/grants
│   └── init_scripts/           # Initialization scripts
├── migration_report.json       # Detailed migration report
└── migration_report.html       # Human-readable report
```

## Key Features

### 1. Streamlit App Support
- Detects Streamlit-based Native Apps
- Preserves multi-page structure (pages/ directory)
- Adapts `snowflake.connector` → `databricks.sql.connect`
- Converts `snowpark.Session` → `spark` (SparkSession)
- Updates st.connection() patterns

### 2. SQL Transformation
- Converts Snowflake SQL dialect → Databricks SQL
- Rewrites stored procedures as Python UDFs
- Transforms NATIVEAPP-specific syntax
- Updates privilege grants for Unity Catalog

### 3. Snowpark → PySpark
- DataFrame API transformations
- UDF/UDTF conversion
- Connector pattern updates
- Session management

### 4. Permission Mapping

| Snowflake Privilege | Databricks Equivalent |
|---------------------|------------------------|
| USAGE (on schema) | USE SCHEMA |
| SELECT (on table/view) | SELECT (on table/view) |
| EXECUTE (on function) | EXECUTE (on function) |
| APPLICATION ROLE | Service Principal |

## Configuration

Create `config.json` in the project root:

```json
{
  "snowflake": {
    "account": "your-account",
    "user": "your-user",
    "warehouse": "COMPUTE_WH",
    "database": "APP_DB",
    "schema": "PUBLIC"
  },
  "databricks": {
    "host": "https://your-workspace.cloud.databricks.com",
    "token": "${DATABRICKS_TOKEN}",
    "catalog": "main",
    "schema": "apps"
  }
}
```

## Migration Checklist

- [ ] Download Snowflake Native App source from stage
- [ ] Run analyzer to understand app structure
- [ ] Review generated migration report
- [ ] Manually review complex stored procedures
- [ ] Test Streamlit UI components
- [ ] Validate SQL transformations
- [ ] Set up Unity Catalog grants
- [ ] Deploy to Databricks Apps
- [ ] Test end-to-end functionality
- [ ] Monitor performance and errors

## Known Limitations

1. **Manual Review Required:**
   - Complex stored procedures with advanced logic
   - Dynamic SQL generation patterns
   - Cross-database references

2. **Not Auto-Converted:**
   - External integrations (webhooks, APIs)
   - Snowflake-specific features (tasks, streams)
   - Advanced security features (masking policies)

3. **Requires Adaptation:**
   - Authentication/authorization flows
   - Data loading patterns
   - Monitoring and alerting

## Support & Development

### Extending the Migrator:

1. **Add new transformers** in `transformers/`
2. **Custom validation rules** in `validators/`
3. **Template customization** in `templates/`

### Testing:

```bash
pytest tests/test_app_migrator.py -v
```

## Examples

See `examples/` directory for:
- Simple Streamlit app migration
- API-based app migration
- Multi-component app migration
- Data analytics dashboard migration

## License

MIT License - See LICENSE file for details
