"""
Object-specific migration strategies hierarchy (spec sections #1, #2, #3, #4, #5, #6, #7, #8).
"""

from __future__ import annotations
import re
from typing import Any
import sqlglot
from sqlglot import exp
from snow2lake_ai.models import MigrationObject, MigrationType, ObjectType, ValidationStatus, ClassificationState
from snow2lake_ai.ai.provider import AIProvider

READ_DIALECT = "snowflake"
WRITE_DIALECT = "databricks"

def transform_datatype(node: exp.Expression) -> exp.Expression:
    if isinstance(node, exp.DataType):
        typename = node.this
        if typename == exp.DataType.Type.DECIMAL:
            params = node.expressions
            if not params:
                return exp.DataType.build("BIGINT")
            elif len(params) == 1:
                return exp.DataType.build(f"DECIMAL({params[0]})")
            elif len(params) == 2:
                if str(params[1]) == "0":
                    try:
                        prec = int(str(params[0]))
                        if prec <= 9:
                            return exp.DataType.build("INT")
                        return exp.DataType.build("BIGINT")
                    except ValueError:
                        pass
                return exp.DataType.build(f"DECIMAL({params[0]}, {params[1]})")
        elif typename in (exp.DataType.Type.VARCHAR, exp.DataType.Type.CHAR, exp.DataType.Type.TEXT):
            return exp.DataType.build("STRING")
        elif typename == exp.DataType.Type.VARIANT:
            return exp.DataType.build("STRING")
        elif typename == exp.DataType.Type.OBJECT:
            return exp.DataType.build("MAP<STRING, STRING>")
        elif typename == exp.DataType.Type.ARRAY:
            return exp.DataType.build("ARRAY<STRING>")
        elif typename in (exp.DataType.Type.TIMESTAMPNTZ, exp.DataType.Type.TIMESTAMPLTZ, exp.DataType.Type.TIMESTAMPTZ):
            return exp.DataType.build("TIMESTAMP")
        elif typename == exp.DataType.Type.TIME:
            return exp.DataType.build("STRING")
    return node


class ObjectMigrationStrategy:
    @staticmethod
    def migrate(stmt: exp.Expression, path: str, ai_provider: AIProvider | None = None) -> MigrationObject:
        raise NotImplementedError()


# ============================================================
# 1. SQL OBJECT STRATEGIES
# ============================================================

class SqlObjectStrategy(ObjectMigrationStrategy):
    pass


class DatabaseMigration(SqlObjectStrategy):
    @staticmethod
    def migrate(stmt: exp.Expression, path: str, ai_provider: AIProvider | None = None) -> MigrationObject:
        name = stmt.this.name if hasattr(stmt.this, "name") else str(stmt.this)
        target_sql = f"CREATE SCHEMA IF NOT EXISTS {name};"
        return MigrationObject(
            object_name=name,
            source_type=ObjectType.DATABASE,
            target_type="DATABRICKS_CATALOG",
            migration_type=MigrationType.AUTOMATED,
            generated_code=target_sql,
            source_file=path,
            script_percentage=100,
            confidence=0.95,
            database=name,
            conversion_strategy="Create schema representing catalog",
            classification_state=ClassificationState.DIRECT,
            validation_status=ValidationStatus.GENERATED
        )


class SchemaMigration(SqlObjectStrategy):
    @staticmethod
    def migrate(stmt: exp.Expression, path: str, ai_provider: AIProvider | None = None) -> MigrationObject:
        name = stmt.this.name if hasattr(stmt.this, "name") else str(stmt.this)
        target_sql = f"CREATE SCHEMA IF NOT EXISTS {name};"
        return MigrationObject(
            object_name=name,
            source_type=ObjectType.SCHEMA,
            target_type="DATABRICKS_SCHEMA",
            migration_type=MigrationType.AUTOMATED,
            generated_code=target_sql,
            source_file=path,
            script_percentage=100,
            confidence=0.95,
            schema=name,
            conversion_strategy="Create schema in Databricks",
            classification_state=ClassificationState.DIRECT,
            validation_status=ValidationStatus.GENERATED
        )


