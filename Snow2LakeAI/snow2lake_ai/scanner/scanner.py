"""
Application Scanner (spec section #5).

Walks a Snowflake application directory (or an extracted ZIP) and
classifies every file by type. Does NOT assume a fixed folder layout —
`.sql` files are treated as SQL wherever they live, `.py` files are
inspected for Snowpark/Streamlit signatures rather than trusted by
folder name alone.
"""

from __future__ import annotations

import os
import zipfile
import tempfile
from pathlib import Path

from snow2lake_ai.models import ScanResult

SQL_EXTENSIONS = {".sql"}
PYTHON_EXTENSIONS = {".py"}
CONFIG_EXTENSIONS = {".yml", ".yaml", ".json", ".toml"}

IGNORE_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", ".idea"}


def _is_streamlit_file(text: str) -> bool:
    markers = ("import streamlit", "from streamlit", "st.title(", "st.button(", "st.selectbox(")
    return any(m in text for m in markers)


def scan_application(input_path: str, application_name: str | None = None) -> ScanResult:
    """Accepts either a directory or a .zip file path."""
    path = Path(input_path)

    if path.is_file() and path.suffix.lower() == ".zip":
        tmp_dir = tempfile.mkdtemp(prefix="snow2lake_")
        with zipfile.ZipFile(path, "r") as zf:
            zf.extractall(tmp_dir)
        root = Path(tmp_dir)
    elif path.is_dir():
        root = path
    else:
        raise ValueError(f"input_path must be a directory or a .zip file, got: {input_path}")

    app_name = application_name or root.name
    result = ScanResult(application_name=app_name, root_path=str(root))

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.startswith(".")]
        for fname in filenames:
            fpath = Path(dirpath) / fname
            rel = str(fpath.relative_to(root))
            suffix = fpath.suffix.lower()

            if suffix in SQL_EXTENSIONS:
                result.sql_files.append(rel)
            elif suffix in PYTHON_EXTENSIONS:
                try:
                    text = fpath.read_text(errors="ignore")
                except Exception:
                    text = ""
                if _is_streamlit_file(text):
                    result.streamlit_files.append(rel)
                else:
                    result.python_files.append(rel)
            elif fname == "manifest.yml" or suffix in CONFIG_EXTENSIONS:
                result.other_files.append(rel)
            else:
                result.other_files.append(rel)

    return result
