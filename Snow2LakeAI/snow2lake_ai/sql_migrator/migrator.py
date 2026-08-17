"""
Deterministic SQL / DDL migration engine (spec section #7, #31).

Uses sqlglot to parse Snowflake SQL into an AST rather than regex, and
transpiles it to the Databricks dialect. Snowflake constructs with no
direct Databricks equivalent (SECURE VIEW, MATERIALIZED VIEW refresh
semantics, STREAM, TASK, STAGE) are intercepted *before* naive
transpilation and routed to dedicated logic instead of being silently
passed through or mistranslated.
"""

from __future__ import annotations

import re

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from snow2lake_ai.ai.provider import AIProvider
from snow2lake_ai.ai.agentic_pipeline import AgenticPipeline
from snow2lake_ai.models import MigrationObject, MigrationType, ObjectType, ValidationStatus, ClassificationState
from snow2lake_ai.sql_migrator.mappings import SPECIAL_CONSTRUCTS
from snow2lake_ai.sql_migrator.strategies import (
    DatabaseMigration,
    SchemaMigration,
    TableMigration,
    ViewMigration,
    SecureViewMigration,
    MaterializedViewMigration,
    StreamMigration,
    TaskMigration,
    StageMigration,
    FileFormatMigration,
    PermissionMigration
)

READ_DIALECT = "snowflake"
WRITE_DIALECT = "databricks"

# Module-level counter for unique statement IDs (prevents duplicate object_name collisions)
import itertools as _itertools
_STMT_COUNTER = _itertools.count(1)

def _object_name(create_expr: exp.Create) -> str:
    this = create_expr.this
    if isinstance(this, exp.Schema):
        this = this.this
    try:
        return this.name if hasattr(this, "name") else str(this)
    except Exception:
        return str(this)


def _has_property(create_expr: exp.Create, prop_type) -> bool:
    props = create_expr.args.get("properties")
    if not props:
        return False
    return any(isinstance(p, prop_type) for p in props.expressions)


def _references_current_role(sql_text: str) -> bool:
    return "CURRENT_ROLE(" in sql_text.upper()


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


def migrate_sql_file(path: str, sql_text: str, ai_provider: AIProvider | None = None) -> list[MigrationObject]:
    """Parse a .sql file into individual statements and migrate each one
    independently, so one bad statement doesn't block the rest."""
    results: list[MigrationObject] = []

    raw_stmts = split_sql_statements(sql_text)
    for raw_stmt in raw_stmts:
        try:
            statements = sqlglot.parse(raw_stmt, read=READ_DIALECT)
            for stmt in statements:
                if stmt is None:
                    continue
                obj = _migrate_statement(stmt, path, ai_provider)
                if obj is not None:
                    results.append(obj)
        except Exception as exc:
            # Fallback instead of failing
            stmt = exp.Command(this="RAW_SQL", expression=exp.Literal.string(raw_stmt))
            obj = _migrate_statement(stmt, path, ai_provider)
            if obj is not None:
                obj.migration_type = MigrationType.HIGH_COMPLEXITY
                obj.classification_state = ClassificationState.MANUAL_REVIEW
                obj.warnings.append(f"SQL parse failed: {exc}")
                obj.manual_review.append("Manually review and migrate this statement; parser could not build an AST.")
                results.append(obj)

    return results


