from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AIStatus(str, Enum):
    CONNECTED = "CONNECTED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    ERROR = "ERROR"


@dataclass
class AIResponse:
    status: AIStatus = AIStatus.ERROR
    target_type: str = ""
    generated_code: str = ""
    business_logic_summary: str = ""
    snowflake_dependencies: list[str] = field(default_factory=list)
    performance_changes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    manual_review: list[str] = field(default_factory=list)
    confidence: float = 0.0
    ai_engine: str = "Databricks SQL ai_query"
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def ai_generated(self) -> bool:
        return self.status == AIStatus.CONNECTED and bool(self.generated_code)

    @classmethod
    def from_json(cls, text: str) -> "AIResponse":
        text = text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return cls(status=AIStatus.ERROR,
                       warnings=["AI response was not valid JSON."],
                       manual_review=["Review AI output manually."], raw={"raw_text": text})
        return cls(status=AIStatus.CONNECTED,
                   target_type=data.get("target_type", ""),
                   generated_code=data.get("generated_code", ""),
                   business_logic_summary=data.get("business_logic_summary", ""),
                   snowflake_dependencies=data.get("snowflake_dependencies", []),
                   performance_changes=data.get("performance_changes", []),
                   warnings=data.get("warnings", []),
                   manual_review=data.get("manual_review", []),
                   confidence=float(data.get("confidence", 0.0)), raw=data)


class AIProvider(ABC):
    engine_name = "Unconfigured"

    @abstractmethod
    def generate(self, prompt: str, context: dict[str, Any]) -> AIResponse:
        raise NotImplementedError

    @abstractmethod
    def status(self) -> AIStatus:
        raise NotImplementedError

    def is_available(self) -> bool:
        return self.status() == AIStatus.CONNECTED

class MockAIProvider(AIProvider):
    """Test-only provider. Never used by the production Streamlit flow."""
    engine_name = "Mock (test only)"

    def status(self) -> AIStatus:
        return AIStatus.CONNECTED

    def generate(self, prompt: str, context: dict[str, Any]) -> AIResponse:
        return AIResponse(
            status=AIStatus.CONNECTED,
            target_type=context.get("target_type", "PYSPARK_FUNCTION"),
            generated_code="# TEST-ONLY AI OUTPUT\n",
            business_logic_summary="Test fixture output.",
            confidence=0.0,
            ai_engine=self.engine_name,
        )
