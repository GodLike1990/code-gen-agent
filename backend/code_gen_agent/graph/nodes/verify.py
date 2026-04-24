"""Verify: semantic requirement acceptance gate after static checks pass."""
from __future__ import annotations

import json
import time
from typing import Any

from code_gen_agent.graph.base import BaseNode
from code_gen_agent.graph.nodes._helpers import call_llm_json
from code_gen_agent.graph.registry import register_node
from code_gen_agent.graph.state import AgentState


def _truncate_files(files: dict[str, str], per_file: int = 4000, total: int = 40000) -> str:
    """Serialize generated files for the verify prompt, bounded in size."""
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
    name = "verify"
    prompt_key = "verify"

    async def run(self, state: AgentState) -> dict[str, Any]:
        files = state.get("generated_files") or {}
        if not files:
            # Nothing to verify — treat as pass, let packaging handle the empty case.
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
            # Transient LLM failures should NOT gate delivery of otherwise-passing code.
            self.log.warning(
                "verify_llm_failed",
                extra={"thread_id": state.get("thread_id"), "event": "verify_skipped", "error": str(e)},
            )
            payload = {
                "passed": True,
                "reasoning": f"verify skipped: {type(e).__name__}: {e}",
                "gaps": [],
            }

        # Coerce shape defensively.
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
            # Inject a synthetic failing check so repair prompt receives gaps as
            # actionable context, and bump verify_failures for routing.
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
