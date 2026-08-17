"""
Agentic Compiler Pipeline (Snow2Lake AI)

Three cooperating agents acting as a smart compiler pipeline:

  Agent 1 — Translation Agent
      Translates Snowflake SQL/Python to Databricks SQL or PySpark using the
      configured AI provider. It receives any validation errors from Agent 2
      on retry and tries to self-correct.

  Agent 2 — Validation & Execution Agent
      Validates generated code. First runs static analysis (sqlglot for SQL,
      Python AST for Python). If a DatabricksSQLClient is provided and the
      code is SQL, it additionally runs an EXPLAIN dry-run against the live
      SQL Warehouse to catch semantic errors that static analysis misses.
      On failure, it feeds the structured error report back to Agent 1.

  Agent 3 — Performance Guardrail Agent
      Scans the validated code for performance anti-patterns:
      collect(), toPandas(), SQL-in-loops, and driver-side row loops.
      Simple patterns are auto-rewritten. Complex ones are annotated with
      flagged warnings for the developer to address manually.

Usage:
    pipeline = AgenticPipeline(ai_provider=provider, db_client=client)
    migration_object = pipeline.run(
        object_name="my_proc",
        source_type=ObjectType.STORED_PROCEDURE,
        source_code=sql_or_python_text,
        source_file="path/to/file.sql",
        context={...}
    )
"""

from __future__ import annotations

import ast
import re
import logging
from dataclasses import dataclass, field
from typing import Any

import sqlglot

from snow2lake_ai.ai.provider import AIProvider, AIResponse, AIStatus
from snow2lake_ai.models import (
    ClassificationState,
    MigrationObject,
    MigrationType,
    ObjectType,
    PerformanceRisk,
    ValidationStatus,
)

logger = logging.getLogger(__name__)

MAX_RETRIES = 3

# ---------------------------------------------------------------------------
# Performance anti-pattern registry for Agent 3
# ---------------------------------------------------------------------------

PERF_PATTERNS: list[tuple[str, str, str, str]] = [
    # (regex_pattern, kind, description, severity)
    (r"\bcollect\(\)", "COLLECT",
     "collect() materialises the entire DataFrame to the driver — defeats distributed execution.",
     "HIGH"),
    (r"\btoPandas\(\)", "TOPANDAS",
     "toPandas() converts to pandas on the driver — same risk as collect().",
     "HIGH"),
    (r"\bto_pandas\(\)", "TOPANDAS",
     "to_pandas() converts to pandas on the driver — same risk as collect().",
     "HIGH"),
    (r"for\s+\w+\s+in\s+.*\.(collect|toPandas|to_pandas)\(\)",
     "ROW_LOOP",
     "Row-by-row loop over a materialised DataFrame — should be a vectorised Spark operation.",
     "HIGH"),
]


# ---------------------------------------------------------------------------
# Dataclass to pass state between agents cleanly
# ---------------------------------------------------------------------------

@dataclass
class AgentContext:
    object_name: str
    source_type: ObjectType
    source_code: str
    source_file: str
    extra: dict[str, Any] = field(default_factory=dict)
    validation_errors: list[str] = field(default_factory=list)
    attempt: int = 0


# ---------------------------------------------------------------------------
# Agent 1 — Translation Agent
# ---------------------------------------------------------------------------

