"""Intent recognition node."""
from __future__ import annotations

from typing import Any

from code_gen_agent.graph.base import BaseNode
from code_gen_agent.graph.nodes._helpers import call_llm_json
from code_gen_agent.graph.registry import register_node
from code_gen_agent.graph.state import AgentState


@register_node("intent")
class IntentNode(BaseNode):
    prompt_key = "intent"

    async def run(self, state: AgentState) -> dict[str, Any]:
        rendered = self.prompts.render(
            "intent",
            user_input=state.get("user_input", ""),
            clarifications=state.get("clarifications") or "none",
        )
        default = {
            "type": "other",
            "summary": "",
            "confidence": 0.0,
            "missing_info": ["unable to parse intent"],
        }
        intent = await call_llm_json(self.llm, rendered["system"], rendered["user"], default)
        if not isinstance(intent, dict):
            intent = default
        intent.setdefault("missing_info", [])
        intent.setdefault("confidence", 0.0)
        return {"intent": intent}
