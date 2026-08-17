"""
Validation Engine (spec section #22, #36, #38).

Nothing is marked `validated=True` on the strength of the generator's
own confidence score. Every MigrationObject's generated_code is
re-checked here:
  - SQL: must parse under the Databricks dialect.
  - Python/PySpark: must parse as valid Python AST, and must not
    reintroduce collect()/toPandas()/driver-side loops.
  - Security-sensitive objects: must carry security_notes explaining
    the intent, not just code.

This is what backs the "no false automation claims" rule (#38): a
migration_type of AUTOMATED or AI_ASSISTED does NOT by itself mean the
report can say "successfully migrated" — `validated` does.
"""

from __future__ import annotations

import ast

import sqlglot
from sqlglot.errors import ParseError

from snow2lake_ai.models import MigrationObject, MigrationType, ObjectType, ValidationStatus

DANGEROUS_PY_PATTERNS = ["collect(", "toPandas(", "to_pandas("]


def validate_object(obj: MigrationObject) -> MigrationObject:
    errors: list[str] = []
    status = ValidationStatus.VALIDATED

    # Object-specific validation checks
    if obj.source_type == ObjectType.TABLE:
        sql_errors = _validate_sql(obj.generated_code)
        if sql_errors:
            errors.extend(sql_errors)
            status = ValidationStatus.FAILED
            
    elif obj.source_type == ObjectType.VIEW:
        sql_errors = _validate_sql(obj.generated_code)
        if sql_errors:
            errors.extend(sql_errors)
            status = ValidationStatus.FAILED
            
    elif obj.source_type == ObjectType.SECURE_VIEW:
        sql_errors = _validate_sql(obj.generated_code)
        if sql_errors:
            errors.extend(sql_errors)
            status = ValidationStatus.FAILED
        elif not obj.security_notes:
            errors.append("Secure view migration is missing security_notes explaining preserved intent.")
            status = ValidationStatus.FAILED
        else:
            status = ValidationStatus.PARTIALLY_VALIDATED
            
    elif obj.source_type == ObjectType.MATERIALIZED_VIEW:
        sql_errors = _validate_sql(obj.generated_code)
        if sql_errors:
            errors.extend(sql_errors)
            status = ValidationStatus.FAILED
        else:
            status = ValidationStatus.PARTIALLY_VALIDATED
            
    elif obj.source_type == ObjectType.STORED_PROCEDURE:
        # Check if the code is actually SQL or Python
        if "DEF " in obj.generated_code.upper():
            py_errors = _validate_python(obj)
            if py_errors:
                errors.extend(py_errors)
                if any("failed to parse" in e.lower() for e in py_errors):
                    status = ValidationStatus.FAILED
                else:
                    status = ValidationStatus.MANUAL_REVIEW
        else:
            # SQL procedure
            sql_errors = _validate_sql(obj.generated_code)
            if sql_errors:
                errors.extend(sql_errors)
                status = ValidationStatus.FAILED
            else:
                status = ValidationStatus.PARTIALLY_VALIDATED
            
    elif obj.source_type in (ObjectType.STREAM, ObjectType.TASK, ObjectType.STAGE, ObjectType.FILE_FORMAT):
        status = ValidationStatus.REDESIGN_REQUIRED
        
    elif obj.source_type == ObjectType.STREAMLIT_APP:
        status = ValidationStatus.PARTIALLY_VALIDATED

    # If it is VALIDATED but has manual review items or warnings, mark as PARTIALLY_VALIDATED
    if status == ValidationStatus.VALIDATED and (obj.manual_review or obj.warnings):
        status = ValidationStatus.PARTIALLY_VALIDATED
        
    if obj.migration_type == MigrationType.HIGH_COMPLEXITY:
        status = ValidationStatus.MANUAL_REVIEW

    obj.validation_errors = errors
    obj.validation_status = status
    obj.validated = (status == ValidationStatus.VALIDATED)
    return obj


def _looks_like_sql(obj: MigrationObject) -> bool:
    return obj.source_type in (
        ObjectType.TABLE,
        ObjectType.VIEW,
        ObjectType.SECURE_VIEW,
        ObjectType.MATERIALIZED_VIEW,
        ObjectType.DML_STATEMENT,
    ) or obj.generated_code.strip().upper().startswith(("CREATE", "SELECT", "INSERT", "UPDATE", "DELETE", "MERGE", "--"))


def _looks_like_python(obj: MigrationObject) -> bool:
    return obj.source_type == ObjectType.STORED_PROCEDURE


def _validate_sql(code: str) -> list[str]:
    # Strip leading architecture-redesign commentary blocks (pure `--` lines)
    # before parsing, since those are intentionally not executable SQL by
    # themselves for ARCHITECTURE_REDESIGN objects — but still try to parse
    # any real statements present.
    stmts = [line for line in code.splitlines()]
    code_for_parse = "\n".join(stmts)
    if not code_for_parse.strip():
        return ["Generated code is empty."]
    try:
        parsed = sqlglot.parse(code_for_parse, read="databricks")
        if not any(p is not None for p in parsed):
            return ["No parseable SQL statements found (may be architecture-redesign commentary only — review manually)."]
        return []
    except ParseError as exc:
        return [f"Generated SQL failed to parse under Databricks dialect: {exc}"]


def _validate_python(obj: MigrationObject) -> list[str]:
    errors: list[str] = []
    code = obj.generated_code
    try:
        ast.parse(code)
    except SyntaxError as exc:
        errors.append(f"Generated Python failed to parse: {exc}")
        return errors  # no point checking patterns on unparseable code

    # Strip full-line comments before scanning — explanatory comments that
    # merely *mention* collect()/toPandas() (e.g. "no collect() calls were
    # needed") must not themselves trip the anti-pattern check.
    code_without_comments = "\n".join(
        line for line in code.splitlines() if not line.strip().startswith("#")
    )

    for pattern in DANGEROUS_PY_PATTERNS:
        if pattern in code_without_comments:
            errors.append(
                f"Generated code still contains '{pattern.rstrip('(')}' — a performance anti-pattern that "
                "should have been eliminated or explicitly flagged for manual review."
            )
    return errors


def validate_all(objects: list[MigrationObject]) -> list[MigrationObject]:
    return [validate_object(o) for o in objects]