class TableMigration(SqlObjectStrategy):
    @staticmethod
    def migrate(stmt: exp.Expression, path: str, ai_provider: AIProvider | None = None) -> MigrationObject:
        source_sql = stmt.sql(dialect=READ_DIALECT)
        transformed_stmt = stmt.transform(transform_datatype)
        name = transformed_stmt.this.this.name if hasattr(transformed_stmt.this, "this") and hasattr(transformed_stmt.this.this, "name") else str(transformed_stmt.this)
        try:
            target_sql = transformed_stmt.sql(dialect=WRITE_DIALECT, pretty=True)
            status = ValidationStatus.GENERATED
            warnings = []
        except Exception as e:
            target_sql = f"-- Transpile failed: {e}\n{source_sql}"
            status = ValidationStatus.FAILED
            warnings = [str(e)]
            
        return MigrationObject(
            object_name=name,
            source_type=ObjectType.TABLE,
            target_type="DATABRICKS_TABLE",
            migration_type=MigrationType.AUTOMATED,
            generated_code=target_sql,
            source_file=path,
            script_percentage=100,
            confidence=0.9,
            conversion_strategy="Type mapped SQL transpilation to Delta Lake",
            classification_state=ClassificationState.DIRECT,
            validation_status=status,
            warnings=warnings
        )


class ViewMigration(SqlObjectStrategy):
    @staticmethod
    def migrate(stmt: exp.Expression, path: str, ai_provider: AIProvider | None = None) -> MigrationObject:
        source_sql = stmt.sql(dialect=READ_DIALECT)
        name = stmt.this.this.name if hasattr(stmt.this, "this") and hasattr(stmt.this.this, "name") else str(stmt.this)
        try:
            target_sql = stmt.sql(dialect=WRITE_DIALECT, pretty=True)
            status = ValidationStatus.GENERATED
            warnings = []
        except Exception as e:
            target_sql = f"-- Transpile failed: {e}\n{source_sql}"
            status = ValidationStatus.FAILED
            warnings = [str(e)]
            
        return MigrationObject(
            object_name=name,
            source_type=ObjectType.VIEW,
            target_type="DATABRICKS_VIEW",
            migration_type=MigrationType.AUTOMATED,
            generated_code=target_sql,
            source_file=path,
            script_percentage=100,
            confidence=0.9,
            conversion_strategy="Transpiled select logic view mapping",
            classification_state=ClassificationState.DIRECT,
            validation_status=status,
            warnings=warnings
        )


class SecureViewMigration(SqlObjectStrategy):
    @staticmethod
    def migrate(stmt: exp.Expression, path: str, ai_provider: AIProvider | None = None) -> MigrationObject:
        source_sql = stmt.sql(dialect=READ_DIALECT)
        name = stmt.this.this.name if hasattr(stmt.this, "this") and hasattr(stmt.this.this, "name") else str(stmt.this)
        
        security_features = []
        preservation = "YES"
        upper_sql = source_sql.upper()
        
        if "CURRENT_ROLE(" in upper_sql:
            security_features.append("CURRENT_ROLE() authorization filter")
            preservation = "PARTIAL"
        if "CURRENT_USER(" in upper_sql:
            security_features.append("CURRENT_USER() authorization filter")
            preservation = "YES"
        if "IS_ROLE_IN_SESSION(" in upper_sql:
            security_features.append("IS_ROLE_IN_SESSION() dynamic policy check")
            preservation = "PARTIAL"
        if "MASKING POLICY" in upper_sql or "ROW ACCESS POLICY" in upper_sql:
            security_features.append("Snowflake Row/Column Policy association")
            preservation = "NO"
            
        target_sql = stmt.sql(dialect=WRITE_DIALECT, pretty=True)
        target_sql = target_sql.replace("CREATE SECURE VIEW", "CREATE VIEW")
        
        sec_notes = [
            f"Snowflake Security Features: {', '.join(security_features) if security_features else 'Plain Secure View metadata restriction'}.",
            f"Databricks Row/Column filter mapping target behavior: {preservation} preservation claim.",
            "Action Required: Verify row-level filters and group/role permissions mapping in Unity Catalog."
        ]
        
        class_state = ClassificationState.MANUAL_REVIEW if preservation in ("PARTIAL", "NO") else ClassificationState.DIRECT
        
        return MigrationObject(
            object_name=name,
            source_type=ObjectType.SECURE_VIEW,
            target_type="DATABRICKS_SECURE_VIEW",
            migration_type=MigrationType.ARCHITECTURE_REDESIGN,
            generated_code=target_sql,
            source_file=path,
            script_percentage=80,
            manual_percentage=20,
            confidence=0.8,
            security_features=security_features,
            security_notes=sec_notes,
            security_preservation=preservation,
            manual_review=["Verify Unity Catalog row-level filters and table policies are set correctly for user groups."],
            conversion_strategy="Row/Column filter mapping on Unity Catalog Views",
            classification_state=class_state,
            validation_status=ValidationStatus.GENERATED
        )


