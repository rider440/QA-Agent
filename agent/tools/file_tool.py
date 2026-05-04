from __future__ import annotations
 
import logging
from pathlib import Path
 
from langchain.tools import BaseTool
from pydantic import Field
 
logger = logging.getLogger(__name__)
 
 
class FileTool(BaseTool):
    """
    LangChain tool for reading and writing files inside the project workspace.
 
    Input format (plain string)
    ───────────────────────────
    READ <path>
    WRITE <path>\n<content…>
    LIST <directory>
    """
 
    name: str = "file_tool"
    description: str = (
        "Read or write files in the project workspace. "
        "To read:  'READ <relative_path>'. "
        "To write: 'WRITE <relative_path>\\n<file_content>'. "
        "To list:  'LIST <directory_path>'."
    )
    settings: dict = Field(default_factory=dict)
 
    def _run(self, tool_input: str) -> str:  # type: ignore[override]
        parts = tool_input.strip().split("\n", 1)
        command_line = parts[0].strip()
        rest = parts[1] if len(parts) > 1 else ""
 
        tokens = command_line.split(" ", 1)
        verb = tokens[0].upper()
        path_str = tokens[1].strip() if len(tokens) > 1 else ""
 
        if verb == "READ":
            return self._read(path_str)
        elif verb == "WRITE":
            return self._write(path_str, rest)
        elif verb == "LIST":
            return self._list(path_str)
        else:
            return f"Unknown command '{verb}'. Use READ, WRITE, or LIST."
 
    async def _arun(self, tool_input: str) -> str:  # type: ignore[override]
        return self._run(tool_input)
 
    # ── Helpers ───────────────────────────────────────────────────────────────
 
    @staticmethod
    def _read(path_str: str) -> str:
        path = Path(path_str)
        if not path.exists():
            return f"ERROR: File not found: {path}"
        try:
            return path.read_text(errors="replace")
        except Exception as exc:
            return f"ERROR reading {path}: {exc}"
 
    @staticmethod
    def _write(path_str: str, content: str) -> str:
        path = Path(path_str)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            logger.info("FileTool wrote %s (%d bytes)", path, len(content))
            return f"OK: Wrote {len(content)} bytes to {path}"
        except Exception as exc:
            return f"ERROR writing {path}: {exc}"
 
    @staticmethod
    def _list(path_str: str) -> str:
        path = Path(path_str)
        if not path.exists():
            return f"ERROR: Directory not found: {path}"
        entries = sorted(path.rglob("*"))
        lines = [str(e.relative_to(path)) for e in entries if e.is_file()]
        return "\n".join(lines) if lines else "(empty)"