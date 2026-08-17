from __future__ import annotations

import json
import os
from pathlib import Path

import streamlit as st

from snow2lake_ai.ai.databricks_sql_ai import DatabricksSQLAIProvider
from snow2lake_ai.connectors.databricks_sql import DatabricksSQLClient, test_databricks_connection
from snow2lake_ai.connectors.snowflake_client import SnowflakeStageClient, test_snowflake_connection
from snow2lake_ai.orchestrator import run_stage_migration
from snow2lake_ai.report.generator import write_html_report, write_json_report

st.set_page_config(page_title="Snow2Lake AI", page_icon="❄️", layout="wide")
st.title("❄️ → 🧱 Snow2Lake AI")
st.caption("Snowflake Stage → deterministic migration → Databricks SQL AI → validated local Databricks project")

if "scan" not in st.session_state:
    st.session_state.scan = None
if "report" not in st.session_state:
    st.session_state.report = None
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

CONFIG_FILE = "config.json"

def load_saved_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_config(config_dict):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config_dict, f, indent=2)
    except Exception:
        pass

saved_cfg = load_saved_config()

# App name input to group outputs under output_dir/app_name
st.sidebar.subheader("App Scope")
app_name = st.sidebar.text_input("Application Name", value=saved_cfg.get("app_name", "my_snowflake_app"))

with st.sidebar:
    st.header("1. Snowflake source")
    sf_account = st.text_input("Account", value=saved_cfg.get("sf_account", os.getenv("SNOWFLAKE_ACCOUNT", "")))
    sf_user = st.text_input("User", value=saved_cfg.get("sf_user", os.getenv("SNOWFLAKE_USER", "")))
    sf_password = st.text_input("Password", type="password", value=saved_cfg.get("sf_password", os.getenv("SNOWFLAKE_PASSWORD", "")))
    sf_auth = st.selectbox("Authenticator", ["snowflake", "externalbrowser"], index=0 if saved_cfg.get("sf_auth", "snowflake") == "snowflake" else 1)
    sf_wh = st.text_input("Warehouse", value=saved_cfg.get("sf_wh", os.getenv("SNOWFLAKE_WAREHOUSE", "")))
    sf_db = st.text_input("Database", value=saved_cfg.get("sf_db", os.getenv("SNOWFLAKE_DATABASE", "")))
    sf_schema = st.text_input("Schema", value=saved_cfg.get("sf_schema", os.getenv("SNOWFLAKE_SCHEMA", "")))
    sf_role = st.text_input("Role", value=saved_cfg.get("sf_role", os.getenv("SNOWFLAKE_ROLE", "")))
    stage = st.text_input("Application stage", value=saved_cfg.get("stage", "@APP_PACKAGE_STAGE"))
    prefix = st.text_input("Stage prefix (optional)", value=saved_cfg.get("prefix", ""))
    test_sf = st.button("Test Snowflake", use_container_width=True)
    scan_sf = st.button("Scan Stage", type="primary", use_container_width=True)

    st.divider()
    st.header("2. Databricks SQL AI")
    db_host = st.text_input("Server hostname", value=saved_cfg.get("db_host", os.getenv("DATABRICKS_SERVER_HOSTNAME", "")))
    db_path = st.text_input("HTTP path", value=saved_cfg.get("db_path", os.getenv("DATABRICKS_HTTP_PATH", "")))
    db_token = st.text_input("Access token", type="password", value=saved_cfg.get("db_token", os.getenv("DATABRICKS_ACCESS_TOKEN", "")))
    ai_model = st.text_input("AI model / endpoint", value=saved_cfg.get("ai_model", os.getenv("DATABRICKS_AI_MODEL", "databricks-gpt-oss-20b")))
    test_db = st.button("Test Databricks SQL", use_container_width=True)

    st.divider()
    base_output_dir = st.text_input("Base Output folder", value=saved_cfg.get("base_output_dir", str(Path.cwd() / "output")))
    migrate = st.button("🚀 Migrate Stage", type="primary", use_container_width=True)

