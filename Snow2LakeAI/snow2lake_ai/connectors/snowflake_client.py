from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any


class SnowflakeStageClient:
    """Small Snowflake connector wrapper for listing/downloading stage files.

    Uses the Snowflake SQL LIST command and GET command. Credentials are read
    from the supplied config/environment and are never written to migration
    output files.
    """

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.conn = None

    def connect(self):
        try:
            import snowflake.connector
        except ImportError as exc:
            raise RuntimeError("Install snowflake-connector-python to use Snowflake stage input.") from exc

        kwargs = {
            "account": self.config["account"],
            "user": self.config["user"],
            "warehouse": self.config.get("warehouse"),
            "database": self.config.get("database"),
            "schema": self.config.get("schema"),
            "role": self.config.get("role"),
        }
        kwargs = {k: v for k, v in kwargs.items() if v}
        auth = self.config.get("authenticator", "snowflake")
        kwargs["authenticator"] = auth
        if auth == "snowflake":
            kwargs["password"] = self.config.get("password") or os.getenv("SNOWFLAKE_PASSWORD")
        elif auth == "externalbrowser":
            # Browser authentication is handled by the connector.
            pass
        else:
            # Allows advanced auth parameters through environment/config later.
            if self.config.get("password"):
                kwargs["password"] = self.config["password"]

        self.conn = snowflake.connector.connect(**kwargs)
        return self

    def close(self):
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def __enter__(self):
        return self.connect()

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def list_stage(self, stage: str) -> list[dict[str, Any]]:
        if self.conn is None:
            self.connect()
        cur = self.conn.cursor()
        try:
            cur.execute(f"LIST {stage}")
            columns = [d[0].lower() for d in cur.description]
            rows = cur.fetchall()
            return [dict(zip(columns, row)) for row in rows]
        finally:
            cur.close()

    def download_stage(self, stage: str, local_dir: str, prefix: str = "") -> Path:
        if self.conn is None:
            self.connect()
        out = Path(local_dir).resolve()
        out.mkdir(parents=True, exist_ok=True)
        stage_ref = stage.rstrip("/")
        if prefix:
            stage_ref += "/" + prefix.strip("/")
        cur = self.conn.cursor()
        try:
            # GET preserves staged file names under the destination directory.
            cur.execute(f"GET {stage_ref} file://{out.as_posix()} OVERWRITE=TRUE")
        finally:
            cur.close()
        return out

    def query(self, sql: str) -> list[tuple]:
        if self.conn is None:
            self.connect()
        cur = self.conn.cursor()
        try:
            cur.execute(sql)
            return cur.fetchall()
        finally:
            cur.close()


def test_snowflake_connection(config: dict[str, Any]) -> tuple[bool, str]:
    try:
        with SnowflakeStageClient(config) as client:
            client.query("SELECT CURRENT_ACCOUNT(), CURRENT_USER(), CURRENT_ROLE()")
        return True, "Connected to Snowflake."
    except Exception as exc:
        return False, str(exc)
