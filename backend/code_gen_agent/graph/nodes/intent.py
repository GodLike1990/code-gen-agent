"""意图识别节点。"""
from __future__ import annotations

from typing import Any

from code_gen_agent.graph.base import BaseNode
from code_gen_agent.graph.nodes._helpers import call_llm_json
from code_gen_agent.graph.registry import register_node
from code_gen_agent.graph.state import AgentState


@register_node("intent")
class IntentNode(BaseNode):
    """意图识别节点 — 图的第一个节点。

    接收用户原始输入，调用 LLM 分析请求类型（code_gen / explain / other）、
    置信度（0~1）和缺失信息列表。

    输出写入 state["intent"]，routing.py 根据 confidence 决定：
    - confidence >= 0.55 → 直接进入 decompose
    - confidence < 0.55 且有 missing_info → 进入 clarify
    - confidence < 0.35 → 直接报错返回
    """

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