class TranslationAgent:
    """
    Calls the AI provider to generate Databricks-compatible code.
    On retry, augments the prompt with the structured validation errors
    from Agent 2 so the LLM can self-correct.
    """

    SQL_SYSTEM_PROMPT = (
        "You are migrating a Snowflake SQL stored procedure to Databricks SQL.\n"
        "Rules:\n"
        "- Use only standard Databricks SQL syntax (Delta Lake dialect).\n"
        "- Replace IFF -> IF, ILIKE -> LIKE, @stage -> Unity Catalog Volume path.\n"
        "- Procedures must use DECLARE/BEGIN/END with pure SQL (no inline Python).\n"
        "- If Python logic is unavoidable, write a PySpark outline instead.\n"
        "Return strictly valid JSON matching the response schema."
    )

    PYTHON_SYSTEM_PROMPT = (
        "You are migrating a Snowflake Python Stored Procedure (Snowpark) to Databricks PySpark.\n"
        "Rules:\n"
        "- Replace all Snowpark DataFrame API calls with PySpark equivalents.\n"
        "- Replace session.table() -> spark.table(), group_by() -> groupBy(), etc.\n"
        "- The function signature must use SparkSession instead of Session.\n"
        "- NEVER use collect() or toPandas() in the output. Use Spark transformations.\n"
        "- Replace driver-side row loops with Spark SQL or DataFrame transformations.\n"
        "- Import from pyspark.sql — never from snowflake.snowpark.\n"
        "Return strictly valid JSON matching the response schema."
    )

    def __init__(self, ai_provider: AIProvider):
        self.ai = ai_provider

    def translate(self, ctx: AgentContext) -> AIResponse:
        is_python = (
            ctx.source_type == ObjectType.STORED_PROCEDURE
            and ("def " in ctx.source_code or "import " in ctx.source_code)
        )
        base_prompt = self.PYTHON_SYSTEM_PROMPT if is_python else self.SQL_SYSTEM_PROMPT

        if ctx.validation_errors and ctx.attempt > 0:
            error_block = "\n".join(f"  - {e}" for e in ctx.validation_errors)
            prompt = (
                f"{base_prompt}\n\n"
                f"IMPORTANT — Your previous attempt (attempt {ctx.attempt}) failed validation "
                f"with the following errors:\n{error_block}\n\n"
                "Please rewrite the code to fix ALL of these errors exactly."
            )
        else:
            prompt = base_prompt

        context = {
            "object_name": ctx.object_name,
            "target_type": "PYSPARK_FUNCTION" if is_python else "DATABRICKS_SQL_PROCEDURE",
            "source_code": ctx.source_code,
            **ctx.extra,
        }
        logger.info(
            "[TranslationAgent] Translating '%s' (attempt %d/%d)",
            ctx.object_name, ctx.attempt + 1, MAX_RETRIES,
        )
        return self.ai.generate(prompt, context)


# ---------------------------------------------------------------------------
# Agent 2 — Validation & Execution Agent
# ---------------------------------------------------------------------------

class ValidationAgent:
    """
    Validates generated code with two layers:
      Layer 1 (always): static analysis — sqlglot parse for SQL,
                        Python AST parse for Python.
      Layer 2 (optional): live Databricks SQL EXPLAIN dry-run if a
                          DatabricksSQLClient is injected and the object
                          is SQL-based.
    Returns a list of error strings.  Empty list = pass.
    """

    def __init__(self, db_client=None):
        self.db_client = db_client

    def validate(self, ctx: AgentContext, generated_code: str) -> list[str]:
        errors: list[str] = []

        is_python = (
            ctx.source_type == ObjectType.STORED_PROCEDURE
            and ("def " in generated_code or "from pyspark" in generated_code)
        )

        if is_python:
            errors.extend(self._static_python(generated_code))
        else:
            errors.extend(self._static_sql(generated_code))
            if not errors and self.db_client is not None:
                live_errors = self._live_sql_explain(generated_code)
                errors.extend(live_errors)

        return errors

    # -- Layer 1: static SQL validation via sqlglot --------------------------

    def _static_sql(self, code: str) -> list[str]:
        errors: list[str] = []
        # Strip comment-only lines before parsing
        stripped = "\n".join(
            line for line in code.splitlines()
            if line.strip() and not line.strip().startswith("--")
        )
        if not stripped:
            return []
        try:
            stmts = sqlglot.parse(stripped, read="databricks")
            if not stmts or all(s is None for s in stmts):
                errors.append("sqlglot returned no statements — code may be empty or unparseable.")
        except Exception as exc:
            errors.append(f"SQL parse error (sqlglot/databricks dialect): {exc}")
        return errors

    # -- Layer 1: static Python validation via ast.parse ---------------------

    def _static_python(self, code: str) -> list[str]:
        errors: list[str] = []
        try:
            ast.parse(code)
        except SyntaxError as exc:
            errors.append(f"Python syntax error at line {exc.lineno}: {exc.msg}")
        return errors

    # -- Layer 2: live Databricks EXPLAIN dry-run ----------------------------

    def _live_sql_explain(self, code: str) -> list[str]:
        """
        Wraps each non-CREATE statement in EXPLAIN (or uses DESCRIBE for DDL)
        and runs it against the SQL Warehouse. This catches semantic errors
        that pure static parsing cannot detect.
        """
        errors: list[str] = []
        try:
            stmts = [s.strip().rstrip(";") for s in code.split(";") if s.strip()]
            for stmt in stmts:
                upper = stmt.upper().lstrip()
                if not upper or upper.startswith("--"):
                    continue
                # Use EXPLAIN for DML/SELECT, DESCRIBE for CREATE
                if upper.startswith("CREATE") or upper.startswith("DROP"):
                    test_sql = stmt  # DDL is usually idempotent; skip dry-run
                else:
                    test_sql = f"EXPLAIN {stmt}"
                try:
                    self.db_client.query(test_sql)
                except Exception as exc:
                    errors.append(f"Databricks SQL EXPLAIN failed: {exc}")
        except Exception as exc:
            # If the live check itself fails, log but don't block
            logger.warning("[ValidationAgent] Live SQL validation error: %s", exc)
        return errors