# Build the specific app's output directory path
output_dir = str(Path(base_output_dir) / app_name)

# Save any changes in the configs when any of the triggers are pressed
if test_sf or scan_sf or test_db or migrate:
    save_config({
        "app_name": app_name,
        "sf_account": sf_account, "sf_user": sf_user, "sf_password": sf_password, "sf_auth": sf_auth,
        "sf_wh": sf_wh, "sf_db": sf_db, "sf_schema": sf_schema, "sf_role": sf_role,
        "stage": stage, "prefix": prefix, "db_host": db_host, "db_path": db_path,
        "db_token": db_token, "ai_model": ai_model, "base_output_dir": base_output_dir
    })

sf_config = {
    "account": sf_account, "user": sf_user, "password": sf_password,
    "authenticator": sf_auth, "warehouse": sf_wh, "database": sf_db,
    "schema": sf_schema, "role": sf_role,
}
db_config = {"server_hostname": db_host, "http_path": db_path, "access_token": db_token, "model": ai_model}

if test_sf:
    ok, msg = test_snowflake_connection(sf_config)
    (st.success if ok else st.error)(msg)

if test_db:
    ok, msg = test_databricks_connection(db_config)
    (st.success if ok else st.error)(msg)

if scan_sf:
    try:
        with st.spinner("Listing stage files..."):
            with SnowflakeStageClient(sf_config) as client:
                listing = client.list_stage(stage)
        st.session_state.scan = listing
        st.success(f"Found {len(listing)} staged entries.")
    except Exception as exc:
        st.error(f"Stage scan failed: {exc}")

# App Explorer - Load previous apps if they exist in the output folder
st.subheader("📁 App Explorer")
existing_apps = []
if os.path.exists(base_output_dir):
    existing_apps = [d.name for d in Path(base_output_dir).iterdir() if d.is_dir() and (d / "migration_report.json").exists()]

# Always try to load the current app name's migration report if it exists on disk and we haven't loaded one yet
if st.session_state.report is None or (st.session_state.report.application_name != app_name):
    report_json_path = Path(output_dir) / "migration_report.json"
    if report_json_path.exists():
        try:
            from snow2lake_ai.models import MigrationReport
            with open(report_json_path, "r", encoding="utf-8") as rf:
                st.session_state.report = MigrationReport.from_dict(json.load(rf))
        except Exception:
            pass

if existing_apps:
    selected_app = st.selectbox("Select converted app to review/edit/deploy:", sorted(list(set(existing_apps + [app_name]))), index=sorted(list(set(existing_apps + [app_name]))).index(app_name) if app_name in sorted(list(set(existing_apps + [app_name]))) else 0)
    if selected_app != app_name:
        app_name = selected_app
        output_dir = str(Path(base_output_dir) / app_name)
        # Load the report for this selected app from disk
        report_json_path = Path(output_dir) / "migration_report.json"
        if report_json_path.exists():
            try:
                from snow2lake_ai.models import MigrationReport
                with open(report_json_path, "r", encoding="utf-8") as rf:
                    st.session_state.report = MigrationReport.from_dict(json.load(rf))
                st.rerun()
            except Exception:
                pass

st.subheader("Stage inventory")
if st.session_state.scan is not None:
    rows = st.session_state.scan
    st.dataframe(rows, use_container_width=True, hide_index=True)
else:
    # Check if we already have a loaded report to avoid confusing "Enter stage and click Scan" instruction
    if st.session_state.report is not None:
        st.info("Loaded converted application from workspace. You can edit and deploy below without scanning/migrating again.")
    else:
        st.info("Enter the Snowflake stage and click **Scan Stage**. The stage is the migration source of truth.")

if migrate:
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    ai_provider = DatabricksSQLAIProvider(db_config)
    with st.spinner("Downloading stage, converting objects, calling Databricks SQL AI where needed, validating, and writing files..."):
        try:
            report = run_stage_migration(sf_config, stage, output_dir, ai_provider, prefix=prefix, application_name=app_name)
            st.session_state.report = report
        except Exception as exc:
            st.exception(exc)

