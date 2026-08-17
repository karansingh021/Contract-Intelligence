"""
Python Stored Procedure / Snowpark migration engine (spec #8, #9, #32, #33).

Pipeline per procedure:
    source -> AST analysis (analyzer.py) -> classification
        safe DataFrame-only code  -> deterministic Snowpark->PySpark mapping
        risky code (collect(), row loops, SQL-in-loop, external APIs, ML)
                                   -> three-agent AgenticPipeline:
                                      Agent 1 (Translation) -> Agent 2 (Validation)
                                      -> Agent 3 (Performance Guardrail)

The AI is never trusted blindly: the Validation Agent runs Python AST
parsing and the Guardrail Agent re-checks for anti-patterns after each
generation. If risks remain, they stay as warnings rather than being
silently promoted to AUTOMATED.
"""

from __future__ import annotations

import re

from snow2lake_ai.ai.provider import AIProvider, AIResponse
from snow2lake_ai.ai.agentic_pipeline import AgenticPipeline
from snow2lake_ai.models import MigrationObject, MigrationType, ObjectType, PerformanceRisk, ClassificationState, ValidationStatus
from snow2lake_ai.python_migrator.analyzer import (
    SNOWPARK_TO_PYSPARK_METHODS,
    ProcedureAnalysis,
    analyze_procedure,
)

AI_PROMPT_TEMPLATE = """You are migrating a Snowflake Python Stored Procedure to Databricks.

Preserve the original business logic. Do NOT perform a simple syntax translation.
Analyze the execution model and generate a Databricks-native implementation.

Prefer:
- PySpark DataFrame operations
- Spark SQL
- distributed transformations
- vectorized operations

Avoid:
- collect()
- toPandas()
- driver-side row loops
- repeated Spark actions
- unnecessary data movement

If the original code contains row-by-row processing, determine whether it can be
expressed as a distributed Spark transformation. If it cannot safely be
distributed, explicitly flag the section for manual review.

Identify:
1. Snowflake-specific APIs
2. Snowpark APIs
3. Python business logic
4. Driver-side operations
5. Performance risks
6. External dependencies
7. Unsupported functionality

Return structured JSON containing:
{
    "target_type": "...",
    "generated_code": "...",
    "business_logic_summary": "...",
    "snowflake_dependencies": [],
    "performance_changes": [],
    "warnings": [],
    "manual_review": [],
    "confidence": 0.0
}
"""


def _deterministic_api_rewrite(source_code: str) -> str:
    """Purely mechanical Snowpark -> PySpark API-name substitution for the
    narrow, already-vetted case where the procedure is safe to auto-convert.
    This is intentionally simple text substitution on method names only —
    it runs after the AST classifier has already confirmed there are no
    anti-patterns, so we're not risking a bad blind conversion."""
    rewritten = source_code
    rewritten = re.sub(r"\bsession\s*:\s*Session\b", "spark: SparkSession", rewritten)
    rewritten = re.sub(r"\bsession\.table\(", "spark.table(", rewritten)
    rewritten = re.sub(r"\bsnowpark_session\.table\(", "spark.table(", rewritten)
    for snowpark_name, pyspark_name in SNOWPARK_TO_PYSPARK_METHODS.items():
        if snowpark_name == pyspark_name or snowpark_name == "table":
            continue
        rewritten = re.sub(rf"\.{snowpark_name}\(", f".{pyspark_name}(", rewritten)
    rewritten = re.sub(r"from snowflake\.snowpark[^\n]*\n", "", rewritten)
    rewritten = re.sub(r"import snowflake\.snowpark[^\n]*\n", "", rewritten)
    
    imports = [
        "from pyspark.sql import SparkSession",
        "from pyspark.sql import functions as F"
    ]
    if re.search(r"\bcol\(", rewritten):
        imports.append("from pyspark.sql.functions import col")

    header = (
        "# Auto-converted deterministically: Snowpark DataFrame API -> PySpark DataFrame API.\n"
        "# No driver-side row processing or unsupported patterns were detected in the source,\n"
        "# so no AI-assisted rewrite was required.\n"
        + "\n".join(imports) + "\n\n"
    )
    return header + rewritten


def migrate_python_file(
    path: str, source_code: str, ai_provider: AIProvider
) -> list[MigrationObject]:
    analyses = analyze_procedure(source_code)
    results: list[MigrationObject] = []

    if not analyses:
        return results

    for analysis in analyses:
        if analysis.is_safe_to_auto_convert and analysis.dataframe_calls:
            results.append(_build_automated_result(path, source_code, analysis))
        else:
            results.append(_build_ai_assisted_result(path, source_code, analysis, ai_provider))

    return results


def _build_automated_result(path: str, source_code: str, analysis: ProcedureAnalysis) -> MigrationObject:
    generated = _deterministic_api_rewrite(source_code)
    return MigrationObject(
        object_name=analysis.function_name,
        source_type=ObjectType.STORED_PROCEDURE,
        target_type="PYSPARK_FUNCTION",
        migration_type=MigrationType.AUTOMATED,
        generated_code=generated,
        source_file=path,
        script_percentage=90,
        ai_percentage=0,
        manual_percentage=10,
        confidence=0.85,
        changes_required=[
            f"Snowpark DataFrame API calls mapped to PySpark equivalents: "
            f"{', '.join(sorted(set(analysis.dataframe_calls))) or 'none'}."
        ],
        manual_review=["Confirm Spark session ('spark') is correctly injected in the target environment."],
        conversion_strategy="Deterministic API mapping to PySpark",
        classification_state=ClassificationState.DIRECT,
        validation_status=ValidationStatus.GENERATED
    )



def _build_ai_assisted_result(
    path: str, source_code: str, analysis: ProcedureAnalysis, ai_provider: AIProvider
) -> MigrationObject:
    """
    Routes risky Python Snowpark procedures through the three-agent
    AgenticPipeline:
      Agent 1 — TranslationAgent  : generates PySpark from Snowpark.
      Agent 2 — ValidationAgent   : Python AST parse check + optional
                                    live Databricks EXPLAIN (if connected).
      Agent 3 — GuardrailAgent    : scans for collect/toPandas/loops,
                                    annotates residual risks.

    The detected analysis metadata (risks, external calls, ML, etc.) is
    passed as extra context so the Translation Agent has full visibility
    into why this procedure could not be auto-converted.
    """
    pipeline = AgenticPipeline(ai_provider=ai_provider)
    result = pipeline.run(
        object_name=analysis.function_name,
        source_type=ObjectType.STORED_PROCEDURE,
        source_code=source_code,
        source_file=path,
        context={
            "detected_performance_risks": [r.kind for r in analysis.performance_risks],
            "external_api_calls": analysis.external_api_calls,
            "ml_usage": analysis.ml_usage,
            "dataframe_calls": analysis.dataframe_calls,
            "imports": analysis.imports,
        },
    )

    # Merge static-analysis risks with any guardrail-detected risks
    all_risks = list(analysis.performance_risks) + list(result.performance_risks)
    result.performance_risks = all_risks

    # Append analysis-level manual review notes
    if analysis.external_api_calls:
        result.manual_review.append(
            "Review external API call(s) for Databricks-native alternatives "
            "(e.g. Workflows, external functions)."
        )
    if analysis.ml_usage:
        result.manual_review.append(
            f"ML libraries detected ({', '.join(analysis.ml_usage)}) — "
            "consider MLflow/Databricks ML migration path."
        )

    return result

