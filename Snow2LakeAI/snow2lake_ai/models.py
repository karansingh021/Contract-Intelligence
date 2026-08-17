"""
Core data models for Snow2Lake AI.

These dataclasses are the shared contract between the scanner, the
deterministic migration engines, the AI layer, the validator and the
report generator. Every migrated object ends up as a MigrationObject,
regardless of which subsystem produced it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class MigrationType(str, Enum):
    AUTOMATED = "AUTOMATED"                    # 🟢 deterministic
    AI_ASSISTED = "AI_ASSISTED"                # 🟡 script + AI
    ARCHITECTURE_REDESIGN = "ARCHITECTURE_REDESIGN"  # 🟠 no 1:1 equivalent
    HIGH_COMPLEXITY = "HIGH_COMPLEXITY"        # 🔴 needs human redesign

    @property
    def emoji(self) -> str:
        return {
            MigrationType.AUTOMATED: "🟢",
            MigrationType.AI_ASSISTED: "🟡",
            MigrationType.ARCHITECTURE_REDESIGN: "🟠",
            MigrationType.HIGH_COMPLEXITY: "🔴",
        }[self]


class ObjectType(str, Enum):
    DATABASE = "DATABASE"
    SCHEMA = "SCHEMA"
    TABLE = "TABLE"
    VIEW = "VIEW"
    SECURE_VIEW = "SECURE_VIEW"
    MATERIALIZED_VIEW = "MATERIALIZED_VIEW"
    STORED_PROCEDURE = "STORED_PROCEDURE"
    UDF = "UDF"
    STREAM = "STREAM"
    TASK = "TASK"
    STAGE = "STAGE"
    FILE_FORMAT = "FILE_FORMAT"
    ROLE = "ROLE"
    GRANT = "GRANT"
    ROW_ACCESS_POLICY = "ROW_ACCESS_POLICY"
    MASKING_POLICY = "MASKING_POLICY"
    STREAMLIT_APP = "STREAMLIT_APP"
    EXTERNAL_FUNCTION = "EXTERNAL_FUNCTION"
    ML_MODEL = "ML_MODEL"
    CORTEX_USAGE = "CORTEX_USAGE"
    SDK_USAGE = "SDK_USAGE"
    DML_STATEMENT = "DML_STATEMENT"
    UNKNOWN = "UNKNOWN"


@dataclass
class SourceObject:
    """A single object discovered by the scanner, prior to migration."""
    name: str
    object_type: ObjectType
    source_file: str
    source_text: str
    start_line: int = 0
    end_line: int = 0
    references: list[str] = field(default_factory=list)  # names of objects it depends on
    raw_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PerformanceRisk:
    kind: str            # e.g. "COLLECT", "ROW_LOOP", "TOPANDAS", "SQL_IN_LOOP"
    description: str
    line: Optional[int] = None
    severity: str = "MEDIUM"  # LOW | MEDIUM | HIGH


class ClassificationState(str, Enum):
    DIRECT = "DIRECT"
    AI_ASSISTED = "AI_ASSISTED"
    ARCHITECTURE_REDESIGN = "ARCHITECTURE_REDESIGN"
    UNSUPPORTED = "UNSUPPORTED"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class ValidationStatus(str, Enum):
    DISCOVERED = "DISCOVERED"
    GENERATED = "GENERATED"
    VALIDATED = "VALIDATED"
    PARTIALLY_VALIDATED = "PARTIALLY_VALIDATED"
    REDESIGN_REQUIRED = "REDESIGN_REQUIRED"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    FAILED = "FAILED"


@dataclass
class MigrationObject:
    """The migrated counterpart of a SourceObject, plus all metadata
    needed for the report and the validator."""
    object_name: str
    source_type: ObjectType
    target_type: str
    migration_type: MigrationType
    generated_code: str
    source_file: str
    generated_file: str = ""
    script_percentage: int = 0
    ai_percentage: int = 0
    manual_percentage: int = 0
    confidence: float = 1.0
    changes_required: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    performance_risks: list[PerformanceRisk] = field(default_factory=list)
    manual_review: list[str] = field(default_factory=list)
    security_notes: list[str] = field(default_factory=list)
    validated: bool = False
    validation_errors: list[str] = field(default_factory=list)

    # Normalized Object Contract fields
    database: str = ""
    schema: str = ""
    dependencies: list[str] = field(default_factory=list)
    dependents: list[str] = field(default_factory=list)
    snowflake_features: list[str] = field(default_factory=list)
    security_features: list[str] = field(default_factory=list)
    conversion_strategy: str = ""
    generated_files: list[str] = field(default_factory=list)
    validation_status: ValidationStatus = ValidationStatus.GENERATED

    # Traceability properties (spec section #14)
    source_object: str = ""
    source_hash: str = ""
    target_file: str = ""
    target_object: str = ""
    strategy: str = ""
    ai_used: bool = False
    ai_model: str = ""
    classification_state: ClassificationState = ClassificationState.DIRECT
    security_preservation: str = ""  # YES / PARTIAL / NO

    def to_dict(self) -> dict[str, Any]:
        return {
            "object": self.object_name,
            "source_type": self.source_type.value,
            "target_type": self.target_type,
            "migration_type": self.migration_type.value,
            "migration_emoji": self.migration_type.emoji,
            "script_percentage": self.script_percentage,
            "ai_percentage": self.ai_percentage,
            "manual_percentage": self.manual_percentage,
            "confidence": self.confidence,
            "source_file": self.source_file,
            "generated_file": self.generated_file,
            "changes_required": self.changes_required,
            "warnings": self.warnings,
            "performance_risks": [
                {"kind": r.kind, "description": r.description, "line": r.line, "severity": r.severity}
                for r in self.performance_risks
            ],
            "manual_review": self.manual_review,
            "security_notes": self.security_notes,
            "validated": self.validated,
            "validation_errors": self.validation_errors,
            "database": self.database,
            "schema": self.schema,
            "dependencies": self.dependencies,
            "dependents": self.dependents,
            "snowflake_features": self.snowflake_features,
            "security_features": self.security_features,
            "conversion_strategy": self.conversion_strategy,
            "generated_files": self.generated_files,
            "validation_status": self.validation_status.value,
            "source_object": self.source_object,
            "source_hash": self.source_hash,
            "target_file": self.target_file,
            "target_object": self.target_object,
            "strategy": self.strategy,
            "ai_used": self.ai_used,
            "ai_model": self.ai_model,
            "classification_state": self.classification_state.value,
            "security_preservation": self.security_preservation,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> MigrationObject:
        perf_risks = []
        for r in d.get("performance_risks", []):
            perf_risks.append(PerformanceRisk(kind=r["kind"], description=r["description"], line=r.get("line"), severity=r.get("severity", "MEDIUM")))
        
        return cls(
            object_name=d["object"],
            source_type=ObjectType(d["source_type"]),
            target_type=d["target_type"],
            migration_type=MigrationType(d["migration_type"]),
            generated_code=d.get("generated_code", ""),
            source_file=d["source_file"],
            generated_file=d.get("generated_file", ""),
            script_percentage=d.get("script_percentage", 0),
            ai_percentage=d.get("ai_percentage", 0),
            manual_percentage=d.get("manual_percentage", 0),
            confidence=d.get("confidence", 1.0),
            changes_required=d.get("changes_required", []),
            warnings=d.get("warnings", []),
            performance_risks=perf_risks,
            manual_review=d.get("manual_review", []),
            security_notes=d.get("security_notes", []),
            validated=d.get("validated", False),
            validation_errors=d.get("validation_errors", []),
            database=d.get("database", ""),
            schema=d.get("schema", ""),
            dependencies=d.get("dependencies", []),
            dependents=d.get("dependents", []),
            snowflake_features=d.get("snowflake_features", []),
            security_features=d.get("security_features", []),
            conversion_strategy=d.get("conversion_strategy", ""),
            generated_files=d.get("generated_files", []),
            validation_status=ValidationStatus(d.get("validation_status", "GENERATED")),
            source_object=d.get("source_object", ""),
            source_hash=d.get("source_hash", ""),
            target_file=d.get("target_file", ""),
            target_object=d.get("target_object", ""),
            strategy=d.get("strategy", ""),
            ai_used=d.get("ai_used", False),
            ai_model=d.get("ai_model", ""),
            classification_state=ClassificationState(d.get("classification_state", "DIRECT")),
            security_preservation=d.get("security_preservation", ""),
        )


@dataclass
class ScanResult:
    application_name: str
    root_path: str
    objects: list[SourceObject] = field(default_factory=list)
    sql_files: list[str] = field(default_factory=list)
    python_files: list[str] = field(default_factory=list)
    streamlit_files: list[str] = field(default_factory=list)
    other_files: list[str] = field(default_factory=list)


@dataclass
class DependencyEdge:
    source: str
    target: str
    relationship: str = "DEPENDS_ON"


@dataclass
class MigrationReport:
    application_name: str
    objects: list[MigrationObject] = field(default_factory=list)
    dependency_edges: list[DependencyEdge] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.objects)

    def count(self, mtype: MigrationType) -> int:
        return sum(1 for o in self.objects if o.migration_type == mtype)

    @property
    def coverage_percent(self) -> float:
        if not self.objects:
            return 0.0
        non_manual = sum(1 for o in self.objects if o.migration_type != MigrationType.HIGH_COMPLEXITY)
        return round(100 * non_manual / len(self.objects), 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "application": self.application_name,
            "objects_analyzed": self.total,
            "automated": self.count(MigrationType.AUTOMATED),
            "ai_assisted": self.count(MigrationType.AI_ASSISTED),
            "architecture_redesign": self.count(MigrationType.ARCHITECTURE_REDESIGN),
            "high_complexity": self.count(MigrationType.HIGH_COMPLEXITY),
            "migration_coverage_percent": self.coverage_percent,
            "performance_risks": sum(len(o.performance_risks) for o in self.objects),
            "security_changes": sum(1 for o in self.objects if o.security_notes),
            "manual_review_items": sum(len(o.manual_review) for o in self.objects),
            "objects": [o.to_dict() for o in self.objects],
            "dependencies": [
                {"source": e.source, "target": e.target, "relationship": e.relationship}
                for e in self.dependency_edges
            ],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> MigrationReport:
        objects = [MigrationObject.from_dict(o) for o in d.get("objects", [])]
        edges = []
        for dep in d.get("dependencies", []):
            edges.append(DependencyEdge(source=dep["source"], target=dep["target"], relationship=dep.get("relationship", "DEPENDS_ON")))
        return cls(
            application_name=d.get("application", "unknown"),
            objects=objects,
            dependency_edges=edges
        )
