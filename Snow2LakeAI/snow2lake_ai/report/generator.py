"""
Migration Report generator (spec section #21, #38).

Produces both a JSON report (machine-readable, feeds the Streamlit UI)
and a standalone HTML report. The report explicitly distinguishes
generated code from *validated* code — see rule #38 in the spec: never
claim "100% automatically migrated" unless validation actually passed.
"""

from __future__ import annotations

import json
from pathlib import Path

from snow2lake_ai.models import MigrationReport, MigrationType


def write_json_report(report: MigrationReport, output_path: str) -> str:
    Path(output_path).write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    return output_path


def write_html_report(report: MigrationReport, output_path: str) -> str:
    d = report.to_dict()
    validated_count = sum(1 for o in report.objects if o.validated)

    rows = []
    for obj in report.objects:
        risks = "".join(f"<li>{r.kind}: {r.description}</li>" for r in obj.performance_risks)
        manual = "".join(f"<li>{m}</li>" for m in obj.manual_review)
        warn = "".join(f"<li>{w}</li>" for w in obj.warnings)
        rows.append(f"""
        <tr class="{'validated' if obj.validated else 'not-validated'}">
          <td>{obj.migration_type.emoji}</td>
          <td>{obj.object_name}</td>
          <td>{obj.source_type.value}</td>
          <td>{obj.target_type}</td>
          <td>{obj.migration_type.value}</td>
          <td>{obj.script_percentage}%</td>
          <td>{obj.ai_percentage}%</td>
          <td>{obj.manual_percentage}%</td>
          <td>{obj.confidence:.2f}</td>
          <td>{'✅' if obj.validated else '❌'}</td>
          <td><ul>{risks}</ul></td>
          <td><ul>{warn}</ul></td>
          <td><ul>{manual}</ul></td>
        </tr>""")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Snow2Lake AI Migration Report — {d['application']}</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 2rem; color: #1a1a1a; background: #fafafa; }}
  h1 {{ margin-bottom: 0.2rem; }}
  .subtitle {{ color: #666; margin-top: 0; }}
  .summary {{ display: flex; gap: 1rem; flex-wrap: wrap; margin: 1.5rem 0; }}
  .card {{ background: white; border: 1px solid #e0e0e0; border-radius: 8px; padding: 1rem 1.5rem; min-width: 140px; }}
  .card .n {{ font-size: 1.8rem; font-weight: 700; }}
  .card .label {{ color: #666; font-size: 0.85rem; }}
  table {{ width: 100%; border-collapse: collapse; background: white; font-size: 0.85rem; }}
  th, td {{ border: 1px solid #e0e0e0; padding: 0.5rem; text-align: left; vertical-align: top; }}
  th {{ background: #f0f0f0; position: sticky; top: 0; }}
  tr.not-validated {{ background: #fff6f6; }}
  ul {{ margin: 0; padding-left: 1.1rem; }}
  .disclaimer {{ background: #fff3cd; border: 1px solid #ffe69c; padding: 0.8rem 1rem; border-radius: 6px; margin: 1rem 0; }}
</style>
</head>
<body>
  <h1>Snow2Lake AI — Migration Report</h1>
  <p class="subtitle">Application: <strong>{d['application']}</strong></p>

  <div class="disclaimer">
    <strong>{validated_count} / {d['objects_analyzed']}</strong> objects passed automated validation.
    A migration_type of AUTOMATED or AI_ASSISTED reflects how the code was generated — it is
    <em>not</em> a claim that the migration is production-ready. Only validated objects (green check
    in the table) have passed the validation engine's syntax, performance, and consistency checks.
  </div>

  <div class="summary">
    <div class="card"><div class="n">{d['objects_analyzed']}</div><div class="label">Objects analyzed</div></div>
    <div class="card"><div class="n">🟢 {d['automated']}</div><div class="label">Automated</div></div>
    <div class="card"><div class="n">🟡 {d['ai_assisted']}</div><div class="label">AI-Assisted</div></div>
    <div class="card"><div class="n">🟠 {d['architecture_redesign']}</div><div class="label">Architecture Redesign</div></div>
    <div class="card"><div class="n">🔴 {d['high_complexity']}</div><div class="label">High Complexity</div></div>
    <div class="card"><div class="n">{d['migration_coverage_percent']}%</div><div class="label">Migration coverage</div></div>
    <div class="card"><div class="n">{d['performance_risks']}</div><div class="label">Performance risks</div></div>
    <div class="card"><div class="n">{d['manual_review_items']}</div><div class="label">Manual review items</div></div>
  </div>

  <table>
    <thead>
      <tr>
        <th></th><th>Object</th><th>Source Type</th><th>Target</th><th>Migration Type</th>
        <th>Script %</th><th>AI %</th><th>Manual %</th><th>Confidence</th><th>Validated</th>
        <th>Performance Risks</th><th>Warnings</th><th>Manual Review</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows)}
    </tbody>
  </table>
</body>
</html>
"""
    Path(output_path).write_text(html, encoding="utf-8")
    return output_path