def _migrate_statement(stmt: exp.Expression, path: str, ai_provider: AIProvider | None) -> MigrationObject | None:
    if isinstance(stmt, exp.Command) and str(stmt.this).upper() == "RAW_SQL":
        # Fallback parse failure from split_sql_statements; extract original string
        raw_text = stmt.expression.name if hasattr(stmt, "expression") else str(stmt)
    else:
        raw_text = stmt.sql(dialect=READ_DIALECT) if hasattr(stmt, "sql") else str(stmt)
        
    # Strip leading SQL comments for reliable prefix matching
    clean_text = raw_text.lstrip()
    while clean_text.startswith("--") or clean_text.startswith("/*"):
        if clean_text.startswith("--"):
            clean_text = clean_text.split("\n", 1)[1].lstrip() if "\n" in clean_text else ""
        elif clean_text.startswith("/*"):
            clean_text = clean_text.split("*/", 1)[1].lstrip() if "*/" in clean_text else ""
            
    raw_upper = clean_text.upper()

    # ── Cortex AI functions ──────────────────────────────────────────────────
    if "SNOWFLAKE.CORTEX" in raw_upper:
        from snow2lake_ai.sql_migrator.cortex_analyzer import CortexAnalyzer
        analysis = CortexAnalyzer.analyze_sql(raw_text)
        if analysis:
            sec_notes = [
                f"Snowflake Cortex function:\n{analysis.cortex_function}\n",
                f"Databricks replacement:\n{analysis.target_capability}\n",
                f"Confidence:\n{analysis.confidence}"
            ]
            return MigrationObject(
                object_name=f"CORTEX_{analysis.cortex_function}",
                source_type=ObjectType.UNKNOWN,
                target_type=analysis.target_capability,
                migration_type=MigrationType.ARCHITECTURE_REDESIGN if analysis.classification_state == "ARCHITECTURE_REDESIGN" else (MigrationType.AUTOMATED if analysis.classification_state == "DIRECT" else MigrationType.HIGH_COMPLEXITY),
                generated_code=analysis.suggested_code,
                source_file=path,
                script_percentage=50,
                manual_percentage=50,
                confidence=analysis.confidence,
                security_notes=sec_notes,
                manual_review=[f"Verify Foundation Model endpoint connection and verify query syntax for {analysis.cortex_function}."],
                conversion_strategy=f"Map Cortex function {analysis.cortex_function} to Databricks model endpoint",
                classification_state=analysis.classification_state,
                validation_status=ValidationStatus.GENERATED
            )

    # ── Noise / boilerplate: skip from report entirely ──────────────────────
    # GRANT … TO APPLICATION ROLE  (Snowflake Native App permission boilerplate)
    # USE ROLE / USE WAREHOUSE / USE DATABASE / USE SCHEMA
    # SET / UNSET variable
    # INSERT INTO … SELECT … WHERE NOT EXISTS (idempotent seed data)
    _SKIP_PREFIXES = (
        "GRANT USAGE ON", "GRANT SELECT ON", "GRANT ALL ON",
        "GRANT USAGE ON SCHEMA", "GRANT USAGE ON PROCEDURE",
        "USE ROLE", "USE WAREHOUSE", "USE DATABASE", "USE SCHEMA",
        "SET ", "UNSET ", "--", "/*"
    )
    if any(raw_upper.startswith(p) for p in _SKIP_PREFIXES):
        return None  # Skip — permission boilerplate, not a migratable object

    # INSERT seed data — surface as DML but skip if it is a common idempotent seed
    if isinstance(stmt, (exp.Insert, exp.Update, exp.Delete, exp.Merge)):
        return _migrate_dml(stmt, path)

    # ── Proper sqlglot-parsed CREATE statements ──────────────────────────────
    if isinstance(stmt, exp.Create):
        return _migrate_create(stmt, path, ai_provider)

    # ── DROP statements ──────────────────────────────────────────────────────
    if isinstance(stmt, exp.Drop):
        return None  # DROP is noise in the migration context — not a target object

    # ── GRANT statements (remaining — not boilerplate, e.g. EXECUTE) ────────
    if isinstance(stmt, exp.Grant):
        return PermissionMigration.migrate(stmt, path, ai_provider)

    # ── exp.Command — sqlglot could not parse this under Snowflake dialect ───
    if isinstance(stmt, exp.Command):

        # Snowflake Native App boilerplate that sqlglot can't parse:
        # CREATE APPLICATION ROLE / CREATE OR ALTER VERSIONED SCHEMA
        if re.search(r"\bCREATE\b.*\bAPPLICATION\s+ROLE\b", raw_text, re.IGNORECASE):
            name_match = re.search(r"APPLICATION\s+ROLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z0-9_.]+)", raw_text, re.IGNORECASE)
            role_name = name_match.group(1) if name_match else f"app_role_{next(_STMT_COUNTER)}"
            return MigrationObject(
                object_name=f"APP_ROLE.{role_name}",
                source_type=ObjectType.GRANT,
                target_type="DATABRICKS_GROUP",
                migration_type=MigrationType.ARCHITECTURE_REDESIGN,
                generated_code=(
                    f"-- Snowflake APPLICATION ROLE '{role_name}' -> Databricks Group / Entitlement\n"
                    f"-- In Databricks Apps, use workspace groups or service principals.\n"
                    f"-- Original: {raw_text[:200]}\n"
                ),
                source_file=path,
                script_percentage=0, ai_percentage=0, manual_percentage=100,
                confidence=0.5,
                manual_review=["Map APPLICATION ROLE to a Databricks workspace group or entitlement via Unity Catalog."],
                conversion_strategy="APPLICATION ROLE -> Databricks Group/Entitlement",
                validation_status=ValidationStatus.REDESIGN_REQUIRED,
            )

        if re.search(r"\bCREATE\b.*\bVERSIONED\s+SCHEMA\b", raw_text, re.IGNORECASE):
            name_match = re.search(r"SCHEMA\s+([A-Za-z0-9_.]+)", raw_text, re.IGNORECASE)
            schema_name = name_match.group(1) if name_match else f"schema_{next(_STMT_COUNTER)}"
            return MigrationObject(
                object_name=f"VERSIONED_SCHEMA.{schema_name}",
                source_type=ObjectType.SCHEMA,
                target_type="DATABRICKS_SCHEMA",
                migration_type=MigrationType.AI_ASSISTED,
                generated_code=f"CREATE SCHEMA IF NOT EXISTS {schema_name};\n-- Note: Databricks does not have versioned schemas. Schema versioning is handled via Delta table versions.",
                source_file=path,
                script_percentage=70, ai_percentage=20, manual_percentage=10,
                confidence=0.8,
                manual_review=["Snowflake VERSIONED SCHEMA has no direct Databricks equivalent. Delta Lake provides table-level versioning."],
                conversion_strategy="VERSIONED SCHEMA -> Databricks Schema (Delta versioning)",
                validation_status=ValidationStatus.GENERATED,
            )

        # Known Snowflake-specific objects: STREAM, TASK, STAGE, FILE FORMAT
        for keyword in ("STREAM", "TASK", "STAGE", "FILE FORMAT"):
            pattern_keyword = keyword.replace(' ', r'\s+')
            if re.search(rf"\bCREATE\b.*\b{pattern_keyword}\b", raw_text, re.IGNORECASE):
                name_match = re.search(rf"{pattern_keyword}\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z0-9_.\"]+)", raw_text, re.IGNORECASE)
                extracted_name = name_match.group(1) if name_match else f"{keyword}_{next(_STMT_COUNTER)}"
                
                obj = None
                if keyword == "STREAM":
                    obj = StreamMigration.migrate(stmt, path, ai_provider)
                elif keyword == "TASK":
                    obj = TaskMigration.migrate(stmt, path, ai_provider)
                elif keyword == "STAGE":
                    obj = StageMigration.migrate(stmt, path, ai_provider)
                elif keyword == "FILE FORMAT":
                    obj = FileFormatMigration.migrate(stmt, path, ai_provider)
                    
                if obj and obj.object_name == "RAW_SQL":
                    obj.object_name = extracted_name
                    
                return obj

        # Procedure defined inside a Command node (sqlglot failed to parse it as exp.Create)
        if re.search(r"\bCREATE\b.*\bPROCEDURE\b", raw_text, re.IGNORECASE):
            if ai_provider is not None:
                return _migrate_procedure_with_ai(raw_text, path, ai_provider)
            # No AI — surface as HIGH_COMPLEXITY
            name_match = re.search(r"PROCEDURE\s+([A-Za-z0-9_.]+)", raw_text, re.IGNORECASE)
            proc_name = name_match.group(1) if name_match else f"procedure_{next(_STMT_COUNTER)}"
            return MigrationObject(
                object_name=proc_name,
                source_type=ObjectType.STORED_PROCEDURE,
                target_type="DATABRICKS_SQL_PROCEDURE",
                migration_type=MigrationType.HIGH_COMPLEXITY,
                generated_code=f"-- Manual migration required (no AI configured).\n-- Original:\n" + "\n".join(f"-- {l}" for l in raw_text.splitlines()),
                source_file=path,
                script_percentage=20, ai_percentage=0, manual_percentage=80,
                confidence=0.2,
                manual_review=["Connect Databricks AI to enable automatic procedure migration."],
                classification_state=ClassificationState.MANUAL_REVIEW,
                validation_status=ValidationStatus.MANUAL_REVIEW,
            )

        # CALL statements — keep them to show what procedures are invoked
        if raw_upper.startswith("CALL "):
            idx = next(_STMT_COUNTER)
            call_match = re.search(r"CALL\s+([A-Za-z0-9_.]+)", raw_text, re.IGNORECASE)
            call_name = call_match.group(1) if call_match else f"call_{idx}"
            return MigrationObject(
                object_name=f"CALL.{call_name}",
                source_type=ObjectType.UNKNOWN,
                target_type="DATABRICKS_SQL",
                migration_type=MigrationType.AI_ASSISTED,
                generated_code=f"CALL {call_name}();  -- Verify argument types match Databricks procedure signature.",
                source_file=path,
                script_percentage=80, ai_percentage=10, manual_percentage=10,
                confidence=0.75,
                manual_review=["Verify CALL statement arguments are compatible with the Databricks procedure."],
                conversion_strategy="CALL -> Databricks CALL",
                validation_status=ValidationStatus.GENERATED,
            )

        # Truly unrecognized — skip noise (ALTER SESSION, USE, etc.)
        # Only surface if it looks like a CREATE for something we missed
        if re.search(r"\bCREATE\b", clean_text, re.IGNORECASE):
            idx = next(_STMT_COUNTER)
            name_match = re.search(r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_]+)", clean_text, re.IGNORECASE)
            first_kw = name_match.group(1).upper() if name_match else "UNKNOWN"
            return _migrate_passthrough(stmt, path, ObjectType.UNKNOWN, f"CREATE_{first_kw}_{idx}")

        # Everything else (ALTER SESSION, etc.) — skip
        return None

    # Any other sqlglot node type — surface but don't clutter
    return None



