from __future__ import annotations

import json
import shutil
import tempfile
import re
from pathlib import Path
from typing import Any

from snow2lake_ai.ai.provider import AIProvider
from snow2lake_ai.models import MigrationObject, MigrationReport, MigrationType, ObjectType, SourceObject, DependencyEdge, ValidationStatus
from snow2lake_ai.scanner.dependency_graph import build_dependency_graph
from snow2lake_ai.scanner.scanner import scan_application
from snow2lake_ai.sql_migrator.migrator import migrate_sql_file, _migrate_statement
from snow2lake_ai.python_migrator.migrator import migrate_python_file
from snow2lake_ai.validation.validator import validate_all
from snow2lake_ai.stage.stage_scanner import pull_stage_to_local
from snow2lake_ai.connectors.snowflake_client import SnowflakeStageClient
from sqlglot import exp

READ_DIALECT = "snowflake"


def run_migration(
    input_path: str,
    output_dir: str,
    ai_provider: AIProvider,
    application_name: str | None = None,
) -> MigrationReport:
    return _run_local(input_path, output_dir, ai_provider, application_name)


def run_stage_migration(
    snowflake_config: dict[str, Any],
    stage: str,
    output_dir: str,
    ai_provider: AIProvider,
    prefix: str = "",
    application_name: str | None = None,
) -> MigrationReport:
    """Download source files from a Snowflake stage, then run the same scanner.

    The stage is the source of truth; no ZIP upload is required.
    """
    out = Path(output_dir).resolve()
    source_dir = out / "_source_from_stage"
    source_dir.mkdir(parents=True, exist_ok=True)
    with SnowflakeStageClient(snowflake_config) as client:
        listing = client.list_stage(stage)
        (out / "stage_inventory.json").write_text(json.dumps(listing, default=str, indent=2), encoding="utf-8")
        pull_stage_to_local(client, stage, str(source_dir), prefix=prefix)
    report = _run_local(str(source_dir), str(out), ai_provider, application_name or stage.strip("@").split("/")[-1])
    return report


def _object_name(create_expr: exp.Create) -> str:
    this = create_expr.this
    if isinstance(this, exp.Schema):
        this = this.this
    try:
        return this.name if hasattr(this, "name") else str(this)
    except Exception:
        return str(this)


def parse_multipart_name(fullname: str) -> tuple[str, str, str]:
    parts = fullname.split(".")
    if len(parts) == 3:
        return parts[0].strip('"'), parts[1].strip('"'), parts[2].strip('"')
    elif len(parts) == 2:
        return "", parts[0].strip('"'), parts[1].strip('"')
    return "", "", fullname.strip('"')


def resolve_object_identities(source_objects: list[SourceObject]) -> list[SourceObject]:
    merged_map: dict[tuple[str, str, str, str], SourceObject] = {}
    
    for obj in source_objects:
        db = obj.raw_metadata.get("database", "").upper()
        schema = obj.raw_metadata.get("schema", "").upper()
        clean_name = obj.name.split(".")[-1].strip('"').upper()
        obj_type = obj.object_type.value
        
        key = (db, schema, obj_type, clean_name)
        
        if key in merged_map:
            existing = merged_map[key]
            if obj.source_file.endswith(".py"):
                existing.source_text = obj.source_text
                existing.raw_metadata["python_file"] = obj.source_file
            else:
                existing.raw_metadata["sql_file"] = obj.source_file
                if not existing.source_file.endswith(".py"):
                    existing.source_text = obj.source_text
        else:
            obj.raw_metadata["sql_file"] = obj.source_file
            merged_map[key] = obj
            
    return list(merged_map.values())


def split_sql_statements(sql_text: str) -> list[str]:
    # Split by semicolon, but respect double-dollar ($$) and single/double quotes
    statements = []
    current = []
    in_dollar = False
    in_single = False
    in_double = False
    
    chars = list(sql_text)
    i = 0
    while i < len(chars):
        c = chars[i]
        if c == '$' and i + 1 < len(chars) and chars[i+1] == '$':
            in_dollar = not in_dollar
            current.append('$$')
            i += 2
            continue
        elif c == "'" and not in_dollar and not in_double:
            in_single = not in_single
            current.append(c)
            i += 1
            continue
        elif c == '"' and not in_dollar and not in_single:
            in_double = not in_double
            current.append(c)
            i += 1
            continue
        elif c == ';' and not in_dollar and not in_single and not in_double:
            stmt = "".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
            i += 1
            continue
        else:
            current.append(c)
            i += 1
            
    stmt = "".join(current).strip()
    if stmt:
        statements.append(stmt)
    return statements


