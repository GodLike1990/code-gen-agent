"""需求拆解节点。"""
from __future__ import annotations

from typing import Any

from code_gen_agent.graph.base import BaseNode
from code_gen_agent.graph.nodes._helpers import call_llm_json
from code_gen_agent.graph.registry import register_node
from code_gen_agent.graph.state import AgentState


@register_node("decompose")
class DecomposeNode(BaseNode):
    """需求拆解节点 — 将用户需求分解为文件级任务列表。

    调用 LLM 将意图 + 澄清信息转化为具体的文件计划：
    - language：目标语言（python / go / typescript / java / rust）
    - tasks：每个文件的路径、用途、依赖关系、验收标准

    MVP 约束（prompt 中强制）：2~4 个文件，必须包含测试文件。
    输出写入 state["tasks"] 和 state["language"]，供 codegen 节点使用。
    """

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