def _migrate_create(stmt: exp.Create, path: str, ai_provider: AIProvider | None = None) -> MigrationObject:
    kind = (stmt.args.get("kind") or "").upper()
    is_secure = _has_property(stmt, exp.SecureProperty)
    is_materialized = _has_property(stmt, exp.MaterializedProperty)

    if kind == "DATABASE":
        return DatabaseMigration.migrate(stmt, path, ai_provider)
    elif kind == "SCHEMA":
        return SchemaMigration.migrate(stmt, path, ai_provider)
    elif kind == "TABLE":
        return TableMigration.migrate(stmt, path, ai_provider)
    elif kind == "VIEW":
        if is_secure:
            return SecureViewMigration.migrate(stmt, path, ai_provider)
        elif is_materialized:
            return MaterializedViewMigration.migrate(stmt, path, ai_provider)
        return ViewMigration.migrate(stmt, path, ai_provider)
    elif kind == "STREAM":
        return StreamMigration.migrate(stmt, path, ai_provider)
    elif kind == "TASK":
        return TaskMigration.migrate(stmt, path, ai_provider)
    elif kind == "STAGE":
        return StageMigration.migrate(stmt, path, ai_provider)
    elif kind == "FILE FORMAT":
        return FileFormatMigration.migrate(stmt, path, ai_provider)

    name = _object_name(stmt)
    source_sql = stmt.sql(dialect=READ_DIALECT)
    return _migrate_transpilable(stmt, path, source_sql, kind, name)