class MaterializedViewMigration(SqlObjectStrategy):
    @staticmethod
    def migrate(stmt: exp.Expression, path: str, ai_provider: AIProvider | None = None) -> MigrationObject:
        source_sql = stmt.sql(dialect=READ_DIALECT)
        name = stmt.this.this.name if hasattr(stmt.this, "this") and hasattr(stmt.this.this, "name") else str(stmt.this)
        
        target_sql = stmt.sql(dialect=WRITE_DIALECT, pretty=True)
        
        # Analyze Materialized view queries
        # If it has joins or complex subqueries not supported by Databricks MV natively:
        class_state = ClassificationState.AI_ASSISTED
        decision = "Databricks Materialized View or scheduled pipeline"
        if "JOIN " in source_sql.upper() or "UNION " in source_sql.upper():
            class_state = ClassificationState.ARCHITECTURE_REDESIGN
            decision = "Redesign refresh using DLT Pipeline / Databricks Jobs (materialized views do not support arbitrary joins natively)"
            
        return MigrationObject(
            object_name=name,
            source_type=ObjectType.MATERIALIZED_VIEW,
            target_type="DATABRICKS_MATERIALIZED_VIEW",
            migration_type=MigrationType.AI_ASSISTED,
            generated_code=target_sql,
            source_file=path,
            script_percentage=60,
            manual_percentage=40,
            confidence=0.7,
            conversion_strategy=decision,
            warnings=["Databricks materialized views refresh logic is managed via workflows or DLT Pipelines."],
            manual_review=["Set schedule/staleness parameters and verify UC refresh credentials."],
            classification_state=class_state,
            validation_status=ValidationStatus.GENERATED
        )


class FunctionMigration(SqlObjectStrategy):
    @staticmethod
    def migrate(stmt: exp.Expression, path: str, ai_provider: AIProvider | None = None) -> MigrationObject:
        source_sql = stmt.sql(dialect=READ_DIALECT)
        name = stmt.this.this.name if hasattr(stmt.this, "this") and hasattr(stmt.this.this, "name") else str(stmt.this)
        try:
            target_sql = stmt.sql(dialect=WRITE_DIALECT, pretty=True)
            status = ValidationStatus.GENERATED
        except Exception as e:
            target_sql = f"-- Transpile failed: {e}\n{source_sql}"
            status = ValidationStatus.FAILED
            
        return MigrationObject(
            object_name=name,
            source_type=ObjectType.UDF,
            target_type="DATABRICKS_UDF",
            migration_type=MigrationType.AUTOMATED,
            generated_code=target_sql,
            source_file=path,
            script_percentage=100,
            confidence=0.9,
            conversion_strategy="SQL Function Transpilation",
            classification_state=ClassificationState.DIRECT,
            validation_status=status
        )


# ============================================================
# 2. PYTHON OBJECT STRATEGIES
# ============================================================

class PythonObjectStrategy(ObjectMigrationStrategy):
    pass


