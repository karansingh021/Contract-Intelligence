from __future__ import annotations

import json
import re
from typing import Any

from snow2lake_ai.ai.provider import AIProvider, AIResponse, AIStatus
from snow2lake_ai.connectors.databricks_sql import DatabricksSQLClient


class DatabricksSQLAIProvider(AIProvider):
    """AI provider that calls Databricks' SQL ai_query() function.

    No external LLM API is called by this class. The configured model endpoint
    is invoked through Databricks SQL. Structured JSON output is requested so
    migration code and metadata can be parsed deterministically.
    """

    engine_name = "Databricks SQL ai_query"

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.model = config.get("model", "databricks-gpt-oss-20b")
        self.client: DatabricksSQLClient | None = None

    def status(self) -> AIStatus:
        if not all(self.config.get(k) for k in ("server_hostname", "http_path", "access_token")):
            return AIStatus.NOT_CONFIGURED
        try:
            self.client = self.client or DatabricksSQLClient(self.config)
            self.client.connect()
            return AIStatus.CONNECTED
        except Exception:
            return AIStatus.ERROR

    def generate(self, prompt: str, context: dict[str, Any]) -> AIResponse:
        status = self.status()
        if status != AIStatus.CONNECTED:
            return AIResponse(status=status, ai_engine=self.engine_name,
                              warnings=["Databricks SQL AI is not configured or unreachable."],
                              manual_review=["Configure Databricks SQL connection and AI model before AI-assisted migration."],
                              confidence=0.0)

        payload = json.dumps({"prompt": prompt, "context": context}, ensure_ascii=False)
        # SQL string literal escaping. The model sees the JSON payload as prompt text.
        escaped = payload.replace("'", "''")
        schema = (
            '{"type":"json_schema","json_schema":{"name":"migration_output",'
            '"schema":{"type":"object","properties":{'
            '"target_type":{"type":"string"},'
            '"generated_code":{"type":"string"},'
            '"business_logic_summary":{"type":"string"},'
            '"snowflake_dependencies":{"type":"array","items":{"type":"string"}},'
            '"performance_changes":{"type":"array","items":{"type":"string"}},'
            '"warnings":{"type":"array","items":{"type":"string"}},'
            '"manual_review":{"type":"array","items":{"type":"string"}},'
            '"confidence":{"type":"number"}},'
            '"required":["target_type","generated_code","business_logic_summary",'
            '"snowflake_dependencies","performance_changes","warnings","manual_review","confidence"],'
            '"additionalProperties":false},"strict":true}}'
        )
        sql = (
            "SELECT ai_query("
            f"'{self.model}', "
            f"'{escaped}', "
            f"responseFormat => '{schema.replace(chr(39), chr(39)*2)}', "
            "failOnError => false"
            ")"
        )
        try:
            result = self.client.scalar(sql) if self.client else None
            if isinstance(result, dict):
                # Connector may return a native struct.
                text = json.dumps(result)
            else:
                text = str(result or "")
            # failOnError=false can return a struct with response/errorMessage.
            if text.startswith("{"):
                try:
                    parsed = json.loads(text)
                    if "response" in parsed and parsed.get("response") is not None:
                        parsed = parsed["response"]
                    text = json.dumps(parsed) if isinstance(parsed, dict) else str(parsed)
                except json.JSONDecodeError:
                    pass
            return AIResponse.from_json(text)
        except Exception as exc:
            return AIResponse(status=AIStatus.ERROR, ai_engine=self.engine_name,
                              warnings=[f"Databricks ai_query failed: {exc}"],
                              manual_review=["Review this object manually or retry AI migration."],
                              confidence=0.0)


def ai_sql_preview(model: str, prompt: str) -> str:
    """Generate the SQL statement shown in the UI without executing it."""
    safe = prompt.replace("'", "''")
    return f"SELECT ai_query('{model}', '{safe}') AS ai_output;"