report = st.session_state.report
# Always show workspace IDE if files are present, even if report wasn't re-generated/is none
all_files = []
if os.path.exists(output_dir):
    for f in sorted(Path(output_dir).rglob("*")):
        if f.is_file():
            # Exclude report JSON and HTML files from editable files list
            rel = str(f.relative_to(output_dir))
            if not rel.endswith(".json") and not rel.endswith(".html"):
                all_files.append(rel)

if all_files:
    st.divider()
    st.subheader("🖥️ Interactive Workspace IDE")
    
    ide_col1, ide_col2 = st.columns([1, 2])
    
    with ide_col1:
        st.write("**Project Files**")
        selected_rel_file = st.radio("Select file to edit/deploy:", all_files, key="ide_file_selector")
        
    with ide_col2:
        if selected_rel_file:
            selected_file_path = Path(output_dir) / selected_rel_file
            code_content = selected_file_path.read_text(errors="ignore")
            st.write(f"Editing: `{selected_rel_file}`")
            edited_code = st.text_area("Source Code", value=code_content, height=400, key=f"editor_{selected_rel_file}")
            
            save_col, ai_col = st.columns(2)
            with save_col:
                if edited_code != code_content:
                    if st.button("💾 Save Local Changes"):
                        selected_file_path.write_text(edited_code, encoding="utf-8")
                        st.success("Saved successfully!")
                        st.rerun()
            with ai_col:
                ai_instruction = st.text_input("Instruction for Databricks AI:", placeholder="e.g. Add logging, fix syntax...", key=f"ai_inst_{selected_rel_file}")
                if st.button("🧠 Apply AI Edit", key=f"ai_btn_{selected_rel_file}"):
                    if not ai_instruction.strip():
                        st.warning("Please enter an instruction.")
                    else:
                        with st.spinner("Applying AI refinement..."):
                            try:
                                ai_provider = DatabricksSQLAIProvider(db_config)
                                prompt = f"Refine the following code based on this instruction: {ai_instruction}\n\nOriginal Code:\n{edited_code}"
                                response = ai_provider.generate(prompt, {"original_code": edited_code, "instruction": ai_instruction})
                                if response.generated_code:
                                    selected_file_path.write_text(response.generated_code, encoding="utf-8")
                                    st.success("AI refinement applied!")
                                    st.rerun()
                                else:
                                    st.error(f"Failed: {response.warnings or response.manual_review}")
                            except Exception as e:
                                st.error(f"Error: {e}")

            # Inline Deployment Component
            st.write("---")
            st.write("🚀 **Deploy to Databricks**")
            d_col1, d_col2 = st.columns(2)
            with d_col1:
                deploy_mode = st.selectbox("Deploy Target", ["SQL Warehouse Execution", "DAB (Databricks Asset Bundle) Setup"], key="dep_target")
            with d_col2:
                if st.button("Run Deployment", key="run_dep_btn"):
                    if deploy_mode == "SQL Warehouse Execution":
                        if selected_file_path.suffix == ".sql":
                            with st.spinner("Executing SQL DDL..."):
                                try:
                                    with DatabricksSQLClient(db_config) as client:
                                        stmts = [s.strip() for s in edited_code.split(";") if s.strip()]
                                        for s in stmts:
                                            client.query(s)
                                        st.success("Statements executed successfully on Databricks!")
                                except Exception as e:
                                    st.error(f"Execution Error: {e}")
                                    st.session_state.chat_history.append({"role": "system", "content": f"Deployment failed on SQL Warehouse with error: {e}"})
                        else:
                            st.warning("SQL Warehouse execution is only supported for .sql files.")
                    else:
                        st.info("Bundle workspace generated. Use 'databricks bundle deploy' locally.")