class PythonFunctionMigration(PythonObjectStrategy):
    @staticmethod
    def migrate(stmt: exp.Expression, path: str, ai_provider: AIProvider | None = None) -> MigrationObject:
        raw_text = stmt.sql(dialect=READ_DIALECT) if hasattr(stmt, "sql") else str(stmt)
        return MigrationObject(
            object_name=f"FUNC_{path}",
            source_type=ObjectType.UDF,
            target_type="DATABRICKS_UDF_PYTHON",
            migration_type=MigrationType.AI_ASSISTED,
            generated_code=raw_text,
            source_file=path,
            script_percentage=40,
            ai_percentage=60,
            confidence=0.7,
            conversion_strategy="Python UDF Translation",
            classification_state=ClassificationState.AI_ASSISTED,
            validation_status=ValidationStatus.GENERATED
        )


class PythonProcedureMigration(PythonObjectStrategy):
    @staticmethod
    def migrate(stmt: exp.Expression, path: str, ai_provider: AIProvider | None = None) -> MigrationObject:
        raw_text = stmt.sql(dialect=READ_DIALECT) if hasattr(stmt, "sql") else str(stmt)
        # Check collect()/toPandas() driver-side loops anti-pattern
        warnings = []
        manual_review = []
        class_state = ClassificationState.AI_ASSISTED
        
        if "collect(" in raw_text.lower() or "toPandas(" in raw_text.lower():
            warnings.append("COLLECT_LOOP")
            manual_review.append("Driver-side row iteration pattern detected. Redesign to Spark transformations.")
            class_state = ClassificationState.MANUAL_REVIEW
            
        return MigrationObject(
            object_name=f"PROC_{path}",
            source_type=ObjectType.STORED_PROCEDURE,
            target_type="DATABRICKS_SPARK_PROCEDURE",
            migration_type=MigrationType.AI_ASSISTED,
            generated_code=raw_text,
            source_file=path,
            script_percentage=30,
            ai_percentage=70,
            confidence=0.6,
            warnings=warnings,
            manual_review=manual_review,
            conversion_strategy="Python Stored Procedure Translation",
            classification_state=class_state,
            validation_status=ValidationStatus.GENERATED
        )


class SnowparkProcedureMigration(PythonObjectStrategy):
    @staticmethod
    def migrate(stmt: exp.Expression, path: str, ai_provider: AIProvider | None = None) -> MigrationObject:
        raw_text = stmt.sql(dialect=READ_DIALECT) if hasattr(stmt, "sql") else str(stmt)
        return MigrationObject(
            object_name=f"SNOWPARK_{path}",
            source_type=ObjectType.STORED_PROCEDURE,
            target_type="DATABRICKS_PYSPARK",
            migration_type=MigrationType.ARCHITECTURE_REDESIGN,
            generated_code=raw_text,
            source_file=path,
            script_percentage=20,
            ai_percentage=80,
            confidence=0.5,
            conversion_strategy="Snowpark API to PySpark translation mapping",
            classification_state=ClassificationState.ARCHITECTURE_REDESIGN,
            validation_status=ValidationStatus.GENERATED
        )


# ============================================================
# 3. CDC STRATEGY
# ============================================================

class CDCStrategy(ObjectMigrationStrategy):
    pass


class StreamMigration(CDCStrategy):
    @staticmethod
    def migrate(stmt: exp.Expression, path: str, ai_provider: AIProvider | None = None) -> MigrationObject:
        name = stmt.this.name if hasattr(stmt.this, "name") else str(stmt.this)
        target_sql = (
            f"-- CDC Setup: Delta Change Data Feed (CDF)\n"
            f"ALTER TABLE source_table SET TBLPROPERTIES (delta.enableChangeDataFeed = true);"
        )
        return MigrationObject(
            object_name=name,
            source_type=ObjectType.STREAM,
            target_type="DATABRICKS_CHANGE_DATA_FEED",
            migration_type=MigrationType.ARCHITECTURE_REDESIGN,
            generated_code=target_sql,
            source_file=path,
            script_percentage=20,
            manual_percentage=80,
            confidence=0.6,
            conversion_strategy="Enable Delta CDF on base tables",
            classification_state=ClassificationState.ARCHITECTURE_REDESIGN,
            validation_status=ValidationStatus.GENERATED,
            manual_review=["Analyze CDC requirements and enable Change Data Feed (CDF)."]
        )


