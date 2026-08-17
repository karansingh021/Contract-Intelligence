"""
Python Stored Procedure analyzer (spec section #8, #32).

This is deliberately NOT a Python-to-Python translator. Before any code
is generated, we walk the AST and classify what the procedure actually
does: DataFrame-style operations (safe to map onto PySpark 1:1),
row-by-row driver-side processing (dangerous to leave as-is under
Spark), external API calls, ML logic, and general side effects.

That classification decides the migration path:
  - Snowpark-DataFrame-only code with no anti-patterns -> deterministic
    API mapping (AUTOMATED / mostly script-based).
  - Anything with collect()/toPandas()/row loops/SQL-in-loops -> flagged
    as a performance risk and routed to the AI layer for a semantic
    rewrite, per the explicit instruction in spec #26 rule 4: never
    blindly convert row-by-row Python into row-by-row PySpark.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

from snow2lake_ai.models import PerformanceRisk

# Snowpark DataFrame methods that map ~1:1 onto PySpark DataFrame methods.
SNOWPARK_TO_PYSPARK_METHODS = {
    "table": "table",
    "filter": "filter",
    "where": "where",
    "select": "select",
    "group_by": "groupBy",
    "agg": "agg",
    "join": "join",
    "with_column": "withColumn",
    "drop": "drop",
    "order_by": "orderBy",
    "sort": "sort",
    "union": "union",
    "union_all": "unionAll",
    "distinct": "distinct",
    "limit": "limit",
    "save_as_table": "saveAsTable",
    "write": "write",
    "to_df": "toDF",
    "count": "count",
}

# Methods that are red flags for driver-side / non-distributed execution.
RISKY_METHODS = {
    "collect": "Materializes the entire DataFrame to the driver — defeats distributed execution.",
    "to_pandas": "Converts to a pandas DataFrame on the driver — same risk as collect().",
    "toPandas": "Converts to a pandas DataFrame on the driver — same risk as collect().",
}

EXTERNAL_API_MODULES = {"requests", "urllib", "urllib2", "urllib3", "httpx", "http.client"}

ML_MODULES = {"sklearn", "xgboost", "lightgbm", "torch", "tensorflow", "keras"}

SNOWPARK_MODULES = {"snowflake.snowpark", "snowflake.connector"}


@dataclass
class ProcedureAnalysis:
    function_name: str
    uses_snowpark_session: bool = False
    dataframe_calls: list[str] = field(default_factory=list)
    unmapped_calls: list[str] = field(default_factory=list)
    performance_risks: list[PerformanceRisk] = field(default_factory=list)
    external_api_calls: list[str] = field(default_factory=list)
    ml_usage: list[str] = field(default_factory=list)
    has_row_loop_over_dataframe: bool = False
    has_sql_in_loop: bool = False
    imports: list[str] = field(default_factory=list)

    @property
    def is_safe_to_auto_convert(self) -> bool:
        """True only if the procedure is pure DataFrame-style code with
        no risky patterns at all -- the narrow case where deterministic
        Snowpark -> PySpark API mapping alone is sufficient."""
        return (
            not self.performance_risks
            and not self.external_api_calls
            and not self.ml_usage
            and not self.unmapped_calls
        )


class SnowparkProcedureVisitor(ast.NodeVisitor):
    """Walks a single function definition and classifies its operations."""

    def __init__(self, function_name: str):
        self.analysis = ProcedureAnalysis(function_name=function_name)
        self._for_depth = 0
        self._dataframe_var_names: set[str] = set()

    # -- imports (module-level, collected separately in analyze_source) --

    def visit_Call(self, node: ast.Call) -> None:
        callee = node.func
        attr_name = None
        base_name = None

        if isinstance(callee, ast.Attribute):
            attr_name = callee.attr
            base = callee.value
            if isinstance(base, ast.Name):
                base_name = base.id

        if attr_name:
            if attr_name in RISKY_METHODS:
                self.analysis.performance_risks.append(
                    PerformanceRisk(
                        kind=attr_name.upper(),
                        description=RISKY_METHODS[attr_name],
                        line=node.lineno,
                        severity="HIGH",
                    )
                )
                if self._for_depth > 0:
                    self.analysis.has_row_loop_over_dataframe = True
            elif attr_name in SNOWPARK_TO_PYSPARK_METHODS:
                self.analysis.dataframe_calls.append(attr_name)
            elif attr_name == "table" and base_name in ("session", "snowpark_session"):
                self.analysis.uses_snowpark_session = True
                self.analysis.dataframe_calls.append("table")
            elif attr_name == "sql" and self._for_depth > 0:
                self.analysis.has_sql_in_loop = True
                self.analysis.performance_risks.append(
                    PerformanceRisk(
                        kind="SQL_IN_LOOP",
                        description="SQL executed inside a loop — likely one query per row instead of a set-based operation.",
                        line=node.lineno,
                        severity="HIGH",
                    )
                )
            elif base_name and self._module_of_name(base_name) in EXTERNAL_API_MODULES:
                self.analysis.external_api_calls.append(f"{base_name}.{attr_name}() @ line {node.lineno}")

        elif isinstance(callee, ast.Name):
            if callee.id in EXTERNAL_API_MODULES:
                self.analysis.external_api_calls.append(f"{callee.id}() @ line {node.lineno}")

        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        self._for_depth += 1
        # Heuristic: `for row in <df>.collect()` or `for row in rows` where
        # `rows` came from a prior .collect()/.to_pandas() call.
        iter_src = ast.dump(node.iter)
        if "collect" in iter_src or "to_pandas" in iter_src or "toPandas" in iter_src:
            self.analysis.has_row_loop_over_dataframe = True
            self.analysis.performance_risks.append(
                PerformanceRisk(
                    kind="ROW_LOOP",
                    description="Row-by-row for-loop driven by a materialized DataFrame/result set.",
                    line=node.lineno,
                    severity="HIGH",
                )
            )
        self.generic_visit(node)
        self._for_depth -= 1

    @staticmethod
    def _module_of_name(name: str) -> str:
        # Best-effort: assumes `import requests` style, not aliasing.
        return name


def analyze_procedure(source_code: str, function_name: str | None = None) -> list[ProcedureAnalysis]:
    """Parse a Python source file and analyze every function definition
    (a Snowflake Python stored procedure typically has one entry point,
    but files may contain helpers too)."""
    tree = ast.parse(source_code)

    module_imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            module_imports.add(node.module)

    results: list[ProcedureAnalysis] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            if function_name and node.name != function_name:
                continue
            visitor = SnowparkProcedureVisitor(node.name)
            visitor.analysis.imports = sorted(module_imports)
            for mod in module_imports:
                if any(mod.startswith(m) for m in ML_MODULES):
                    visitor.analysis.ml_usage.append(mod)
                if any(mod.startswith(m) for m in SNOWPARK_MODULES):
                    visitor.analysis.uses_snowpark_session = True
            visitor.visit(node)
            results.append(visitor.analysis)

    return results
