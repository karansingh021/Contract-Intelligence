from __future__ import annotations

from typing import Any


class DatabricksSQLClient:
    """Databricks SQL connector wrapper used by the AI provider and tests."""

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.conn = None

    def connect(self):
        try:
            from databricks import sql
        except ImportError as exc:
            raise RuntimeError("Install databricks-sql-connector to use Databricks SQL.") from exc
        self.conn = sql.connect(
            server_hostname=self.config["server_hostname"],
            http_path=self.config["http_path"],
            access_token=self.config["access_token"],
        )
        return self

    def close(self):
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def __enter__(self):
        return self.connect()

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def query(self, sql_text: str) -> list[tuple]:
        if self.conn is None:
            self.connect()
        cur = self.conn.cursor()
        try:
            cur.execute(sql_text)
            return cur.fetchall()
        finally:
            cur.close()

    def scalar(self, sql_text: str) -> Any:
        rows = self.query(sql_text)
        return rows[0][0] if rows else None

    def validate_sql_syntax(self, sql_text: str) -> list[str]:
        """
        Attempts an EXPLAIN dry-run on each statement in sql_text.
        Returns a list of error strings; empty list means all statements
        parsed and planned successfully on the warehouse.
        Skips pure DDL (CREATE/DROP/ALTER) since those cannot be EXPLAINed.
        """
        errors: list[str] = []
        stmts = [s.strip().rstrip(";") for s in sql_text.split(";") if s.strip()]
        for stmt in stmts:
            upper = stmt.upper().lstrip()
            if not upper or upper.startswith("--"):
                continue
            # DDL cannot be EXPLAINed — skip gracefully
            if any(upper.startswith(kw) for kw in ("CREATE", "DROP", "ALTER", "USE")):
                continue
            try:
                self.query(f"EXPLAIN {stmt}")
            except Exception as exc:
                errors.append(str(exc))
        return errors


def test_databricks_connection(config: dict[str, Any]) -> tuple[bool, str]:
    try:
        with DatabricksSQLClient(config) as client:
            value = client.scalar("SELECT current_catalog()")
        return True, f"Connected to Databricks SQL. Catalog: {value}"
    except Exception as exc:
        return False, str(exc)

