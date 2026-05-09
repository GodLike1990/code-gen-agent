"""HITL 升级节点 — 修复耗尽后暂停等待人工决策。"""
from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

from code_gen_agent.graph.base import BaseNode
from code_gen_agent.graph.registry import register_node
from code_gen_agent.graph.state import AgentState


@register_node("hitl")
class HitlNode(BaseNode):
    """人工介入节点 — 修复次数耗尽或 verify 多次失败后升级给人工处理。

    调用 LangGraph interrupt() 暂停执行，将失败摘要（尝试次数、失败 checker、
    文件列表、verify 发现的语义 gap）推送前端，等待用户决策：

    - action="retry"：允许再修复一轮（重置 repair_attempts）
    - action="patch"：用户直接提供修改后的文件内容，跳过 LLM 修复
    - action="abort"：终止整个 run，routing 路由到 END

    决策结果写入 state["hitl_decision"] 和 state["next_action"]，
    routing.py 的 route_after_hitl() 根据 next_action 分发后续流程。
    """
    async def run(self, state: AgentState) -> dict[str, Any]:
        verify = state.get("verify_result") or {}
        summary = {
            "attempts": state.get("repair_attempts"),
            "failed_checks": [
                name
                for name, r in (state.get("check_results") or {}).items()
                if not r.get("passed")
            ],
            "files": list((state.get("generated_files") or {}).keys()),
            "history": state.get("repair_history") or [],
            # 若因语义验收失败升级到此，将 gap 详情突出显示，让用户看到真实原因
            "verify_gaps": verify.get("gaps") or [],
            "verify_reasoning": verify.get("reasoning") or "",
        }

        decision = interrupt({"type": "hitl", "summary": summary})

        # decision 格式：{"action": "retry"|"patch"|"abort", "hint": str, "files": {path: content}}
        if not isinstance(decision, dict):
            decision = {"action": "abort"}
        action = decision.get("action", "abort")

        updates: dict[str, Any] = {
            "hitl_decision": decision,
            "escalated": True,
            "next_action": action,
            "events": [{"type": "hitl_decision", "action": action}],
        }

        if action == "retry":
            # 允许再修复一轮
            updates["repair_attempts"] = max(0, int(state.get("max_repairs") or 3) - 1)
        elif action == "patch":
            # 用户直接提供文件内容，合并后重置检查结果
            patched = dict(state.get("generated_files") or {})
            for path, content in (decision.get("files") or {}).items():
                if isinstance(path, str) and isinstance(content, str):
                    patched[path] = content
            updates["generated_files"] = patched
            updates["check_results"] = {}
            updates["repair_attempts"] = 0
        # abort：无需额外修改状态，路由器直接发送到 END
        return updates
