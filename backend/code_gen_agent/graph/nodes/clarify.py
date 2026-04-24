"""Interactive clarification node using LangGraph interrupt()."""
from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

from code_gen_agent.graph.base import BaseNode
from code_gen_agent.graph.nodes._helpers import call_llm_json
from code_gen_agent.graph.registry import register_node
from code_gen_agent.graph.state import AgentState


@register_node("clarify")
class ClarifyNode(BaseNode):
    prompt_key = "clarify"

    async def run(self, state: AgentState) -> dict[str, Any]:
        intent = state.get("intent") or {}
        missing = intent.get("missing_info") or []

        # 1) produce up to 3 clarifying questions
        rendered = self.prompts.render(
            "clarify", intent=intent, missing_info=missing
        )
        default = {"questions": missing[:3] or ["Please provide more details."]}
        payload = await call_llm_json(self.llm, rendered["system"], rendered["user"], default)
        questions = payload.get("questions") if isinstance(payload, dict) else None
        if not isinstance(questions, list) or not questions:
            questions = default["questions"]
        questions = [str(q) for q in questions[:3]]

        # 2) interrupt to wait for human answers
        answers = interrupt(
            {
                "type": "clarify",
                "questions": questions,
                "intent": intent,
            }
        )

        # 3) persist answers back into state
        if isinstance(answers, dict):
            answer_list = answers.get("answers") or []
        elif isinstance(answers, list):
            answer_list = answers
        else:
            answer_list = [str(answers)]

        new_clarifications = [
            {"question": q, "answer": a}
            for q, a in zip(questions, answer_list, strict=False)
        ]
        existing = list(state.get("clarifications") or [])
        existing.extend(new_clarifications)
        return {
            "clarifications": existing,
            "clarify_questions": questions,
        }
