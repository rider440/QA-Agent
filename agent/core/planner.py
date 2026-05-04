from __future__ import annotations
 
import json
import logging
from pathlib import Path
from typing import Any
 
from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
 
from agent.prompts.System_promt import System_Prompt
 
logger = logging.getLogger(__name__)
 
 
# ──────────────────────────────────────────────────────────────────────────────
# Data models
# ──────────────────────────────────────────────────────────────────────────────
 
class APITestCase(BaseModel):
    """A single API endpoint test to be generated."""
    endpoint: str = Field(..., description="HTTP path, e.g. /api/users")
    method: str = Field(..., description="HTTP verb: GET | POST | PUT | DELETE")
    description: str = Field(..., description="What this test verifies")
    expected_status: int = Field(200, description="Expected HTTP status code")
    payload: dict[str, Any] = Field(default_factory=dict)
 
 
class UITestCase(BaseModel):
    """A single Playwright UI test to be generated."""
    page: str = Field(..., description="URL path of the page to test")
    action: str = Field(..., description="User action to simulate")
    assertion: str = Field(..., description="What to assert after the action")
 
 
class TestPlan(BaseModel):
    """Complete test plan returned by the Planner."""
    api_tests: list[APITestCase] = Field(default_factory=list)
    ui_tests: list[UITestCase] = Field(default_factory=list)
    summary: str = ""
 
 
# ──────────────────────────────────────────────────────────────────────────────
# Planner
# ──────────────────────────────────────────────────────────────────────────────
 
class TestPlanner:
    """
    Uses an LLM to analyse the codebase summary and produce a `TestPlan`.
    """
 
    SYSTEM_PROMPT = (
        f"{System_Prompt}\n\n"
        "---"
        "\n\n### 💡 PLANNER INSTRUCTIONS\n"
        "As the Planner, your job is to analyze the codebase summary and produce a structured JSON test plan.\n"
        "The JSON MUST have the following keys:\n"
        "  • api_tests  – list of API endpoint tests\n"
        "  • ui_tests   – list of Playwright UI tests\n"
        "  • summary    – one-paragraph description of your plan\n\n"
        "Return ONLY valid JSON, no markdown fences. "
        "Ignore the 'OUTPUT FORMAT' section in the rules above for this specific task, "
        "as you are generating the input for the next agent."
    )
 
    def __init__(self, llm: BaseChatModel):
        self.llm = llm
        self._prompt_template = self._load_prompt()
        self._chain = (
            ChatPromptTemplate.from_messages(
                [
                    ("system", self.SYSTEM_PROMPT),
                    ("human", "{codebase_summary}"),
                ]
            )
            | self.llm.with_structured_output(TestPlan)
        )
 
    # ── Private ──────────────────────────────────────────────────────────────
 
    @staticmethod
    def _load_prompt() -> str:
        path = Path("agent/prompts/api_analysis_prompt.txt")
        if path.exists():
            return path.read_text()
        return ""  # fallback: rely on SYSTEM_PROMPT
 
    # ── Public ───────────────────────────────────────────────────────────────
 
    async def plan(self, codebase_summary: str) -> TestPlan:
        """
        Invoke the LLM chain and parse the response into a `TestPlan`.
 
        The `.with_fallbacks()` on the underlying LLM means this call
        silently retries on transient provider errors.
        """
        logger.info("Planner: invoking LLM to build test plan …")
        plan: TestPlan = await self._chain.ainvoke(
            {"codebase_summary": codebase_summary}
        )
        logger.debug("Planner raw output: %s", plan.model_dump_json(indent=2))
        logger.info(
            "Planner: %d API tests + %d UI tests planned.",
            len(plan.api_tests),
            len(plan.ui_tests),
        )
        return plan