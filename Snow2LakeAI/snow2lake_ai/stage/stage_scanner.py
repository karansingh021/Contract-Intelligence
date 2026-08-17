from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from snow2lake_ai.connectors.snowflake_client import SnowflakeStageClient

SUPPORTED = {".sql", ".py", ".yml", ".yaml", ".json", ".toml", ".md", ".txt"}
IGNORE = {".git", "__pycache__", ".venv", "venv", "node_modules", ".idea"}


def pull_stage_to_local(client: SnowflakeStageClient, stage: str, work_dir: str, prefix: str = "") -> Path:
    root = Path(work_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    client.download_stage(stage, str(root), prefix=prefix)
    # GET may create a nested directory for stage paths; find the first useful source root.
    return root


def scan_downloaded_stage(root: str, stage_ref: str) -> dict[str, Any]:
    base = Path(root).resolve()
    files: list[dict[str, Any]] = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in IGNORE and not d.startswith(".")]
        for name in filenames:
            p = Path(dirpath) / name
            rel = str(p.relative_to(base))
            ext = p.suffix.lower()
            if ext not in SUPPORTED and name != "manifest.yml":
                continue
            try:
                text = p.read_text(errors="ignore")
            except Exception:
                text = ""
            kind = "config"
            if ext == ".sql":
                kind = "sql"
            elif ext == ".py":
                kind = "streamlit" if any(x in text for x in ("import streamlit", "from streamlit", "st.title(")) else "python"
            files.append({
                "path": rel,
                "stage_path": stage_ref.rstrip("/") + "/" + rel.replace(os.sep, "/"),
                "extension": ext,
                "kind": kind,
                "size": p.stat().st_size,
                "content": text,
            })
    return {
        "root": str(base),
        "stage": stage_ref,
        "files": files,
        "counts": {
            "total": len(files),
            "sql": sum(f["kind"] == "sql" for f in files),
            "python": sum(f["kind"] == "python" for f in files),
            "streamlit": sum(f["kind"] == "streamlit" for f in files),
            "config": sum(f["kind"] == "config" for f in files),
        },
    }
