from pathlib import Path

from snow2lake_ai.ai.databricks_sql_ai import ai_sql_preview
from snow2lake_ai.stage.stage_scanner import scan_downloaded_stage


def test_stage_scan(tmp_path: Path):
    (tmp_path / "setup.sql").write_text("create table x(id int);")
    (tmp_path / "p.py").write_text("def f():\n    return 1\n")
    result = scan_downloaded_stage(str(tmp_path), "@APP_STAGE")
    assert result["counts"]["total"] == 2
    assert result["counts"]["sql"] == 1
    assert result["counts"]["python"] == 1


def test_ai_sql_preview_escapes_prompt():
    sql = ai_sql_preview("databricks-gpt-oss-20b", "Convert O'Reilly")
    assert "O''Reilly" in sql
    assert sql.startswith("SELECT ai_query(")
