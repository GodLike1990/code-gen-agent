"""HITL escalation node — pauses for human decision after repair exhaustion."""
from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

from code_gen_agent.graph.base import BaseNode
from code_gen_agent.graph.registry import register_node
from code_gen_agent.graph.state import AgentState


@register_node("hitl")
class HitlNode(BaseNode):
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
            # If we landed here because the semantic verifier flagged gaps,
            # surface them prominently so the human sees the real reason.
            "verify_gaps": verify.get("gaps") or [],
            "verify_reasoning": verify.get("reasoning") or "",
        }

        decision = interrupt({"type": "hitl", "summary": summary})

        # decision may be {"action": "retry"|"patch"|"abort", "hint": str, "files": {path: content}}
        if not isinstance(decision, dict):
            decision = {"action": "abort"}
        action = decision.get("action", "abort")

        updates: dict[str, Any] = {
            "hitl_decision": decision,
            "escalated": True,
            "events": [{"type": "hitl_decision", "action": action}],
        }

        if action == "retry":
            # allow one more round of repairs
            updates["repair_attempts"] = max(0, int(state.get("max_repairs") or 3) - 1)
        elif action == "patch":
            # user provided files directly — merge them and reset checks
            patched = dict(state.get("generated_files") or {})
            for path, content in (decision.get("files") or {}).items():
                if isinstance(path, str) and isinstance(content, str):
                    patched[path] = content
            updates["generated_files"] = patched
            updates["check_results"] = {}
            updates["repair_attempts"] = 0
        elif action == "abort":
            updates["check_results"] = {
                "_aborted": {"passed": True, "severity": "info", "raw_output": "aborted by user"}
            }
        return updates
