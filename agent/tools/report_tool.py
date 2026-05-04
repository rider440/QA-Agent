from __future__ import annotations
 
import json
import logging
from datetime import datetime
from pathlib import Path
 
from jinja2 import Template
from langchain.tools import BaseTool
from pydantic import Field
 
logger = logging.getLogger(__name__)
 
# ── Embedded HTML template ────────────────────────────────────────────────────
 
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>QA Agent Report – {{ generated_at }}</title>
<style>
  body { font-family: system-ui, sans-serif; margin: 2rem; background: #f9fafb; color: #111; }
  h1   { color: #1d4ed8; }
  .badge { display: inline-block; padding: .2rem .6rem; border-radius: 9999px; font-size: .8rem; font-weight: 700; }
  .pass { background: #d1fae5; color: #065f46; }
  .fail { background: #fee2e2; color: #991b1b; }
  .skip { background: #fef9c3; color: #713f12; }
  table { border-collapse: collapse; width: 100%; margin-top: 1rem; }
  th, td { border: 1px solid #e5e7eb; padding: .5rem .75rem; text-align: left; }
  th { background: #eff6ff; }
  pre  { background: #1e1e2e; color: #cdd6f4; padding: 1rem; border-radius: .5rem; overflow-x: auto; font-size: .8rem; }
</style>
</head>
<body>
<h1>🤖 QA Agent Test Report</h1>
<p>Generated: <strong>{{ generated_at }}</strong></p>
 
<h2>Summary</h2>
<p>
  <span class="badge pass">✅ Passed: {{ summary.passed }}</span>&nbsp;
  <span class="badge fail">❌ Failed: {{ summary.failed }}</span>&nbsp;
  <span class="badge skip">⏭ Skipped: {{ summary.skipped }}</span>&nbsp;
  Total: {{ summary.total }}
</p>
 
<h2>Test Results</h2>
<table>
  <tr><th>Test</th><th>Outcome</th><th>Duration (s)</th></tr>
  {% for t in tests %}
  <tr>
    <td>{{ t.nodeid }}</td>
    <td><span class="badge {{ 'pass' if t.outcome == 'passed' else 'fail' }}">{{ t.outcome }}</span></td>
    <td>{{ "%.3f"|format(t.duration) }}</td>
  </tr>
  {% endfor %}
</table>
 
{% if failures %}
<h2>Failure Details</h2>
{% for f in failures %}
<h3>{{ f.nodeid }}</h3>
<pre>{{ f.longrepr }}</pre>
{% endfor %}
{% endif %}
 
</body>
</html>"""
 
 
class ReportTool(BaseTool):
    """
    LangChain tool that generates HTML and JSON reports from pytest output.
 
    Input
    ─────
    "GENERATE"  –  read latest_report.json and write latest_report.html
    """
 
    name: str = "report_tool"
    description: str = (
        "Generate an HTML test report from pytest results. "
        "Input: 'GENERATE'. Reads reports/latest_report.json and writes "
        "reports/latest_report.html."
    )
    settings: dict = Field(default_factory=dict)
 
    def _run(self, tool_input: str = "GENERATE") -> str:  # type: ignore[override]
        reports_dir = Path(self.settings.get("paths", {}).get("reports", "reports"))
        json_path = reports_dir / "latest_report.json"
        html_path = reports_dir / "latest_report.html"
 
        if not json_path.exists():
            return f"ERROR: {json_path} not found. Run tests first."
 
        try:
            report = json.loads(json_path.read_text())
        except json.JSONDecodeError as exc:
            return f"ERROR: Could not parse {json_path}: {exc}"
 
        tests = report.get("tests", [])
        summary = report.get("summary", {})
        summary.setdefault("passed", 0)
        summary.setdefault("failed", 0)
        summary.setdefault("skipped", 0)
        summary.setdefault("total", len(tests))
 
        failures = [
            {
                "nodeid": t["nodeid"],
                "longrepr": t.get("call", {}).get("longrepr", ""),
            }
            for t in tests
            if t.get("outcome") in ("failed", "error")
        ]
 
        rendered = Template(HTML_TEMPLATE).render(
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            summary=summary,
            tests=tests,
            failures=failures,
        )
 
        html_path.write_text(rendered)
        logger.info("ReportTool: wrote %s", html_path)
 
        return (
            f"Report generated: {html_path}\n"
            f"Summary: {summary['passed']} passed / "
            f"{summary['failed']} failed / "
            f"{summary['total']} total."
        )
 
    async def _arun(self, tool_input: str = "GENERATE") -> str:  # type: ignore[override]
        return self._run(tool_input)