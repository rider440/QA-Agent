from __future__ import annotations
 
import logging
import os
import re
from pathlib import Path
from typing import AsyncIterator
 
import aiofiles
 
logger = logging.getLogger(__name__)
 
# File extensions worth reading
READABLE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx",
    ".html", ".css",
    ".json", ".yaml", ".yml",
    ".md", ".txt",
}
 
# Patterns that suggest an API route definition
ROUTE_PATTERNS = [
    # Flask / FastAPI
    r'@(?:app|router)\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)',
    # Express.js
    r'(?:app|router)\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)',
]
 
MAX_FILE_BYTES = 8_192  # 8 KB per file
 
 
class CodebaseReader:
    """
    Scans `project_path` and produces a human-readable summary for the LLM.
    """
 
    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
 
    # ── Private ──────────────────────────────────────────────────────────────
 
    def _iter_source_files(self) -> list[Path]:
        """Return all readable source files under project_path."""
        files: list[Path] = []
        for root, dirs, filenames in os.walk(self.project_path):
            # Skip common noise directories
            dirs[:] = [
                d for d in dirs
                if d not in {"node_modules", ".git", "__pycache__", ".venv", "venv", "dist", "build"}
            ]
            for fname in filenames:
                fpath = Path(root) / fname
                if fpath.suffix in READABLE_EXTENSIONS:
                    files.append(fpath)
        return sorted(files)
 
    @staticmethod
    def _detect_routes(content: str) -> list[str]:
        """Extract API route signatures from source content."""
        routes: list[str] = []
        for pattern in ROUTE_PATTERNS:
            for match in re.finditer(pattern, content, re.MULTILINE):
                method, path = match.group(1).upper(), match.group(2)
                routes.append(f"{method} {path}")
        return routes
 
    def _build_tree(self, files: list[Path]) -> str:
        """Build a compact directory tree string."""
        lines: list[str] = [str(self.project_path)]
        for f in files:
            rel = f.relative_to(self.project_path)
            depth = len(rel.parts) - 1
            indent = "  " * depth
            lines.append(f"{indent}└─ {rel.name}")
        return "\n".join(lines)
 
    # ── Public ───────────────────────────────────────────────────────────────
 
    async def read_async(self) -> str:
        """
        Asynchronously read the codebase and return a summary string.
        """
        if not self.project_path.exists():
            logger.warning("project_path %s does not exist – using empty summary.", self.project_path)
            return "No project codebase found."
 
        source_files = self._iter_source_files()
        logger.info("Reader: found %d source files.", len(source_files))
 
        tree = self._build_tree(source_files)
        all_routes: list[str] = []
        file_snippets: list[str] = []
 
        for fpath in source_files:
            try:
                async with aiofiles.open(fpath, "r", errors="replace") as fh:
                    content = await fh.read(MAX_FILE_BYTES)
                routes = self._detect_routes(content)
                all_routes.extend(routes)
                rel = fpath.relative_to(self.project_path)
                file_snippets.append(
                    f"### {rel}\n```\n{content[:2000]}\n```"
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("Could not read %s: %s", fpath, exc)
 
        summary_parts = [
            "## Directory Structure",
            tree,
            "\n## Detected API Routes",
            "\n".join(f"  - {r}" for r in sorted(set(all_routes))) or "  (none detected)",
            "\n## Source File Snippets",
            "\n\n".join(file_snippets[:20]),  # cap at 20 files for context budget
        ]
        return "\n".join(summary_parts)