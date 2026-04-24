"""LLM-based code review checker."""
from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from code_gen_agent.checkers.base import CheckResult, Issue, register_checker
from code_gen_agent.graph.nodes._helpers import call_llm_json
from code_gen_agent.prompts.loader import PromptRegistry


@register_checker("llm_review")
class LLMReviewChecker:
    """Requires llm+prompts injected by checks orchestrator via context."""

    name = "llm_review"

    async def run(
        self, workspace: str, files: dict[str, str], context: dict[str, Any] | None = None
    ) -> CheckResult:
        ctx = context or {}
        llm: BaseChatModel | None = ctx.get("llm")
        prompts: PromptRegistry | None = ctx.get("prompts")
        tasks = ctx.get("tasks") or []
        if llm is None or prompts is None:
            return CheckResult(
                name=self.name,
                passed=True,
                severity="info",
                raw_output="llm_review skipped: no LLM context",
            )

        # truncate files to keep context reasonable
        snippet = {p: (c if len(c) < 6000 else c[:6000] + "\n...[truncated]") for p, c in files.items()}
        rendered = prompts.render("llm_review", tasks=tasks, files=snippet)
        default = {"passed": True, "issues": []}
        payload = await call_llm_json(llm, rendered["system"], rendered["user"], default)
        if not isinstance(payload, dict):
            payload = default

        issues = []
        for it in payload.get("issues") or []:
            if not isinstance(it, dict):
                continue
            sev = str(it.get("severity") or "warn")
            if sev not in ("info", "warn", "error"):
                sev = "warn"
            issues.append(
                Issue(
                    file=str(it.get("file") or ""),
                    line=int(it.get("line") or 0),
                    severity=sev,  # type: ignore[arg-type]
                    message=str(it.get("message") or ""),
                )
            )

        passed = bool(payload.get("passed"))
        return CheckResult(
            name=self.name,
            passed=passed,
            severity="error" if not passed else "info",
            issues=issues,
            raw_output="",
        )