# ============================================================
# 4. WORKFLOW STRATEGY
# ============================================================

class WorkflowStrategy(ObjectMigrationStrategy):
    pass


class TaskMigration(WorkflowStrategy):
    @staticmethod
    def migrate(stmt: exp.Expression, path: str, ai_provider: AIProvider | None = None) -> MigrationObject:
        name = stmt.this.name if hasattr(stmt.this, "name") else str(stmt.this)
        target_yaml = (
            f"resources:\n"
            f"  jobs:\n"
            f"    job_{name}:\n"
            f"      name: job_{name}\n"
            f"      tasks:\n"
            f"        - task_key: run_sql\n"
            f"          sql_task:\n"
            f"            warehouse_id: sql_warehouse_id\n"
            f"            sql:\n"
            f"              path: ./sql/{name}.sql\n"
        )
        return MigrationObject(
            object_name=name,
            source_type=ObjectType.TASK,
            target_type="DATABRICKS_WORKFLOW",
            migration_type=MigrationType.ARCHITECTURE_REDESIGN,
            generated_code=target_yaml,
            source_file=path,
            script_percentage=30,
            manual_percentage=70,
            confidence=0.7,
            conversion_strategy="Databricks Workflows Job configuration",
            classification_state=ClassificationState.ARCHITECTURE_REDESIGN,
            validation_status=ValidationStatus.GENERATED,
            manual_review=["Verify task schedules and Databricks SQL Warehouse configuration."]
        )


# ============================================================
# 5. STORAGE STRATEGIES
# ============================================================

class StorageStrategy(ObjectMigrationStrategy):
    pass


class StageMigration(StorageStrategy):
    @staticmethod
    def migrate(stmt: exp.Expression, path: str, ai_provider: AIProvider | None = None) -> MigrationObject:
        source_sql = stmt.sql(dialect=READ_DIALECT) if hasattr(stmt, "sql") else str(stmt)
        name = stmt.this.name if hasattr(stmt.this, "name") else str(stmt.this)
        
        url_match = re.search(r"URL\s*=\s*'([^']+)'", source_sql, re.IGNORECASE)
        storage_integration_match = re.search(r"STORAGE_INTEGRATION\s*=\s*([A-Za-z0-9_]+)", source_sql, re.IGNORECASE)
        
        target_type = "DATABRICKS_VOLUME"
        target_code = ""
        class_state = ClassificationState.DIRECT
        
        if url_match:
            url = url_match.group(1)
            target_type = "DATABRICKS_EXTERNAL_LOCATION"
            target_code = (
                f"-- Databricks External Location Setup\n"
                f"-- Source URL: {url}\n"
                f"-- Storage Integration: {storage_integration_match.group(1) if storage_integration_match else 'None'}\n"
                f"CREATE EXTERNAL LOCATION `{name}_loc` URL '{url}' WITH (CONNECTION `{name}_connection`);"
            )
            class_state = ClassificationState.ARCHITECTURE_REDESIGN
        else:
            target_code = (
                f"-- Databricks Unity Catalog Volume for Internal Stage\n"
                f"CREATE Volume IF NOT EXISTS {name};"
            )
            
        return MigrationObject(
            object_name=name,
            source_type=ObjectType.STAGE,
            target_type=target_type,
            migration_type=MigrationType.ARCHITECTURE_REDESIGN,
            generated_code=target_code,
            source_file=path,
            script_percentage=80,
            manual_percentage=20,
            confidence=0.8,
            conversion_strategy="Storage mapping matching Stage URLs and Integration config",
            classification_state=class_state,
            validation_status=ValidationStatus.GENERATED,
            manual_review=["Ensure correct IAM role for Databricks Access to external path, if any."]
        )