# We only display assessment metadata if the report is active
if report is not None:
    d = report.to_dict()
    st.divider()
    st.subheader("Migration assessment")
    cols = st.columns(6)
    cols[0].metric("Objects", d["objects_analyzed"])
    cols[1].metric("🟢 Automated", d["automated"])
    cols[2].metric("🟡 AI-Assisted", d["ai_assisted"])
    cols[3].metric("🟠 Redesign", d["architecture_redesign"])
    cols[4].metric("🔴 High complexity", d["high_complexity"])
    cols[5].metric("Coverage", f"{d['migration_coverage_percent']}%")

    st.dataframe([
        {
            "": o["migration_emoji"], "Object": o["object"], "Source": o["source_type"],
            "Target": o["target_type"], "Type": o["migration_type"],
            "Script %": o["script_percentage"], "AI %": o["ai_percentage"],
            "Manual %": o["manual_percentage"], "Confidence": o["confidence"],
            "Validated": "✅" if o["validated"] else "❌",
            "Output": o.get("generated_file", ""),
        } for o in d["objects"]
    ], use_container_width=True, hide_index=True)

    # Sidebar Databricks Genie AI Debug Chat Panel
    st.sidebar.divider()
    st.sidebar.subheader("💬 Databricks Genie AI")
    
    # New Chat / Clear Chat session option
    if st.sidebar.button("🗑️ New Chat"):
        st.session_state.chat_history = []
        st.rerun()

    for chat in st.session_state.chat_history:
        with st.sidebar.chat_message(chat["role"]):
            st.sidebar.markdown(chat["content"])
            
    chat_input = st.sidebar.chat_input("Ask Databricks Genie AI about errors, tables, or SQL queries...")
    if chat_input:
        st.session_state.chat_history.append({"role": "user", "content": chat_input})
        with st.sidebar.chat_message("user"):
            st.sidebar.markdown(chat_input)
            
        with st.sidebar.chat_message("assistant"):
            with st.spinner("Genie thinking..."):
                try:
                    ai_provider = DatabricksSQLAIProvider(db_config)
                    # Create prompt injecting code context if a file is open
                    context_info = ""
                    if selected_rel_file:
                        context_info = f"Current active file is: {selected_rel_file}\nContent:\n{edited_code}\n\n"
                    
                    # Also pass historical context if there are previous exchanges
                    history_context = ""
                    if len(st.session_state.chat_history) > 1:
                        history_context = "Conversation history:\n" + "\n".join(f"{msg['role'].upper()}: {msg['content']}" for msg in st.session_state.chat_history[:-1]) + "\n\n"
                    
                    full_chat_prompt = (
                        f"{context_info}{history_context}You are Databricks Genie AI, a smart assistant specialized in data, SQL, and migrations. "
                        f"Answer the user's question, help debug execution errors, explain target schemas, or suggest modifications. "
                        f"If the user asks a question, reply with a detailed explanation in markdown. "
                        f"User Question:\n{chat_input}"
                    )
                    response = ai_provider.generate(full_chat_prompt, {"chat_input": chat_input, "active_file": selected_rel_file})
                    
                    # Handle raw markdown reply or structural reply from AI response mapping
                    reply = response.business_logic_summary or response.generated_code or "Sorry, Genie encountered an issue processing this request."
                    # If response generated code was returned, append it
                    if response.generated_code and response.generated_code != edited_code:
                        reply += f"\n\n```sql\n{response.generated_code}\n```"
                    if response.warnings:
                        reply += "\n\n⚠️ Genie Warnings:\n" + "\n".join(response.warnings)
                        
                    st.sidebar.markdown(reply)
                    st.session_state.chat_history.append({"role": "assistant", "content": reply})
                except Exception as e:
                    st.sidebar.error(f"Error: {e}")

    # Generate Reports
    json_path = write_json_report(report, str(Path(output_dir) / "migration_report.json"))
    html_path = write_html_report(report, str(Path(output_dir) / "migration_report.html"))
    c1, c2 = st.columns(2)
    c1.download_button("Download JSON report", Path(json_path).read_bytes(), file_name="migration_report.json")
    c2.download_button("Download HTML report", Path(html_path).read_bytes(), file_name="migration_report.html")
