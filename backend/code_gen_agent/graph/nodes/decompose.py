"""Requirement decomposition node."""
from __future__ import annotations

from typing import Any

from code_gen_agent.graph.base import BaseNode
from code_gen_agent.graph.nodes._helpers import call_llm_json
from code_gen_agent.graph.registry import register_node
from code_gen_agent.graph.state import AgentState


@register_node("decompose")
class DecomposeNode(BaseNode):
    prompt_key = "decompose"

    async def run(self, state: AgentState) -> dict[str, Any]:
        rendered = self.prompts.render(
            "decompose",
            intent=state.get("intent") or {},
            clarifications=state.get("clarifications") or [],
        )
        default = {"language": "python", "tasks": []}
        payload = await call_llm_json(self.llm, rendered["system"], rendered["user"], default)
        if not isinstance(payload, dict):
            payload = default

        tasks_raw = payload.get("tasks") or []
        tasks: list[dict[str, Any]] = []
        for t in tasks_raw:
            if not isinstance(t, dict):
                continue
            path = str(t.get("path") or "").strip()
            if not path:
                continue
            tasks.append(
                {
                    "path": path,
                    "purpose": str(t.get("purpose") or ""),
                    "deps": list(t.get("deps") or []),
                    "acceptance": str(t.get("acceptance") or ""),
                }
            )
        return {
            "language": str(payload.get("language") or "python"),
            "tasks": tasks,
        }
