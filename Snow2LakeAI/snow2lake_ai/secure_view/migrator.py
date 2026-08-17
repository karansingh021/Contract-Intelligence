"""
Secure View migration (spec section #10, #34).

A Snowflake SECURE VIEW's defining characteristic isn't the SQL body —
it's that it hides its definition from unauthorized users and typically
encodes row-level access logic (often via CURRENT_ROLE()). Databricks
has no "secure view" object. Blindly emitting `CREATE VIEW ... WHERE
region = CURRENT_USER()` would be wrong on two counts: it silently swaps
the security *principal* (role vs. user) and it does nothing to restrict
who can see the view definition itself.

This module treats every secure view as an ARCHITECTURE_REDESIGN: it
extracts the underlying query, flags the CURRENT_ROLE() dependency
instead of auto-substituting it, and generates a Unity-Catalog-based
implementation (view + row filter function) with the security intent
spelled out for human review.
"""

from __future__ import annotations

import re

from sqlglot import exp

from snow2lake_ai.models import MigrationObject, MigrationType, ObjectType

READ_DIALECT = "snowflake"
WRITE_DIALECT = "databricks"

CURRENT_ROLE_RE = re.compile(r"CURRENT_ROLE\s*\(\s*\)", re.IGNORECASE)


def migrate_secure_view(stmt: exp.Create, path: str, source_sql: str) -> MigrationObject:
    this = stmt.this
    if isinstance(this, exp.Schema):
        this = this.this
    name = this.name if hasattr(this, "name") else str(this)

    select_expr = stmt.expression  # the AS SELECT ... body
    uses_current_role = bool(CURRENT_ROLE_RE.search(source_sql))

    try:
        transpiled_body = select_expr.sql(dialect=WRITE_DIALECT, pretty=True) if select_expr else ""
    except Exception:
        transpiled_body = select_expr.sql(dialect=READ_DIALECT) if select_expr else ""

    security_notes = [
        "Source object was a Snowflake SECURE VIEW — security intent (not just SQL) must be preserved.",
    ]
    manual_review = [
        f"Confirm which Unity Catalog group(s) should replace the Snowflake role(s) referenced by '{name}'.",
        "Grant SELECT on the underlying table(s) only to the row-filter function's execution context, "
        "not broadly, to replicate 'secure view hides definition' semantics.",
    ]
    warnings = []

    if uses_current_role:
        security_notes.append(
            "Original view used CURRENT_ROLE() for row filtering. This was NOT auto-replaced with "
            "CURRENT_USER() — role-based and user-based filtering are different security models. "
            "A Unity Catalog row filter function using is_account_group_member() is generated as the "
            "closest equivalent; verify it matches the original role hierarchy."
        )
        row_filter_name = f"{name}_row_filter"
        generated_code = _generate_row_filter_architecture(
            view_name=name,
            row_filter_fn_name=row_filter_name,
            transpiled_body=transpiled_body,
        )
        target_type = "UC_VIEW + ROW_FILTER_FUNCTION"
    else:
        warnings.append(
            "SECURE VIEW detected without CURRENT_ROLE() usage — verify whether it relies on other "
            "security mechanisms (e.g. masking policies, secure UDFs) not captured by this scan."
        )
        generated_code = _generate_plain_secure_view(view_name=name, transpiled_body=transpiled_body)
        target_type = "UC_VIEW (definition-hiding via catalog permissions)"

    return MigrationObject(
        object_name=name,
        source_type=ObjectType.SECURE_VIEW,
        target_type=target_type,
        migration_type=MigrationType.ARCHITECTURE_REDESIGN,
        generated_code=generated_code,
        source_file=path,
        script_percentage=55,
        ai_percentage=30,
        manual_percentage=15,
        confidence=0.7,
        changes_required=[
            "SECURE VIEW re-architected as Unity Catalog VIEW + row-level security mechanism.",
            "View definition visibility now controlled via Unity Catalog object permissions "
            "(REVOKE viewing of the view's DDL from non-owners), not a SECURE keyword.",
        ],
        warnings=warnings,
        manual_review=manual_review,
        security_notes=security_notes,
    )


def _generate_row_filter_architecture(view_name: str, row_filter_fn_name: str, transpiled_body: str) -> str:
    return f"""\
-- ARCHITECTURE REDESIGN: Snowflake SECURE VIEW -> Unity Catalog VIEW + ROW FILTER
--
-- Snowflake implementation:
--   SECURE VIEW + role-based WHERE clause using CURRENT_ROLE()
--
-- Databricks implementation:
--   1. A Unity Catalog row filter FUNCTION encoding the same access rule,
--      driven by group membership (is_account_group_member) instead of
--      CURRENT_ROLE(). Map each Snowflake ROLE to a Databricks account/
--      workspace GROUP with the same name during the permissions phase
--      (spec section #16) so this function resolves correctly.
--   2. A plain VIEW over the same base tables as the original query.
--   3. ALTER TABLE ... SET ROW FILTER attaching the function to the
--      underlying table(s), so the restriction applies everywhere the
--      table is queried -- not only through this view.
--
-- MANUAL REVIEW REQUIRED: replace <BASE_TABLE> and the role/group name
-- below with the actual mapping from Snowflake roles to Unity Catalog
-- groups once that mapping is finalized.

CREATE OR REPLACE FUNCTION {row_filter_fn_name}(region STRING)
RETURN
  is_account_group_member(region);  -- TODO: confirm group-naming convention

-- Example attachment (adjust <BASE_TABLE> and column list):
-- ALTER TABLE <BASE_TABLE> SET ROW FILTER {row_filter_fn_name} ON (region);

CREATE OR REPLACE VIEW {view_name} AS
{transpiled_body};
-- Row-level restriction is enforced by the row filter on the base table,
-- not by a WHERE clause in this view -- this preserves the original
-- "restriction applies no matter how the data is accessed" intent.
"""


def _generate_plain_secure_view(view_name: str, transpiled_body: str) -> str:
    return f"""\
-- ARCHITECTURE REDESIGN: Snowflake SECURE VIEW -> Unity Catalog VIEW
-- No CURRENT_ROLE()-based filter detected in the source. If this view
-- relied on masking policies or secure UDFs, migrate those separately
-- (see Masking Policy / UDF migration) and reference them here.

CREATE OR REPLACE VIEW {view_name} AS
{transpiled_body};

-- To replicate "definition hidden from non-owners":
--   REVOKE BROWSE ON VIEW {view_name} FROM `account users`;
--   GRANT SELECT ON VIEW {view_name} TO <authorized_group>;
"""
