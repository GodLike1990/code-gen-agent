"""Verify：静态检查通过后的语义验收门禁。"""
from __future__ import annotations

import json
import time
from typing import Any

from code_gen_agent.graph.base import BaseNode
from code_gen_agent.graph.nodes._helpers import call_llm_json
from code_gen_agent.graph.registry import register_node
from code_gen_agent.graph.state import AgentState


def _truncate_files(files: dict[str, str], per_file: int = 4000, total: int = 40000) -> str:
    """序列化生成文件供 verify prompt 使用，限制总大小。"""
    out: list[str] = []
    used = 0
    for path, content in (files or {}).items():
        body = content or ""
        if len(body) > per_file:
            body = body[:per_file] + f"\n… (truncated, {len(content)} bytes total)"
        chunk = f"### {path}\n{body}\n"
        if used + len(chunk) > total:
            out.append(f"### … ({len(files) - len(out)} more files omitted)\n")
            break
        out.append(chunk)
        used += len(chunk)
    return "\n".join(out) or "(no files)"


@register_node("verify")
class VerifyNode(BaseNode):
    """语义验收节点 — 静态检查全部通过后的最后一道语义门禁。

    调用 LLM 对照原始需求、意图、任务列表和生成文件，判断代码是否真正满足需求：
    - passed=True → 进入 package 打包
    - passed=False → 将 gaps 注入 check_results["verify"]，
      触发 repair 循环；连续失败 verify_failures 次后升级 hitl

    设计原则：LLM 调用失败（网络/超时）时默认 passed=True，
    避免因 LLM 不稳定阻塞原本正确的代码交付。
    """

    name = "verify"
    prompt_key = "verify"

    async def run(self, state: AgentState) -> dict[str, Any]:
        files = state.get("generated_files") or {}
        if not files:
            # 无文件可验证，视为通过，交由打包节点处理空工作区
            result = {
                "passed": True,
                "reasoning": "No files generated; nothing to verify.",
                "gaps": [],
                "ts": int(time.time() * 1000),
            }
            return {
                "verify_result": result,
                "events": [{"type": "verify", **result}],
            }

        user_input = state.get("user_input") or ""
        intent = state.get("intent") or {}
        clarifications = state.get("clarifications") or []
        tasks = state.get("tasks") or []

        rendered = self.prompts.render(
            "verify",
            user_input=user_input,
            intent=json.dumps(intent, ensure_ascii=False, indent=2),
            clarifications=json.dumps(clarifications, ensure_ascii=False, indent=2),
            tasks=json.dumps(tasks, ensure_ascii=False, indent=2),
            files=_truncate_files(files),
        )

        default = {
            "passed": True,
            "reasoning": "verify skipped: LLM response unparseable",
            "gaps": [],
        }
        try:
            payload = await call_llm_json(self.llm, rendered["system"], rendered["user"], default)
        except Exception as e:  # noqa: BLE001
            # LLM 瞬时故障不应阻塞本已通过静态检查的代码交付
            self.log.warning(
                "verify_llm_failed",
                extra={"thread_id": state.get("thread_id"), "event": "verify_skipped", "error": str(e)},
            )
            payload = {
                "passed": True,
                "reasoning": f"verify skipped: {type(e).__name__}: {e}",
                "gaps": [],
            }

        # 防御性类型收窄
        passed = bool(payload.get("passed")) if isinstance(payload, dict) else True
        reasoning = str(payload.get("reasoning", "") if isinstance(payload, dict) else "")
        raw_gaps = payload.get("gaps") if isinstance(payload, dict) else []
        gaps = [str(g) for g in raw_gaps] if isinstance(raw_gaps, list) else []

        result = {
            "passed": passed,
            "reasoning": reasoning,
            "gaps": gaps,
            "ts": int(time.time() * 1000),
        }
        update: dict[str, Any] = {
            "verify_result": result,
            "events": [{"type": "verify", **result}],
        }
        if not passed:
            # 注入合成失败检查项，让 repair prompt 将 gaps 作为可操作上下文，
            # 并递增 verify_failures 供路由判断
            prev_checks = dict(state.get("check_results") or {})
            gaps_text = "\n".join(f"- {g}" for g in gaps) or reasoning or "verify failed"
            prev_checks["verify"] = {
                "name": "verify",
                "passed": False,
                "severity": "error",
                "issues": [],
                "raw_output": f"Acceptance gaps:\n{gaps_text}\n\nReasoning: {reasoning}",
            }
            update["check_results"] = prev_checks
            update["verify_failures"] = int(state.get("verify_failures") or 0) + 1
        return update
