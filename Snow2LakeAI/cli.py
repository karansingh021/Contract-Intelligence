#!/usr/bin/env python3
"""
Snow2Lake AI — CLI entrypoint.

Usage:
    python cli.py --input sample_snowflake_app --output out/

Runs the full vertical-slice pipeline: scan -> deterministic + AI-assisted
migration -> validation -> generated Databricks project + report.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from snow2lake_ai.orchestrator import run_migration
from snow2lake_ai.report.generator import write_html_report, write_json_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Snow2Lake AI — Snowflake to Databricks migration accelerator")
    parser.add_argument("--input", required=True, help="Path to a Snowflake application directory or .zip file")
    parser.add_argument("--output", required=True, help="Directory to write the generated Databricks project + report")
    parser.add_argument("--name", default=None, help="Application name (defaults to the input folder name)")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[snow2lake-ai] Scanning and migrating: {args.input}")
    report = run_migration(args.input, str(output_dir), application_name=args.name)

    json_path = write_json_report(report, str(output_dir / "migration_report.json"))
    html_path = write_html_report(report, str(output_dir / "migration_report.html"))

    d = report.to_dict()
    print()
    print("=" * 60)
    print(" SNOW2LAKE AI MIGRATION REPORT")
    print("=" * 60)
    print(f" Application:            {d['application']}")
    print(f" Objects analyzed:       {d['objects_analyzed']}")
    print(f" 🟢 Automated:            {d['automated']}")
    print(f" 🟡 AI-assisted:          {d['ai_assisted']}")
    print(f" 🟠 Architecture redesign:{d['architecture_redesign']}")
    print(f" 🔴 High complexity:      {d['high_complexity']}")
    print(f" Migration coverage:     {d['migration_coverage_percent']}%")
    print(f" Performance risks:      {d['performance_risks']}")
    print(f" Security changes:       {d['security_changes']}")
    print(f" Manual review items:    {d['manual_review_items']}")
    print("=" * 60)
    print(f" JSON report: {json_path}")
    print(f" HTML report: {html_path}")
    print(f" Generated project: {output_dir}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
