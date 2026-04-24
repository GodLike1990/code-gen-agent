"""Parallel multi-dimensional checks orchestrator."""
from __future__ import annotations

import asyncio
from typing import Any

from code_gen_agent.checkers.base import CheckerRegistry
from code_gen_agent.graph.base import BaseNode
from code_gen_agent.graph.registry import register_node
from code_gen_agent.graph.state import AgentState


@register_node("checks")
class ChecksNode(BaseNode):
    """Runs all enabled checkers concurrently."""

    DEFAULT_CHECKS = ["lint", "security", "compile", "test", "llm_review"]

    async def run(self, state: AgentState) -> dict[str, Any]:
        files = dict(state.get("generated_files") or {})
        workspace = state.get("workspace_dir") or "."
        enabled = state.get("enable_checks") or self.DEFAULT_CHECKS  # type: ignore[assignment]

        context = {"llm": self.llm, "prompts": self.prompts, "tasks": state.get("tasks") or []}

        async def run_one(name: str):
            cls = CheckerRegistry.get(name)
            inst = cls()
            try:
                return await asyncio.wait_for(inst.run(workspace, files, context), timeout=90)
            except asyncio.TimeoutError:
                from code_gen_agent.checkers.base import CheckResult

                return CheckResult(
                    name=name, passed=False, severity="error", raw_output="checker timeout"
                )

        results = await asyncio.gather(*[run_one(n) for n in enabled])
        serialized = {r.name: r.to_dict() for r in results}
        all_pass = all(r.passed for r in results)

        return {
            "check_results": serialized,
            "events": [{"type": "check_report", "passed": all_pass, "summary": {r.name: r.passed for r in results}}],
        }