class FileFormatMigration(StorageStrategy):
    @staticmethod
    def migrate(stmt: exp.Expression, path: str, ai_provider: AIProvider | None = None) -> MigrationObject:
        name = stmt.this.name if hasattr(stmt.this, "name") else str(stmt.this)
        target_code = (
            f"# Spark Read format options mapping\n"
            f"df = spark.read.option(\"header\", \"true\")"
        )
        return MigrationObject(
            object_name=name,
            source_type=ObjectType.FILE_FORMAT,
            target_type="DATABRICKS_READ_OPTIONS",
            migration_type=MigrationType.ARCHITECTURE_REDESIGN,
            generated_code=target_code,
            source_file=path,
            script_percentage=50,
            manual_percentage=50,
            confidence=0.7,
            conversion_strategy="Spark format properties mapping",
            classification_state=ClassificationState.ARCHITECTURE_REDESIGN,
            validation_status=ValidationStatus.GENERATED
        )


# ============================================================
# 6. APPLICATION STRATEGIES
# ============================================================

class ApplicationStrategy(ObjectMigrationStrategy):
    pass


class StreamlitMigration(ApplicationStrategy):
    @staticmethod
    def migrate(stmt: exp.Expression, path: str, ai_provider: AIProvider | None = None) -> MigrationObject:
        name = stmt.this.name if hasattr(stmt.this, "name") else str(stmt.this)
        target_code = (
            f"# Databricks Streamlit Application Redesign\n"
            f"# Review connections and replace with Databricks SQL Warehouse/Workspace API connection\n"
        )
        return MigrationObject(
            object_name=name,
            source_type=ObjectType.STREAMLIT_APP,
            target_type="DATABRICKS_STREAMLIT",
            migration_type=MigrationType.ARCHITECTURE_REDESIGN,
            generated_code=target_code,
            source_file=path,
            script_percentage=50,
            manual_percentage=50,
            confidence=0.75,
            conversion_strategy="Databricks Apps layout migration",
            classification_state=ClassificationState.ARCHITECTURE_REDESIGN,
            validation_status=ValidationStatus.GENERATED
        )


class NativeAppMigration(ApplicationStrategy):
    @staticmethod
    def migrate(stmt: exp.Expression, path: str, ai_provider: AIProvider | None = None) -> MigrationObject:
        name = stmt.this.name if hasattr(stmt.this, "name") else str(stmt.this)
        return MigrationObject(
            object_name=name,
            source_type=ObjectType.UNKNOWN,
            target_type="DATABRICKS_ASSET_BUNDLE",
            migration_type=MigrationType.HIGH_COMPLEXITY,
            generated_code="# Snowflake Native App must be redesigned as a Databricks Asset Bundle (DAB) or clean workspace.",
            source_file=path,
            script_percentage=10,
            manual_percentage=90,
            confidence=0.3,
            conversion_strategy="Native App to DAB redesign manual migration",
            classification_state=ClassificationState.MANUAL_REVIEW,
            validation_status=ValidationStatus.GENERATED
        )


# ============================================================
# 7. PERMISSION & GRANTS
# ============================================================

class PermissionMigration(ObjectMigrationStrategy):
    @staticmethod
    def migrate(stmt: exp.Expression, path: str, ai_provider: AIProvider | None = None) -> MigrationObject:
        source_sql = stmt.sql(dialect=READ_DIALECT)
        target_sql = stmt.sql(dialect=WRITE_DIALECT, pretty=True)
        return MigrationObject(
            object_name=f"GRANT_{path}",
            source_type=ObjectType.GRANT,
            target_type="DATABRICKS_GRANT",
            migration_type=MigrationType.AUTOMATED,
            generated_code=target_sql,
            source_file=path,
            script_percentage=90,
            confidence=0.85,
            conversion_strategy="Unity Catalog GRANT transpilation",
            classification_state=ClassificationState.DIRECT,
            validation_status=ValidationStatus.GENERATED
        )
