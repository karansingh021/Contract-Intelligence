"""
Deterministic mapping registries for Snowflake -> Databricks SQL.

sqlglot's Snowflake->Databricks dialect transpilation handles the bulk of
function/type/syntax mapping already (spec #31 explicitly says to lean
on a real parser/AST rather than regex, and to evaluate existing
Databricks-oriented conversion tooling instead of reinventing it). These
registries exist for:

  1. Documentation / explainability (spec rule #10: every migration
     decision must be explainable) — we can show *why* something changed.
  2. Extra Snowflake-specific constructs sqlglot doesn't fully resolve
     (e.g. SECURE VIEW, CURRENT_ROLE()), which we handle with dedicated
     logic in migrator.py / secure_view.
  3. A place to add overrides if we find sqlglot gets something wrong
     for a specific customer's dialect quirks.
"""

from __future__ import annotations

# Purely documentary — sqlglot performs the actual rewrite for these.
FUNCTION_MAPPING: dict[str, str] = {
    "NVL": "COALESCE",
    "IFF": "IF",
    "DATEADD": "date_add / dateadd",
    "DATEDIFF": "datediff",
    "TO_VARCHAR": "CAST(... AS STRING)",
    "TO_NUMBER": "CAST(... AS DECIMAL)",
    "OBJECT_CONSTRUCT": "named_struct / to_json(struct(...))",
    "ARRAY_AGG": "collect_list",
    "LISTAGG": "array_join(collect_list(...), sep)",
    "PARSE_JSON": "from_json / get_json_object",
    "CURRENT_TIMESTAMP()": "current_timestamp()",
}

TYPE_MAPPING: dict[str, str] = {
    "VARIANT": "STRING / VARIANT (Delta supports VARIANT natively on recent DBR)",
    "OBJECT": "STRUCT / MAP<STRING, STRING>",
    "ARRAY": "ARRAY",
    "NUMBER": "DECIMAL",
    "TEXT": "STRING",
    "TIMESTAMP_NTZ": "TIMESTAMP_NTZ",
    "TIMESTAMP_LTZ": "TIMESTAMP",
    "TIMESTAMP_TZ": "TIMESTAMP",
}

# Snowflake object-level keywords that have no direct sqlglot/Databricks
# translation and must be intercepted before/around transpilation.
SPECIAL_CONSTRUCTS = {
    "SECURE VIEW": "Requires architecture redesign -> Unity Catalog view + row filter / column mask",
    "MATERIALIZED VIEW": "Databricks Materialized View (DLT) where compatible, else Delta + scheduled refresh",
    "STREAM": "Delta Change Data Feed",
    "TASK": "Databricks Workflow / Job",
    "STAGE": "Unity Catalog Volume / External Location",
    "CURRENT_ROLE()": "No direct equivalent -- must be re-derived from Unity Catalog group membership, not CURRENT_USER()",
}
