from __future__ import annotations
 
import asyncio
import logging
from pathlib import Path
from typing import Any
 
import yaml
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
 
from agent.core.generator import TestGenerator
from agent.core.planner import TestPlanner
from agent.core.reader import CodebaseReader
from agent.memory.context_store import ContextStore
from agent.tools.file_tool import FileTool
from agent.tools.playwright_tool import PlaywrightTool
from agent.tools.report_tool import ReportTool
from agent.tools.test_runner import TestRunner
 
logger = logging.getLogger(__name__)
 
 
# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
 
def _load_settings(config_path: str = "config/settings.yaml") -> dict:
    """Read and return raw YAML settings."""
    with open(config_path, "r") as fh:
        return yaml.safe_load(fh)
 
 
def _build_llm(provider: str, model: str, temperature: float,
               max_tokens: int | None = None, **kwargs) -> BaseChatModel:
    """Instantiate one LLM from settings dict values."""
    if provider == "openai":
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            max_retries=kwargs.get("max_retries", 2),
        )
    elif provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            max_retries=kwargs.get("max_retries", 2),
        )
    elif provider == "grok":
        import os
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            max_retries=kwargs.get("max_retries", 2),
            api_key=os.getenv("GROK_API_KEY"),
            base_url="https://api.x.ai/v1",
        )
    elif provider == "openrouter":
        import os
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            max_retries=kwargs.get("max_retries", 2),
            api_key=os.getenv("OPENROUTER_API_KEY"),
            base_url="https://openrouter.ai/api/v1",
        )
    else:
        raise ValueError(f"Unknown provider: {provider!r}")
 
 
def _build_llm_with_fallbacks(llm_cfg: dict) -> BaseChatModel:
    """
    Build the primary LLM and attach the fallback chain.
 
    LangChain's `.with_fallbacks()` accepts a list of Runnable objects.
    Each one is tried in order if the previous raises any exception.
    """
    retry_attempts = llm_cfg.get("retry_attempts", 2)
    
    primary_cfg = llm_cfg["primary"]
    primary_llm = _build_llm(**primary_cfg, max_retries=retry_attempts)
 
    fallback_llms = [
        _build_llm(**fb_cfg, max_retries=retry_attempts)
        for fb_cfg in llm_cfg.get("fallbacks", [])
    ]
 
    if fallback_llms:
        logger.info(
            "Fallback chain: %s -> %s",
            primary_cfg["model"],
            " -> ".join(f["model"] for f in llm_cfg["fallbacks"]),
        )
        return primary_llm.with_fallbacks(fallback_llms)
 
    return primary_llm
 
 
# ──────────────────────────────────────────────────────────────────────────────
# QAAgent
# ──────────────────────────────────────────────────────────────────────────────
 
class QAAgent:
    """
    High-level QA agent that orchestrates reading, planning, generating and
    running tests against a developer codebase.
    """
 
    def __init__(self, config_path: str = "config/settings.yaml"):
        self.settings = _load_settings(config_path)
        self.llm = _build_llm_with_fallbacks(self.settings["llm"])
        self.context_store = ContextStore()
 
        # Sub-components
        self.reader = CodebaseReader(self.settings["paths"]["project_under_test"])
        self.planner = TestPlanner(self.llm)
        self.generator = TestGenerator(self.llm, self.settings)
 
        # LangChain tools exposed to the ReAct agent
        self.tools = [
            FileTool(settings=self.settings),
            TestRunner(settings=self.settings),
            PlaywrightTool(settings=self.settings),
            ReportTool(settings=self.settings),
        ]
 
        self._agent_executor = self._build_agent_executor()
 
    # ── Private ──────────────────────────────────────────────────────────────
 
    def _build_agent_executor(self):
        """Create a ReAct agent executor with all tools wired in."""
        workflow_prompt_path = Path("agent/prompts/workflow_prompt.txt")
        prompt_text = workflow_prompt_path.read_text()
 
        agent = create_react_agent(
            model=self.llm,
            tools=self.tools,
            prompt=prompt_text,
        )
 
        return agent
 
    # ── Public ───────────────────────────────────────────────────────────────
 
    async def run(self, project_path: str | None = None) -> dict[str, Any]:
        """
        Full pipeline:
          1. Read the codebase.
          2. Plan which tests are needed.
          3. Generate test files.
          4. Execute them and collect results.
          5. Return a summary dict.
        """
        if project_path:
            self.reader.project_path = project_path
 
        logger.info("Step 1/4 - Reading codebase ...")
        codebase_summary = await self.reader.read_async()
        self.context_store.set("codebase_summary", codebase_summary)
 
        logger.info("Step 2/4 - Planning tests ...")
        test_plan = await self.planner.plan(codebase_summary)
        self.context_store.set("test_plan", test_plan)
 
        logger.info("Step 3/4 - Generating test files ...")
        generated_files = await self.generator.generate(test_plan, codebase_summary)
        self.context_store.set("generated_files", generated_files)
 
        logger.info("Step 4/4 - Running agent executor ...")
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self._agent_executor.invoke(
                {
                    "messages": [
                        HumanMessage(content=f"Run all generated tests in {self.settings['paths']['tests_generated']} and produce an HTML + JSON report.")
                    ]
                }
            ),
        )
 
        agent_output = ""
        if "messages" in result and result["messages"]:
            agent_output = result["messages"][-1].content
            
        return {
            "codebase_summary": codebase_summary,
            "test_plan": test_plan,
            "generated_files": generated_files,
            "agent_output": agent_output,
        }