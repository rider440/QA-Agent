from __future__ import annotations
 
import json
import logging
import subprocess
import sys
from pathlib import Path
 
from langchain.tools import BaseTool
from pydantic import Field
 
logger = logging.getLogger(__name__)
 
 
class TestRunner(BaseTool):
    """
    LangChain tool that executes pytest and returns a structured summary.
 
    Input
    ─────
    Either empty (runs all generated tests) or a specific test path:
        "tests_generated/api/test_get_users.py"
    """
 
    name: str = "test_runner"
    description: str = (
        "Run pytest on the generated tests. "
        "Pass a specific test file path or leave empty to run all tests. "
        "Returns a summary of passed / failed / error counts and failure details."
    )
    settings: dict = Field(default_factory=dict)
 
    def _run(self, tool_input: str = "") -> str:  # type: ignore[override]
        test_path = tool_input.strip() or self.settings.get("paths", {}).get(
            "tests_generated", "tests_generated"
        )
        report_path = (
            Path(self.settings.get("paths", {}).get("reports", "reports"))
            / "latest_report.json"
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)
 
        cmd = [
            sys.executable, "-m", "pytest",
            test_path,
            "--json-report",
            f"--json-report-file={report_path}",
            "-q",
            "--tb=short",
            "--no-header",
        ]
        logger.info("TestRunner: %s", " ".join(cmd))
 
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )
 
        # Parse the JSON report for a structured summary
        try:
            report = json.loads(report_path.read_text())
            summary = report.get("summary", {})
            passed = summary.get("passed", 0)
            failed = summary.get("failed", 0)
            errors = summary.get("error", 0)
            total = summary.get("total", 0)
 
            failure_lines: list[str] = []
            for test in report.get("tests", []):
                if test.get("outcome") in ("failed", "error"):
                    failure_lines.append(
                        f"  FAIL: {test['nodeid']}\n"
                        f"       {test.get('call', {}).get('longrepr', '')[:300]}"
                    )
 
            return (
                f"pytest results: {passed}/{total} passed, "
                f"{failed} failed, {errors} errors.\n"
                + ("\n".join(failure_lines) if failure_lines else "All tests passed!")
            )
        except Exception:
            # Fallback to raw stdout
            return result.stdout[-3000:] or result.stderr[-1000:]
 
    async def _arun(self, tool_input: str = "") -> str:  # type: ignore[override]
        return self._run(tool_input)