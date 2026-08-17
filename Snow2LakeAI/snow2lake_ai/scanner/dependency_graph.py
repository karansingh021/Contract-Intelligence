"""
Dependency graph (spec section #6).

Lightweight, deterministic dependency inference: for each migration
object, check whether its generated/source code text references another
known object's name. This is intentionally simple (name matching, not
full semantic analysis) — good enough to drive the UI graph and to warn
when a manual-review object has downstream dependents.
"""

from __future__ import annotations

import re

from snow2lake_ai.models import DependencyEdge, MigrationObject


def build_dependency_graph(objects: list[MigrationObject]) -> list[DependencyEdge]:
    edges: list[DependencyEdge] = []
    names = [o.object_name for o in objects if o.object_name and "::" not in o.object_name]
    # Longer names first so "customers" doesn't false-match inside "customer_secure_view".
    names_sorted = sorted(set(names), key=len, reverse=True)

    for obj in objects:
        haystack = f"{obj.source_file}\n{obj.generated_code}"
        seen_in_this_object: set[str] = set()
        for name in names_sorted:
            if name == obj.object_name:
                continue
            if re.search(rf"\b{re.escape(name)}\b", haystack, re.IGNORECASE):
                if name not in seen_in_this_object:
                    edges.append(DependencyEdge(source=obj.object_name, target=name))
                    seen_in_this_object.add(name)

    return edges