def discover_source_objects(scan_result: Any) -> list[SourceObject]:
    source_objects = []
    root = Path(scan_result.root_path)
    stmt_index = 0
    
    # 1. SQL files
    for rel_path in scan_result.sql_files:
        full_path = root / rel_path
        try:
            sql_text = full_path.read_text(errors="ignore")
            raw_stmts = split_sql_statements(sql_text)
            for raw_stmt in raw_stmts:
                stmt_index += 1
                try:
                    parsed_stmts = sqlglot.parse(raw_stmt, read=READ_DIALECT)
                    stmt = parsed_stmts[0] if parsed_stmts else None
                except Exception:
                    stmt = exp.Command(this="RAW_SQL", expression=exp.Literal.string(raw_stmt))
                
                if stmt is None:
                    continue
                
                kind = "UNKNOWN"
                name = ""
                
                if isinstance(stmt, exp.Create):
                    kind = (stmt.args.get("kind") or "").upper()
                    name = _object_name(stmt)
                elif isinstance(stmt, (exp.Insert, exp.Update, exp.Delete, exp.Merge)):
                    kind = "DML"
                    kind_name = type(stmt).__name__.upper()
                    name = f"{kind_name}_{stmt_index}"
                elif isinstance(stmt, exp.Drop):
                    kind = "DROP"
                    name = f"DROP_{stmt_index}"
                elif isinstance(stmt, exp.Grant):
                    kind = "GRANT"
                    name = f"GRANT_{stmt_index}"
                elif isinstance(stmt, exp.Command):
                    raw_text = stmt.sql(dialect=READ_DIALECT) if hasattr(stmt, "sql") else str(stmt)
                    for keyword in ("STREAM", "TASK", "STAGE", "FILE FORMAT"):
                        pattern_keyword = keyword.replace(' ', r'\s+')
                        if re.search(rf"\bCREATE\b.*\b{pattern_keyword}\b", raw_text, re.IGNORECASE):
                            kind = keyword
                            name_match = re.search(rf"{keyword}\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z0-9_.\"]+)", raw_text, re.IGNORECASE)
                            name = name_match.group(1) if name_match else f"{keyword}_{stmt_index}"
                            break
                    if not name and "PROCEDURE" in raw_text.upper():
                        kind = "STORED_PROCEDURE"
                        name_match = re.search(r"PROCEDURE\s+([A-Za-z0-9_.]+)", raw_text, re.IGNORECASE)
                        name = name_match.group(1) if name_match else f"PROCEDURE_{stmt_index}"
                    if not name:
                        kind = "COMMAND"
                        name = f"COMMAND_{stmt_index}"
                else:
                    kind = type(stmt).__name__.upper()
                    name = f"{kind}_{stmt_index}"
                
                if name:
                    object_type_map = {
                        "DATABASE": ObjectType.DATABASE,
                        "SCHEMA": ObjectType.SCHEMA,
                        "TABLE": ObjectType.TABLE,
                        "VIEW": ObjectType.VIEW,
                        "SECURE_VIEW": ObjectType.SECURE_VIEW,
                        "MATERIALIZED_VIEW": ObjectType.MATERIALIZED_VIEW,
                        "STORED_PROCEDURE": ObjectType.STORED_PROCEDURE,
                        "STREAM": ObjectType.STREAM,
                        "TASK": ObjectType.TASK,
                        "STAGE": ObjectType.STAGE,
                        "FILE_FORMAT": ObjectType.FILE_FORMAT,
                        "GRANT": ObjectType.GRANT,
                        "DML": ObjectType.DML_STATEMENT,
                    }
                    obj_type = object_type_map.get(kind, ObjectType.UNKNOWN)
                    db, schema, short_name = parse_multipart_name(name)
                    stmt_sql = stmt.sql(dialect=READ_DIALECT) if hasattr(stmt, "sql") else raw_stmt
                    source_objects.append(SourceObject(
                        name=name,
                        object_type=obj_type,
                        source_file=rel_path,
                        source_text=stmt_sql,
                        raw_metadata={"database": db, "schema": schema, "short_name": short_name}
                    ))
        except Exception:
            pass

    # 2. Python files
    for rel_path in scan_result.python_files:
        full_path = root / rel_path
        try:
            src = full_path.read_text(errors="ignore")
            from snow2lake_ai.python_migrator.analyzer import analyze_procedure
            analyses = analyze_procedure(src)
            for analysis in analyses:
                db, schema, short_name = parse_multipart_name(analysis.function_name)
                source_objects.append(SourceObject(
                    name=analysis.function_name,
                    object_type=ObjectType.STORED_PROCEDURE,
                    source_file=rel_path,
                    source_text=src,
                    raw_metadata={"database": db, "schema": schema, "short_name": short_name}
                ))
        except Exception:
            pass

    # 3. Streamlit files
    for rel_path in scan_result.streamlit_files:
        source_objects.append(SourceObject(
            name=Path(rel_path).stem,
            object_type=ObjectType.STREAMLIT_APP,
            source_file=rel_path,
            source_text="",
            raw_metadata={"database": "", "schema": "", "short_name": Path(rel_path).stem}
        ))
        
    return source_objects


