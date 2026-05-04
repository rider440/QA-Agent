from __future__ import annotations
 
import logging
from pathlib import Path
 
from langchain.tools import BaseTool
from pydantic import Field
 
logger = logging.getLogger(__name__)
 
 
class PlaywrightTool(BaseTool):
    """
    LangChain tool that provides on-demand Playwright browser commands.
    """
 
    name: str = "playwright_tool"
    description: str = (
        "Control a headless browser for quick checks during test planning. "
        "Commands:\n"
        "  NAVIGATE <url>  – return page title\n"
        "  SCREENSHOT <url> <output_path>  – save a screenshot\n"
        "  TEXT <url> <css_selector>  – extract element text\n"
        "  CLICK <url> <css_selector>  – click an element\n"
    )
    settings: dict = Field(default_factory=dict)
 
    # ── _run (sync) ───────────────────────────────────────────────────────────
 
    def _run(self, tool_input: str) -> str:  # type: ignore[override]
        try:
            from playwright.sync_api import sync_playwright  # local import
        except ImportError:
            return "ERROR: playwright not installed. Run `playwright install`."
 
        parts = tool_input.strip().split()
        if not parts:
            return "ERROR: empty command."
 
        verb = parts[0].upper()
        headless: bool = self.settings.get("playwright", {}).get("headless", True)
        browser_type: str = self.settings.get("playwright", {}).get("browser", "chromium")
        timeout: int = self.settings.get("playwright", {}).get("timeout_ms", 30_000)
 
        with sync_playwright() as pw:
            browser_launcher = getattr(pw, browser_type)
            browser = browser_launcher.launch(headless=headless)
            page = browser.new_page()
 
            try:
                if verb == "NAVIGATE":
                    url = parts[1] if len(parts) > 1 else ""
                    page.goto(url, timeout=timeout)
                    title = page.title()
                    return f"Page title: {title!r}"
 
                elif verb == "SCREENSHOT":
                    url = parts[1] if len(parts) > 1 else ""
                    out = parts[2] if len(parts) > 2 else "reports/screenshot.png"
                    page.goto(url, timeout=timeout)
                    Path(out).parent.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=out, full_page=True)
                    return f"Screenshot saved to {out}"
 
                elif verb == "TEXT":
                    url = parts[1] if len(parts) > 1 else ""
                    selector = parts[2] if len(parts) > 2 else "body"
                    page.goto(url, timeout=timeout)
                    text = page.locator(selector).inner_text(timeout=5_000)
                    return f"Text: {text[:500]}"
 
                elif verb == "CLICK":
                    url = parts[1] if len(parts) > 1 else ""
                    selector = parts[2] if len(parts) > 2 else ""
                    page.goto(url, timeout=timeout)
                    page.locator(selector).click(timeout=5_000)
                    return f"Clicked '{selector}' on {url}"
 
                else:
                    return f"Unknown command: {verb}"
 
            except Exception as exc:
                return f"ERROR: {exc}"
            finally:
                browser.close()
 
    async def _arun(self, tool_input: str) -> str:  # type: ignore[override]
        # Playwright sync API is fine to call from a thread pool
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._run, tool_input)