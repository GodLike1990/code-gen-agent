"""ReAct 修复策略节点。"""
from __future__ import annotations

from typing import Any

from code_gen_agent.graph.base import BaseNode
from code_gen_agent.graph.nodes._helpers import call_llm_json
from code_gen_agent.graph.registry import register_node
from code_gen_agent.graph.state import AgentState


@register_node("repair")
class RepairNode(BaseNode):
    """ReAct 修复策略节点 — 分析失败原因并决定修复动作。

    读取 check_results 中的失败信息，调用 LLM 制定修复策略：
    - action="regen"：重新生成目标文件（最常见）
    - action="patch"：对现有文件打补丁
    - action="reclarify"：判断需求本身有歧义，需重新澄清

    循环检测：如果连续 2 轮失败的 checker 集合完全相同，判定陷入死循环，
    强制将 repair_attempts 推到 max_repairs，触发 hitl 升级。

    每次修复完成后更新 state["repair_attempts"] 和 state["repair_history"]，
    下一轮由 codegen 节点按 repair 决策重新生成代码。
    """

    prompt_key = "repair"

    async def run(self, state: AgentState) -> dict[str, Any]:
        attempts = int(state.get("repair_attempts") or 0)
        max_attempts = int(state.get("max_repairs") or 5)
        history = list(state.get("repair_history") or [])
        check_results = state.get("check_results") or {}

        # 截取失败摘要（保留尾部，确保 traceback 不被截断）
        def _tail(raw: str, limit: int = 4000) -> str:
            raw = raw or ""
            if len(raw) <= limit:
                return raw
            return "...[truncated]\n" + raw[-limit:]

        failed = {
            name: {"issues": r.get("issues", [])[:10], "raw": _tail(r.get("raw_output") or "")}
            for name, r in check_results.items()
            if not r.get("passed")
        }

        # 从 issues 中收集失败文件名（去重），回退到全量文件列表
        generated = state.get("generated_files") or {}
        file_set: list[str] = []
        seen: set[str] = set()
        for r in check_results.values():
            if r.get("passed"):
                continue
            for issue in r.get("issues") or []:
                f = issue.get("file") if isinstance(issue, dict) else None
                if f and f not in seen:
                    seen.add(f)
                    file_set.append(f)
        if not file_set:
            file_set = list(generated.keys())

        # 构建有界摘录：每个文件最多 2KB，总量最多 8KB，超过 50KB 的原始文件跳过
        per_file_cap = 2048
        total_cap = 8192
        excerpts: list[str] = []
        used = 0
        for path in file_set:
            content = generated.get(path)
            if not isinstance(content, str):
                continue
            if len(content) > 50_000:
                excerpts.append(f"--- {path} (skipped: >50KB) ---")
                continue
            snippet = content[:per_file_cap]
            if len(content) > per_file_cap:
                snippet += "\n...[truncated]"
            block = f"--- {path} ---\n{snippet}"
            if used + len(block) > total_cap:
                excerpts.append(f"--- {path} (omitted: context full) ---")
                break
            excerpts.append(block)
            used += len(block)
        failing_files = "\n\n".join(excerpts) or "(no file content available)"

        rendered = self.prompts.render(
            "repair",
            user_input=state.get("user_input", "") or "",
            clarifications=state.get("clarifications") or [],
            tasks=state.get("tasks") or [],
            attempt=attempts + 1,
            max_attempts=max_attempts,
            failing_files=failing_files,
            check_results=failed,
            history=history,
        )
        default = {
            "action": "regen",
            "reasoning": "fallback",
            "target_files": [],
            "hint": "",
        }
        decision = await call_llm_json(self.llm, rendered["system"], rendered["user"], default)
        if not isinstance(decision, dict):
            decision = default

        # 循环检测：若最近 2 条历史的失败签名完全相同，则判定死循环，强制升级 hitl
        signature = sorted(failed.keys())
        recent = [h.get("failed_checks") for h in history[-2:]]
        loop_detected = len(recent) >= 2 and all(s == signature for s in recent)
        new_attempts = attempts + 1

        history_entry = {
            "attempt": new_attempts,
            "failed_checks": signature,
            "decision": decision,
        }

        update = {
            "repair_attempts": new_attempts,
            "repair_history": [history_entry],
            "events": [
                {
                    "type": "repair",
                    "attempt": new_attempts,
                    "action": decision.get("action"),
                    "reasoning": decision.get("reasoning"),
                }
            ],
        }
        if loop_detected:
            update["repair_attempts"] = max_attempts  # 强制路由到 hitl
        return update