def topological_sort(source_objects: list[SourceObject], edges: list[DependencyEdge]) -> tuple[list[SourceObject], set[str]]:
    adj = {obj.name: [] for obj in source_objects}
    for edge in edges:
        if edge.source in adj and edge.target in adj:
            adj[edge.source].append(edge.target)
            
    visited = {}
    ordered = []
    circulars = set()
    
    def dfs(name):
        if visited.get(name) == 0:
            circulars.add(name)
            return
        if visited.get(name) == 1:
            return
        visited[name] = 0
        for dep in adj[name]:
            dfs(dep)
        visited[name] = 1
        ordered.append(name)
        
    for obj in source_objects:
        if obj.name not in visited:
            dfs(obj.name)
            
    obj_map = {obj.name: obj for obj in source_objects}
    sorted_objs = [obj_map[name] for name in ordered if name in obj_map]
    return sorted_objs, circulars


def _run_local(input_path: str, output_dir: str, ai_provider: AIProvider, application_name: str | None) -> MigrationReport:
    scan_result = scan_application(input_path, application_name=application_name)
    root = Path(scan_result.root_path)
    
    # 1. Discover all source objects first
    source_objects = discover_source_objects(scan_result)
    source_objects = resolve_object_identities(source_objects)
    
    # 2. Build preliminary dependency graph among unmigrated source objects
    names = [obj.name for obj in source_objects]
    names_sorted = sorted(set(names), key=len, reverse=True)
    prelim_edges = []
    for obj in source_objects:
        seen_in_this_object = set()
        for name in names_sorted:
            if name == obj.name:
                continue
            if obj.source_text and re.search(rf"\b{re.escape(name)}\b", obj.source_text, re.IGNORECASE):
                if name not in seen_in_this_object:
                    prelim_edges.append(DependencyEdge(source=obj.name, target=name))
                    seen_in_this_object.add(name)
                    
    # 3. Topologically sort objects by dependencies
    sorted_source_objects, circulars = topological_sort(source_objects, prelim_edges)
    
    if len(sorted_source_objects) < len(source_objects):
        # Fallback to keep everything
        sorted_source_objects = source_objects

    objects: list[MigrationObject] = []
    
    # 4. Migrate objects in dependency order
    for src_obj in sorted_source_objects:
        obj_list = []
        if src_obj.object_type == ObjectType.STREAMLIT_APP:
            # Handle Streamlit
            obj = MigrationObject(
                object_name=src_obj.name,
                source_type=ObjectType.STREAMLIT_APP,
                target_type="DATABRICKS_APP_STREAMLIT",
                migration_type=MigrationType.ARCHITECTURE_REDESIGN,
                generated_code=(
                    "# Architecture redesign required.\n"
                    "# Preserve Streamlit UI where possible; replace Snowflake-specific\n"
                    "# connectors/session APIs with Databricks-supported connectivity.\n"
                    f"# Original source: {src_obj.source_file}\n"
                ),
                source_file=src_obj.source_file,
                script_percentage=50, ai_percentage=40, manual_percentage=10,
                confidence=0.75,
                changes_required=["Replace Snowflake backend/connectors and deployment model with Databricks Apps-compatible implementation."],
                manual_review=["Validate secrets, connectivity, and Databricks App deployment."],
                validation_status=ValidationStatus.GENERATED
            )
            obj_list.append(obj)
        elif src_obj.object_type == ObjectType.STORED_PROCEDURE and src_obj.source_file.endswith(".py"):
            # Handle Python procedures
            try:
                proc_objs = migrate_python_file(src_obj.source_file, src_obj.source_text, ai_provider)
                obj_list.extend(proc_objs)
            except Exception as exc:
                obj_list.append(MigrationObject(
                    object_name=src_obj.name, source_type=ObjectType.STORED_PROCEDURE,
                    target_type="UNKNOWN", migration_type=MigrationType.HIGH_COMPLEXITY,
                    generated_code="", source_file=src_obj.source_file, confidence=0.0,
                    warnings=[str(exc)], manual_review=["Manually review this file."]
                ))
        else:
            # SQL / SQL DDL
            try:
                sql_objs = migrate_sql_file(src_obj.source_file, src_obj.source_text, ai_provider)
                # Set database/schema schema details if detected
                for o in sql_objs:
                    if src_obj.object_type == ObjectType.DATABASE:
                        o.database = src_obj.name
                    elif src_obj.object_type == ObjectType.SCHEMA:
                        o.schema = src_obj.name
                obj_list.extend(sql_objs)
            except Exception as exc:
                obj_list.append(MigrationObject(
                    object_name=src_obj.name, source_type=src_obj.object_type,
                    target_type="UNKNOWN", migration_type=MigrationType.HIGH_COMPLEXITY,
                    generated_code="", source_file=src_obj.source_file, confidence=0.0,
                    warnings=[str(exc)], manual_review=["Manually review this object."]
                ))

        for o in obj_list:
            if src_obj.name in circulars:
                o.warnings.append("CIRCULAR_DEPENDENCY")
                o.manual_review.append("Circular dependency detected involving this object; verify execution order.")
                o.validation_status = ValidationStatus.MANUAL_REVIEW
            o.source_object = src_obj.name
            o.source_hash = str(hash(src_obj.source_text))
            o.target_object = o.object_name
            o.strategy = o.conversion_strategy or "DIRECT_CONVERSION"
        
        objects.extend(obj_list)

    # Traceability dependencies mapping back to migration objects
    migrated_names = [o.object_name for o in objects]
    migrated_names_sorted = sorted(set(migrated_names), key=len, reverse=True)
    for obj in objects:
        seen = set()
        for name in migrated_names_sorted:
            if name == obj.object_name:
                continue
            if obj.generated_code and re.search(rf"\b{re.escape(name)}\b", obj.generated_code, re.IGNORECASE):
                if name not in seen:
                    obj.dependencies.append(name)
                    seen.add(name)
        # Find dependents
        for other in objects:
            if obj.object_name in other.dependencies:
                obj.dependents.append(other.object_name)

    objects = validate_all(objects)
    dependency_edges = build_dependency_graph(objects)
    report = MigrationReport(application_name=scan_result.application_name, objects=objects, dependency_edges=dependency_edges)
    _write_generated_project(objects, output_dir, root)
    return report


