# Creating and Deploying Apps in Databricks vs. Snowflake

This reference guide outlines the core architecture and requirements difference between **Databricks Apps** and **Snowflake Native Apps**.

---

## 1. App Architecture & Deployment Model

| Feature | Snowflake Native App | Databricks App |
| :--- | :--- | :--- |
| **Hosting Model** | Hosted inside consumer Snowflake account boundary. Runs within an isolated sandbox. | Managed containerized environment (hosted on serverless compute in Databricks workspace). |
| **Manifest File** | `manifest.yml` - defines package, version, entry points, setup script, roles, and privileges. | `databricks.yml` - defines bundle config, application settings, environment variables, and resources.<br>`app.yaml` - defines runtime behavior, environment variables, and startup command (e.g. `["streamlit", "run", "app.py"]`). |
| **CLI & Tools** | Snowflake CLI / SQL | Databricks CLI (v0.250.0 or above is required for Databricks Apps support). |
| **Development SDK**| Snowflake Provider/Consumer API, Snowpark API. | Databricks SDK for Python (`WorkspaceClient`), `@databricks/appkit` for TypeScript. |
| **User Interface** | Streamlit-in-Snowflake, Native SQL commands, worksheets. | Flexible web apps (Dash, Streamlit, Gradio, Flask, React/Node.js, etc.). |

---

## 2. Identity and Authentication

### Snowflake
- USERS access via Snowflake role hierarchy (`APPLICATION ROLE`).
- Privileges are granted to/by consumer accounts explicitly (e.g., access to external tables, stages, databases).

### Databricks
Databricks Apps authenticate using a dual-identity model:
1. **Service Principal Authorization (Default)**:
   - Every app has a dedicated system-managed Service Principal automatically provisioned when the app is created.
   - For background actions, catalog access, or DB queries, you grant standard Unity Catalog privileges to the app's Service Principal.
   - Credentials (`DATABRICKS_CLIENT_ID` and `DATABRICKS_CLIENT_SECRET`) are automatically provided in the app's environment at runtime.
2. **On-Behalf-Of-User (OBO) Authorization**:
   - For interactive apps, authorization can run under the credentials of the logged-in user.
   - Databricks passes the active user token in the `x-forwarded-access-token` HTTP header.
   - The app can instantiate the `WorkspaceClient` using this token to enforce user-specific policies (like column masking or row-level security).

---

## 3. Configuration & Resource Definition

### Snowflake `manifest.yml` Example:
```yaml
manifest_version: 1
version:
  name: "1.0"
  label: "My Snowflake App"
artifacts:
  setup_script: setup.sql
  readme: README.md
privileges:
  - reference_database:
      description: "Access to target user database"
```

### Databricks App Configuration Examples:

#### A. Databricks Asset Bundle (`databricks.yml`)
In Databricks, permissions and required data sources (like SQL Warehouses, Delta tables, or Volumes) are declared in `databricks.yml` resources:
```yaml
bundle:
  name: my_databricks_app

app:
  name: my_app
  entry_point: app/streamlit_app.py
  # Scopes declare API permissions for OAuth
  oauth_scopes:
    - "all-apis"
```

#### B. Runtime Configuration (`app.yaml`)
Put an `app.yaml` file in the root of your application directory (e.g., `app/` or the bundle root) to specify runtime parameters and startup command overrides:
```yaml
# app.yaml
command:
  - "streamlit"
  - "run"
  - "app.py"
env:
  - name: "LOG_LEVEL"
    value: "INFO"
```

Instead of manually granting database privileges through a complex SQL setup script like in Snowflake, you assign roles directly in Unity Catalog to the App's Service Principal:
- `GRANT SELECT ON SCHEMA catalog.schema TO `my_app_service_principal`;`

---

## 4. Deployment Flow
To deploy your Databricks App using Databricks Asset Bundles:
1. Ensure the Databricks CLI v0.250.0+ is installed and authenticated.
2. Initialize or configure `databricks.yml` and `app.yaml` in your project.
3. Deploy the application:
   ```bash
   databricks bundle deploy
   ```