def _migrate_transpilable(stmt: exp.Create, path: str, source_sql: str, kind: str, name: str) -> MigrationObject:
    try:
        target_sql = stmt.sql(dialect=WRITE_DIALECT, pretty=True)
        confidence = 0.95
        warnings: list[str] = []
    except Exception as exc:
        target_sql = f"-- TRANSPILE FAILED: {exc}\n{source_sql}"
        confidence = 0.3
        warnings = [f"Transpilation to Databricks dialect failed: {exc}"]

    object_type_map = {
        "TABLE": ObjectType.TABLE,
        "VIEW": ObjectType.VIEW,
        "DATABASE": ObjectType.DATABASE,
        "SCHEMA": ObjectType.SCHEMA,
    }
    obj_type = object_type_map.get(kind, ObjectType.UNKNOWN)

    changes = []
    if kind == "TABLE":
        changes.append("Snowflake column types mapped to Delta Lake / Spark SQL types.")

    return MigrationObject(
        object_name=name or f"{kind}_{path}",
        source_type=obj_type,
        target_type=f"DATABRICKS_{kind}",
        migration_type=MigrationType.AUTOMATED,
        generated_code=target_sql,
        source_file=path,
        script_percentage=100,
        ai_percentage=0,
        manual_percentage=0,
        confidence=confidence,
        changes_required=changes,
        warnings=warnings,
    )


def _migrate_materialized_view(stmt: exp.Create, path: str, source_sql: str, name: str) -> MigrationObject:
    try:
        target_sql = stmt.sql(dialect=WRITE_DIALECT, pretty=True)
    except Exception as exc:
        target_sql = f"-- TRANSPILE FAILED: {exc}\n{source_sql}"

    return MigrationObject(
        object_name=name,
        source_type=ObjectType.MATERIALIZED_VIEW,
        target_type="DATABRICKS_MATERIALIZED_VIEW",
        migration_type=MigrationType.AI_ASSISTED,
        generated_code=target_sql,
        source_file=path,
        script_percentage=70,
        ai_percentage=20,
        manual_percentage=10,
        confidence=0.6,
        changes_required=[
            "Query body transpiled to Databricks SQL.",
            "Refresh semantics differ from Snowflake (target: Databricks Materialized View "
            "with a defined refresh schedule, or a Delta Live Tables pipeline).",
        ],
        warnings=[SPECIAL_CONSTRUCTS["MATERIALIZED VIEW"]],
        manual_review=["Confirm refresh schedule / staleness tolerance matches business requirement."],
    )


