"""
Tests for the Snow2Lake AI vertical-slice MVP.

Run with: pytest tests/ -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from snow2lake_ai.ai.provider import MockAIProvider
from snow2lake_ai.models import MigrationType, ObjectType
from snow2lake_ai.orchestrator import run_migration
from snow2lake_ai.python_migrator.analyzer import analyze_procedure
from snow2lake_ai.python_migrator.migrator import migrate_python_file
from snow2lake_ai.secure_view.migrator import migrate_secure_view
from snow2lake_ai.sql_migrator.migrator import migrate_sql_file
from snow2lake_ai.validation.validator import validate_object

SAMPLE_APP = Path(__file__).resolve().parent.parent / "sample_snowflake_app"


# ---------------------------------------------------------------- SQL ----

def test_create_table_migrates_automated_and_validates():
    sql = "CREATE TABLE t (id NUMBER, name VARCHAR(50), amt NUMBER(10,2));"
    objs = migrate_sql_file("t.sql", sql)
    assert len(objs) == 1
    obj = objs[0]
    assert obj.migration_type == MigrationType.AUTOMATED
    assert obj.source_type == ObjectType.TABLE
    assert "CREATE TABLE" in obj.generated_code.upper()
    validate_object(obj)
    assert obj.validated is True


def test_secure_view_is_architecture_redesign_and_preserves_role_logic():
    sql = (
        "CREATE SECURE VIEW customer_secure_view AS "
        "SELECT customer_id FROM customers WHERE region = CURRENT_ROLE();"
    )
    objs = migrate_sql_file("v.sql", sql)
    assert len(objs) == 1
    obj = objs[0]
    assert obj.migration_type == MigrationType.ARCHITECTURE_REDESIGN
    assert obj.source_type == ObjectType.SECURE_VIEW
    assert obj.security_notes, "secure view must carry security_notes"
    # Must NOT silently replace CURRENT_ROLE() with CURRENT_USER()
    assert "CURRENT_USER" not in obj.generated_code.upper() or "is_account_group_member" in obj.generated_code


def test_stream_and_task_are_architecture_redesign_not_silently_dropped():
    sql = "CREATE STREAM s1 ON TABLE sales;\nCREATE TASK t1 SCHEDULE='1 minute' AS CALL foo();"
    objs = migrate_sql_file("st.sql", sql)
    assert len(objs) == 2
    for obj in objs:
        assert obj.migration_type == MigrationType.ARCHITECTURE_REDESIGN
        assert obj.manual_review


def test_materialized_view_flags_refresh_semantics():
    sql = "CREATE MATERIALIZED VIEW mv AS SELECT a, SUM(b) FROM t GROUP BY a;"
    objs = migrate_sql_file("mv.sql", sql)
    obj = objs[0]
    assert obj.source_type == ObjectType.MATERIALIZED_VIEW
    assert obj.migration_type == MigrationType.AI_ASSISTED
    assert any("refresh" in w.lower() for w in obj.warnings)


def test_unparseable_sql_flagged_high_complexity_not_crashed():
    objs = migrate_sql_file("bad.sql", "CREATE TALBE !!! not sql at all ((((")
    assert len(objs) == 1
    assert objs[0].migration_type == MigrationType.HIGH_COMPLEXITY


# ---------------------------------------------------------- Python AST ----

def test_analyzer_detects_collect_and_row_loop_antipattern():
    src = (SAMPLE_APP / "procedures" / "process_sales.py").read_text()
    results = analyze_procedure(src)
    assert len(results) == 1
    analysis = results[0]
    assert analysis.performance_risks, "collect()+loop should be flagged"
    kinds = {r.kind for r in analysis.performance_risks}
    assert "COLLECT" in kinds
    assert analysis.has_row_loop_over_dataframe is True
    assert analysis.has_sql_in_loop is True
    assert analysis.is_safe_to_auto_convert is False


def test_analyzer_clean_dataframe_code_is_safe_to_auto_convert():
    src = (SAMPLE_APP / "procedures" / "process_customer.py").read_text()
    results = analyze_procedure(src)
    analysis = results[0]
    assert not analysis.performance_risks
    assert analysis.is_safe_to_auto_convert is True
    assert "join" in analysis.dataframe_calls


def test_clean_procedure_migrates_automated_without_ai():
    src = (SAMPLE_APP / "procedures" / "process_customer.py").read_text()
    objs = migrate_python_file("process_customer.py", src, MockAIProvider())
    assert len(objs) == 1
    obj = objs[0]
    assert obj.migration_type == MigrationType.AUTOMATED
    assert obj.ai_percentage == 0
    assert "spark.table(" in obj.generated_code
    assert "session.table(" not in obj.generated_code


def test_risky_procedure_routes_to_ai_assisted_path():
    src = (SAMPLE_APP / "procedures" / "process_sales.py").read_text()
    objs = migrate_python_file("process_sales.py", src, MockAIProvider())
    assert len(objs) == 1
    obj = objs[0]
    assert obj.migration_type in (MigrationType.AI_ASSISTED, MigrationType.HIGH_COMPLEXITY)
    assert obj.performance_risks
    assert obj.manual_review


def test_never_blindly_converts_row_loop_to_pyspark_row_loop():
    """Core requirement: a driver-side `for row in df.collect()` loop must
    never be mechanically retyped as a PySpark row loop and marked done."""
    src = (SAMPLE_APP / "procedures" / "process_sales.py").read_text()
    objs = migrate_python_file("process_sales.py", src, MockAIProvider())
    obj = objs[0]
    assert obj.migration_type != MigrationType.AUTOMATED
    assert any(r.kind == "COLLECT" for r in obj.performance_risks)


# --------------------------------------------------------- end-to-end ----

def test_full_pipeline_runs_end_to_end(tmp_path):
    report = run_migration(str(SAMPLE_APP), str(tmp_path / "out"), ai_provider=MockAIProvider())
    assert report.total > 0
    # Every migration type bucket should be represented in this sample app.
    assert report.count(MigrationType.AUTOMATED) > 0
    assert report.count(MigrationType.ARCHITECTURE_REDESIGN) > 0
    # No object should be silently dropped without a target type.
    assert all(o.target_type for o in report.objects)
    # Generated project files were actually written.
    generated_files = list((tmp_path / "out").rglob("*"))
    assert any(f.suffix == ".sql" for f in generated_files)
    assert any(f.suffix == ".py" for f in generated_files)


def test_validation_never_marks_ai_placeholder_as_falsely_complete():
    """The MockAIProvider's placeholder output must not be reported as a
    confidently-validated, production-ready migration (spec rule #38)."""
    src = (SAMPLE_APP / "procedures" / "process_sales.py").read_text()
    objs = migrate_python_file("process_sales.py", src, MockAIProvider())
    obj = objs[0]
    assert obj.confidence == 0.0
    assert obj.manual_review


def test_comprehensive_object_migration():
    # Verify Table mappings
    sql_tbl = "CREATE TABLE sales (id NUMBER(18,0), amt NUMBER(10,2), desc VARCHAR, created TIMESTAMP_NTZ);"
    objs = migrate_sql_file("tbl.sql", sql_tbl)
    assert len(objs) == 1
    assert "id BIGINT" in objs[0].generated_code
    assert "amt DECIMAL(10, 2)" in objs[0].generated_code
    assert "desc STRING" in objs[0].generated_code
    assert "created TIMESTAMP" in objs[0].generated_code
    
    # Verify database / schema mapping
    sql_db = "CREATE DATABASE my_db;"
    objs = migrate_sql_file("db.sql", sql_db)
    assert objs[0].target_type == "DATABRICKS_CATALOG"
    
    # Verify Stream CDC mapping
    sql_st = "CREATE STREAM s1 ON TABLE sales;"
    objs = migrate_sql_file("stream.sql", sql_st)
    assert objs[0].target_type == "DATABRICKS_CHANGE_DATA_FEED"
    
    # Verify Task mapping
    sql_tsk = "CREATE TASK t1 SCHEDULE='5 minute' AS SELECT 1;"
    objs = migrate_sql_file("task.sql", sql_tsk)
    assert objs[0].target_type == "DATABRICKS_WORKFLOW"
    
    # Verify Stage mapping
    sql_stg = "CREATE STAGE my_stage;"
    objs = migrate_sql_file("stage.sql", sql_stg)
    assert objs[0].target_type == "DATABRICKS_VOLUME"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