def _write_generated_project(objects: list[MigrationObject], output_dir: str, source_root: Path) -> None:
    out = Path(output_dir).resolve()
    project_dir = out / "databricks_project"
    
    # 24. Standardized generated files directory setup
    tables_conv = project_dir / "tables" / "convertible"
    tables_non_conv = project_dir / "tables" / "non_convertible"
    views_conv = project_dir / "views" / "convertible"
    views_non_conv = project_dir / "views" / "non_convertible"
    proc_conv = project_dir / "procedures" / "convertible"
    proc_non_conv = project_dir / "procedures" / "non_convertible"
    
    workflows_dir = project_dir / "workflows"
    app_dir = project_dir / "app"
    config_dir = project_dir / "config"
    review_dir = project_dir / "review"
    tests_dir = project_dir / "tests"

    for d in (tables_conv, tables_non_conv, views_conv, views_non_conv, proc_conv, proc_non_conv, workflows_dir, app_dir, config_dir, review_dir, tests_dir):
        d.mkdir(parents=True, exist_ok=True)

    bundle_name = out.name.replace("-", "_") or "snow2lake_migrated_app"
    (project_dir / "databricks.yml").write_text(
        "bundle:\n"
        f"  name: {bundle_name}\n\n"
        "include:\n  - workflows/*.yml\n\n"
        "targets:\n  dev:\n    mode: development\n",
        encoding="utf-8"
    )
    
    (workflows_dir / "jobs.yml").write_text(
        "resources:\n"
        "  jobs: {}\n\n"
        "# Add migrated Snowflake TASK -> Databricks Workflow definitions here.\n",
        encoding="utf-8"
    )

    # Copy source files into a clearly separated audit folder.
    source_copy = out / "source_snapshot"
    if source_root.exists():
        shutil.copytree(source_root, source_copy, dirs_exist_ok=True)

    # Dictionary to keep track of grouped objects for inventory generation
    inventory_data = {
        "tables": {"convertible": [], "non_convertible": []},
        "views": {"convertible": [], "non_convertible": []},
        "procedures": {"convertible": [], "non_convertible": []},
        "others": []
    }

    for obj in objects:
        safe = _safe_filename(obj.object_name)
        
        is_conv = (
            obj.migration_type in {MigrationType.AUTOMATED, MigrationType.AI_ASSISTED}
            and obj.validation_status not in {ValidationStatus.FAILED, ValidationStatus.REDESIGN_REQUIRED, ValidationStatus.MANUAL_REVIEW}
            and not any("circular" in w.lower() or "failed" in w.lower() for w in obj.warnings)
        )
        folder = "convertible" if is_conv else "non_convertible"
        
        if obj.source_type == ObjectType.TABLE:
            dest = (tables_conv if is_conv else tables_non_conv) / f"{safe}.sql"
            inventory_data["tables"][folder].append(obj)
        elif obj.source_type in {ObjectType.VIEW, ObjectType.SECURE_VIEW, ObjectType.MATERIALIZED_VIEW}:
            dest = (views_conv if is_conv else views_non_conv) / f"{safe}.sql"
            inventory_data["views"][folder].append(obj)
        elif obj.source_type in {ObjectType.STORED_PROCEDURE, ObjectType.UDF}:
            ext = ".py" if ("def " in (obj.generated_code or "") or "import " in (obj.generated_code or "") or obj.target_type in {"PYSPARK_FUNCTION", "DATABRICKS_APP_STREAMLIT"}) else ".sql"
            dest = (proc_conv if is_conv else proc_non_conv) / f"{safe}{ext}"
            inventory_data["procedures"][folder].append(obj)
        elif obj.source_type == ObjectType.STREAMLIT_APP:
            dest = app_dir / f"{safe}.py"
            inventory_data["others"].append(obj)
        elif obj.source_type == ObjectType.TASK:
            dest = workflows_dir / f"{safe}.yml"
            inventory_data["others"].append(obj)
        else:
            dest = review_dir / f"{safe}.sql"
            inventory_data["others"].append(obj)
            
        dest.write_text(obj.generated_code or "# No generated output; manual review required.\n", encoding="utf-8")
        obj.generated_file = str(dest.relative_to(out))
        obj.generated_files = [str(dest.relative_to(out))]

    # Generate object_inventory.md
    inventory_lines = [
        "# Databricks Project Object Inventory",
        "",
        "This file lists all migrated objects segregated by object group and convertibility status.",
        "",
    ]
    
    for category in ["tables", "views", "procedures"]:
        inventory_lines.append(f"## {category.capitalize()}")
        inventory_lines.append("")
        for status in ["convertible", "non_convertible"]:
            display_status = "Convertible (Automated/Direct)" if status == "convertible" else "Manual Review Required / Complex"
            emoji = "✅" if status == "convertible" else "⚠️"
            inventory_lines.append(f"### {emoji} {display_status}")
            items = inventory_data[category][status]
            if not items:
                inventory_lines.append("*No objects found in this group.*")
            else:
                for item in items:
                    details = []
                    if item.warnings:
                        details.append(f"Warnings: {', '.join(item.warnings)}")
                    if item.manual_review:
                        details.append(f"Manual Actions: {', '.join(item.manual_review)}")
                    details_str = f" - ({'; '.join(details)})" if details else ""
                    inventory_lines.append(f"- **{item.object_name}** (Target: `{item.target_type}`){details_str}")
            inventory_lines.append("")
            
    if inventory_data["others"]:
        inventory_lines.append("## Other App Objects (Workflows, Configs, Apps)")
        inventory_lines.append("")
        for item in inventory_data["others"]:
            inventory_lines.append(f"- **{item.object_name}** (`{item.source_type.value}` -> `{item.target_type}`)")
        inventory_lines.append("")

    (project_dir / "object_inventory.md").write_text("\n".join(inventory_lines), encoding="utf-8")

    # Generate databricks_app_requirements.md
    app_req_content = """# Creating and Deploying Apps in Databricks vs. Snowflake

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
"""
    (project_dir / "databricks_app_requirements.md").write_text(app_req_content, encoding="utf-8")


def _safe_filename(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)[:100] or "object"