def _migrate_unsupported_object(kind: str, name: str, path: str, source_sql: str) -> MigrationObject:
    target_map = {
        "STREAM": ("Delta Change Data Feed", ObjectType.STREAM),
        "TASK": ("Databricks Workflow / Job", ObjectType.TASK),
        "STAGE": ("Unity Catalog Volume / External Location", ObjectType.STAGE),
        "FILE FORMAT": ("Databricks file format options on COPY INTO / Auto Loader", ObjectType.FILE_FORMAT),
    }
    target_desc, obj_type = target_map.get(kind, ("Architecture redesign required", ObjectType.UNKNOWN))
    return MigrationObject(
        object_name=name or f"{kind}_{path}",
        source_type=obj_type,
        target_type=target_desc,
        migration_type=MigrationType.ARCHITECTURE_REDESIGN,
        generated_code=f"-- Original Snowflake {kind}:\n-- {source_sql}\n-- Target architecture: {target_desc}\n"
                        f"-- (no direct DDL transpile; see migration report for recommended implementation)",
        source_file=path,
        script_percentage=20,
        ai_percentage=50,
        manual_percentage=30,
        confidence=0.5,
        warnings=[SPECIAL_CONSTRUCTS.get(kind, f"{kind} has no direct Databricks DDL equivalent.")],
        manual_review=[f"Design the {target_desc} implementation for '{name}'."],
    )


def _migrate_dml(stmt: exp.Expression, path: str) -> MigrationObject:
    source_sql = stmt.sql(dialect=READ_DIALECT)
    kind_name = type(stmt).__name__.upper()
    try:
        target_sql = stmt.sql(dialect=WRITE_DIALECT, pretty=True)
        confidence = 0.9
        warnings = []
    except Exception as exc:
        target_sql = f"-- TRANSPILE FAILED: {exc}\n{source_sql}"
        confidence = 0.3
        warnings = [f"Transpilation failed: {exc}"]

    return MigrationObject(
        object_name=f"{kind_name}_{path}",
        source_type=ObjectType.DML_STATEMENT,
        target_type=f"DATABRICKS_SQL_{kind_name}",
        migration_type=MigrationType.AUTOMATED,
        generated_code=target_sql,
        source_file=path,
        script_percentage=100,
        confidence=confidence,
        warnings=warnings,
    )


def _migrate_passthrough(stmt: exp.Expression, path: str, obj_type: ObjectType, label: str) -> MigrationObject:
    source_sql = stmt.sql(dialect=READ_DIALECT)
    try:
        target_sql = stmt.sql(dialect=WRITE_DIALECT, pretty=True)
        confidence = 0.7
    except Exception:
        target_sql = source_sql
        confidence = 0.4
    return MigrationObject(
        object_name=label,  # caller is responsible for uniqueness
        source_type=obj_type,
        target_type="DATABRICKS_SQL",
        migration_type=MigrationType.AI_ASSISTED,
        generated_code=target_sql,
        source_file=path,
        script_percentage=60,
        ai_percentage=20,
        manual_percentage=20,
        confidence=confidence,
        manual_review=[f"Confirm '{label}' statement was translated with correct semantics."],
    )


def _migrate_procedure_with_ai(source_sql: str, path: str, ai_provider: AIProvider) -> MigrationObject:
    """
    Route SQL stored procedures through the three-agent agentic pipeline:
      Agent 1 — TranslationAgent  : generates Databricks SQL / PySpark.
      Agent 2 — ValidationAgent   : validates syntax and runs live EXPLAIN
                                    dry-run if a warehouse is connected.
      Agent 3 — GuardrailAgent    : scans for performance anti-patterns.
    The pipeline self-corrects up to MAX_RETRIES times before falling back
    to a HIGH_COMPLEXITY manual-review object.
    """
    name_match = re.search(r"PROCEDURE\s+([A-Za-z0-9_.]+)", source_sql, re.IGNORECASE)
    name = name_match.group(1) if name_match else f"PROCEDURE_{path}"

    pipeline = AgenticPipeline(ai_provider=ai_provider)
    return pipeline.run(
        object_name=name,
        source_type=ObjectType.STORED_PROCEDURE,
        source_code=source_sql,
        source_file=path,
        context={
            "hint": (
                "Translate to Databricks SQL procedure using DECLARE/BEGIN/END. "
                "If LANGUAGE PYTHON is involved, generate a PySpark function instead. "
                "Replace IFF->IF, ILIKE->LIKE, @stage->Unity Catalog Volume path."
            )
        },
    )
