"""
CortexAnalyzer - Decodes and maps Snowflake Cortex operations to Databricks capabilities (spec section #3).
"""

from __future__ import annotations
import re
from typing import Any

class CortexAnalysis:
    def __init__(
        self,
        cortex_function: str,
        input_args: list[str],
        expected_behavior: str,
        target_capability: str,
        suggested_code: str,
        classification_state: str,
        confidence: float
    ):
        self.cortex_function = cortex_function
        self.input_args = input_args
        self.expected_behavior = expected_behavior
        self.target_capability = target_capability
        self.suggested_code = suggested_code
        self.classification_state = classification_state
        self.confidence = confidence

class CortexAnalyzer:
    @staticmethod
    def analyze_sql(sql_text: str) -> CortexAnalysis | None:
        # Match SNOWFLAKE.CORTEX.<FUNCTION> or SNOWFLAKE.CORTEX.<FUNCTION>(...)
        match = re.search(r"SNOWFLAKE\.CORTEX\.([A-Z_]+)\s*\((.*)\)", sql_text, re.IGNORECASE)
        if not match:
            # Check without parenthesis
            match_no_args = re.search(r"SNOWFLAKE\.CORTEX\.([A-Z_]+)", sql_text, re.IGNORECASE)
            if not match_no_args:
                return None
            func_name = match_no_args.group(1).upper()
            args = []
        else:
            func_name = match.group(1).upper()
            # extract arguments roughly
            raw_args = match.group(2)
            args = [a.strip().strip("'\"") for a in raw_args.split(",") if a.strip()]

        # Determine Databricks implementation based on Cortex operation semantics
        if func_name in ("COMPLETE", "EXTRACT_ANSWER"):
            return CortexAnalysis(
                cortex_function=func_name,
                input_args=args,
                expected_behavior="Large Language Model text completion/generation",
                target_capability="ai_query() or Databricks Foundation Model APIs",
                suggested_code=f"SELECT ai_query('databricks-meta-llama-3-1-70b-instruct', {', '.join(args) if args else 'prompt'})",
                classification_state="DIRECT",
                confidence=0.9
            )
        elif func_name in ("SENTIMENT", "SUMMARIZE", "TRANSLATE"):
            target_model = {
                "SENTIMENT": "Sentiment Analysis",
                "SUMMARIZE": "Text Summarization",
                "TRANSLATE": "Language Translation"
            }.get(func_name, "Text Completion")
            return CortexAnalysis(
                cortex_function=func_name,
                input_args=args,
                expected_behavior=f"Specialized NLP text function for {target_model}",
                target_capability="ai_query() with custom system prompt instruction",
                suggested_code=f"SELECT ai_query('databricks-meta-llama-3-1-70b-instruct', 'Perform {target_model} on: ' || {args[0] if args else 'text'})",
                classification_state="AI_ASSISTED",
                confidence=0.8
            )
        elif func_name in ("EMBED_TEXT", "EMBED_TEXT_1024"):
            return CortexAnalysis(
                cortex_function=func_name,
                input_args=args,
                expected_behavior="Text embedding generation",
                target_capability="Databricks BGE or GTE Embedding Model Endpoint via ai_query()",
                suggested_code=f"SELECT ai_query('databricks-bge-large-en', {args[0] if args else 'text'})",
                classification_state="ARCHITECTURE_REDESIGN",
                confidence=0.75
            )
        else:
            # Custom/Fine-tuned ML model calling
            return CortexAnalysis(
                cortex_function=func_name,
                input_args=args,
                expected_behavior="Specialized Snowflake proprietary ML function call",
                target_capability="Databricks Model Serving endpoint or custom Python MLflow model UDF",
                suggested_code=f"-- Manual rewrite required: Set up a Databricks Model Serving endpoint for replacement",
                classification_state="MANUAL_REVIEW",
                confidence=0.4
            )