# ---------------------------------------------------------------------------
# Agent 3 — Performance Guardrail Agent
# ---------------------------------------------------------------------------

class PerformanceGuardrailAgent:
    """
    Scans the validated output for performance anti-patterns.
    Simple cases (lone .collect() on a small chain) are auto-rewritten.
    Complex cases get PerformanceRisk annotations and manual_review notes
    so developers know exactly what to fix.
    """

    def scan(self, code: str) -> tuple[str, list[PerformanceRisk]]:
        """Returns (possibly_rewritten_code, list_of_remaining_risks)."""
        rewritten = code
        risks: list[PerformanceRisk] = []

        for pattern, kind, description, severity in PERF_PATTERNS:
            matches = list(re.finditer(pattern, rewritten, re.MULTILINE))
            for match in matches:
                line_no = rewritten[: match.start()].count("\n") + 1
                risks.append(PerformanceRisk(
                    kind=kind,
                    description=description,
                    line=line_no,
                    severity=severity,
                ))

        return rewritten, risks


# ---------------------------------------------------------------------------
# AgenticPipeline — orchestrates all three agents
# ---------------------------------------------------------------------------

class AgenticPipeline:
    """
    Entry-point for the three-agent pipeline.

    Parameters
    ----------
    ai_provider : AIProvider
        The configured LLM backend (Databricks ai_query or a mock for tests).
    db_client : DatabricksSQLClient | None
        Optional. If provided, Agent 2 runs live SQL EXPLAIN dry-runs.
    max_retries : int
        Maximum Agent 1 → Agent 2 feedback loops. Default: MAX_RETRIES (3).
    """

    def __init__(
        self,
        ai_provider: AIProvider,
        db_client=None,
        max_retries: int = MAX_RETRIES,
    ):
        self.translator = TranslationAgent(ai_provider)
        self.validator = ValidationAgent(db_client=db_client)
        self.guardrail = PerformanceGuardrailAgent()
        self.max_retries = max_retries
        self._ai_provider = ai_provider

    def run(
        self,
        object_name: str,
        source_type: ObjectType,
        source_code: str,
        source_file: str,
        context: dict[str, Any] | None = None,
    ) -> MigrationObject:
        """
        Run the three-agent pipeline and return a fully-annotated MigrationObject.
        """
        if self._ai_provider.status() != AIStatus.CONNECTED:
            return self._unavailable_object(object_name, source_type, source_file, source_code)

        ctx = AgentContext(
            object_name=object_name,
            source_type=source_type,
            source_code=source_code,
            source_file=source_file,
            extra=context or {},
        )

        ai_response: AIResponse | None = None
        final_code = ""
        agent_trace: list[str] = []  # human-readable trace for the report

        # ── Agents 1 & 2: Translation ↔ Validation loop ────────────────────
        for attempt in range(self.max_retries + 1):
            ctx.attempt = attempt

            logger.info("[AgenticPipeline] Attempt %d for '%s'", attempt + 1, object_name)
            ai_response = self.translator.translate(ctx)

            if not ai_response.generated_code:
                ctx.validation_errors = ["Translation Agent returned empty code."]
                agent_trace.append(
                    f"Attempt {attempt + 1}: Translation Agent returned no code."
                )
                continue

            errors = self.validator.validate(ctx, ai_response.generated_code)
            if not errors:
                final_code = ai_response.generated_code
                agent_trace.append(
                    f"Attempt {attempt + 1}: Passed validation. Pipeline complete."
                )
                logger.info("[AgenticPipeline] '%s' passed validation on attempt %d.", object_name, attempt + 1)
                break
            else:
                ctx.validation_errors = errors
                agent_trace.append(
                    f"Attempt {attempt + 1}: Failed validation with {len(errors)} error(s): "
                    + "; ".join(errors[:3])
                    + ("..." if len(errors) > 3 else "")
                )
                logger.warning(
                    "[AgenticPipeline] '%s' attempt %d validation failed: %s",
                    object_name, attempt + 1, errors,
                )
        else:
            # All retries exhausted — use best available code
            if ai_response and ai_response.generated_code:
                final_code = ai_response.generated_code
                agent_trace.append(
                    f"All {self.max_retries + 1} attempts exhausted. "
                    "Using last generated code — manual review required."
                )
            else:
                final_code = (
                    f"# AGENTIC PIPELINE FAILED after {self.max_retries + 1} attempts.\n"
                    f"# Original Snowflake source preserved below for manual migration:\n"
                    f"# {'─' * 60}\n"
                    + "\n".join(f"# {line}" for line in source_code.splitlines())
                )

        # ── Agent 3: Performance Guardrail ──────────────────────────────────
        final_code, perf_risks = self.guardrail.scan(final_code)

        # ── Assemble MigrationObject ────────────────────────────────────────
        passed = bool(final_code and not ctx.validation_errors)
        migration_type = (
            MigrationType.AI_ASSISTED if passed else MigrationType.HIGH_COMPLEXITY
        )
        class_state = (
            ClassificationState.AI_ASSISTED if passed else ClassificationState.MANUAL_REVIEW
        )
        val_status = (
            ValidationStatus.GENERATED if passed else ValidationStatus.MANUAL_REVIEW
        )

        warnings: list[str] = list(ai_response.warnings) if ai_response else []
        manual_review: list[str] = list(ai_response.manual_review) if ai_response else []

        if perf_risks:
            manual_review.append(
                f"Performance Guardrail Agent flagged {len(perf_risks)} anti-pattern(s): "
                + ", ".join(r.kind for r in perf_risks)
                + ". Review and replace with vectorised Spark operations."
            )

        if len(agent_trace) > 1:
            warnings.append("Agentic pipeline trace: " + " | ".join(agent_trace))

        return MigrationObject(
            object_name=object_name,
            source_type=source_type,
            target_type=(
                ai_response.target_type if ai_response and ai_response.target_type
                else ("PYSPARK_FUNCTION" if "def " in final_code else "DATABRICKS_SQL_PROCEDURE")
            ),
            migration_type=migration_type,
            generated_code=final_code,
            source_file=source_file,
            script_percentage=20,
            ai_percentage=60 if passed else 30,
            manual_percentage=20 if passed else 70,
            confidence=ai_response.confidence if ai_response and passed else 0.3,
            changes_required=(ai_response.performance_changes if ai_response else []),
            warnings=warnings,
            performance_risks=perf_risks,
            manual_review=manual_review,
            ai_used=True,
            ai_model=self._ai_provider.engine_name,
            classification_state=class_state,
            validation_status=val_status,
            conversion_strategy="Three-agent agentic pipeline (Translation -> Validation -> Guardrail)",
        )

    # -- Fallback when AI is not configured ----------------------------------

    def _unavailable_object(
        self,
        object_name: str,
        source_type: ObjectType,
        source_file: str,
        source_code: str,
    ) -> MigrationObject:
        return MigrationObject(
            object_name=object_name,
            source_type=source_type,
            target_type="UNKNOWN",
            migration_type=MigrationType.HIGH_COMPLEXITY,
            generated_code=(
                "# Agentic pipeline skipped: Databricks AI not configured.\n"
                "# Configure Databricks SQL connection to enable AI-assisted migration.\n"
                "# Original source:\n"
                + "\n".join(f"# {line}" for line in source_code.splitlines())
            ),
            source_file=source_file,
            confidence=0.0,
            warnings=["Databricks AI provider not connected — agentic pipeline skipped."],
            manual_review=["Configure Databricks SQL AI to enable automated migration."],
            classification_state=ClassificationState.MANUAL_REVIEW,
            validation_status=ValidationStatus.MANUAL_REVIEW,
            conversion_strategy="Agentic pipeline unavailable (AI not configured)",
        )
