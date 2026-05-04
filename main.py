from __future__ import annotations
 
import argparse
import asyncio
import logging
import sys
from pathlib import Path
 
# Load .env before anything else so API keys are available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv optional in minimal installs
 
from agent.core.agent import QAAgent
 
 
# ── CLI argument parsing ───────────────────────────────────────────────────────
 
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="QA Agent – automatically generate and run tests for a codebase.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples
────────
  # Run with defaults (reads config/settings.yaml)
  python main.py
 
  # Point at a different project
  python main.py --project ./my_flask_app
 
  # Debug mode
  python main.py --log-level DEBUG
        """,
    )
    parser.add_argument(
        "--config",
        default="config/settings.yaml",
        help="Path to settings.yaml  (default: config/settings.yaml)",
    )
    parser.add_argument(
        "--project",
        default=None,
        help="Override the project_under_test path from settings.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO)",
    )
    return parser.parse_args()
 
 
# ── Logging setup ──────────────────────────────────────────────────────────────
 
def configure_logging(level: str, log_dir: str = "reports/logs") -> None:
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    log_file = Path(log_dir) / "qa_agent.log"
 
    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, encoding="utf-8"),
    ]
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s [%(levelname)-8s] %(name)s – %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )
 
 
# ── Main coroutine ─────────────────────────────────────────────────────────────
 
async def main() -> int:
    """Return exit code: 0 = all tests pass, 1 = failures or errors."""
    args = parse_args()
    configure_logging(args.log_level)
 
    logger = logging.getLogger("main")
    logger.info("=" * 60)
    logger.info("QA Agent starting ...")
    logger.info("Config : %s", args.config)
    logger.info("Project: %s", args.project or "(from settings.yaml)")
    logger.info("=" * 60)
 
    agent = QAAgent(config_path=args.config)
 
    try:
        result = await agent.run(project_path=args.project)
    except Exception as exc:
        logger.error("Fatal error: %s", exc)
        return 1
 
    logger.info("=" * 60)
    logger.info("QA Agent finished.")
    logger.info("Generated files : %s", result.get("generated_files", []))
    logger.info("Agent output    : %s", result.get("agent_output", "")[:500])
    logger.info("=" * 60)
 
    # Exit 1 if the agent output mentions failures
    output: str = result.get("agent_output", "").lower()
    if "failed" in output and "0 failed" not in output:
        return 1
    return 0
 
 
# ── Entry point ───────────────────────────────────────────────────────────────
 
if __name__ == "__main__":
    sys.exit(asyncio.run(main()))