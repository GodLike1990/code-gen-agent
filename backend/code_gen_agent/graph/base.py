"""Base class for agent nodes with automatic logging."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from code_gen_agent.graph.state import AgentState
from code_gen_agent.observability.logger import get_logger
from code_gen_agent.prompts.loader import PromptRegistry

# Keys to include in the node state summary (stable, low-cardinality).
_SUMMARY_KEYS = (
    "repair_attempts",
    "verify_failures",
    "clarify_questions",
    "user_input",
    "hitl_decision",
    "error",
)


def _state_summary(state: AgentState) -> dict[str, Any]:
    """Return a concise, safe snapshot of key state fields.

    Avoids dumping generated_files / full code bodies which can be MB-sized.
    """
    summary: dict[str, Any] = {}
    for key in _SUMMARY_KEYS:
        val = state.get(key)
        if val is None:
            continue
        if isinstance(val, str):
            summary[key] = val[:200]
        elif isinstance(val, list):
            summary[key] = len(val)
        else:
            summary[key] = val
    # Add file count without content.
    gf = state.get("generated_files")
    if isinstance(gf, dict):
        summary["file_count"] = len(gf)
    # Add check pass/fail summary.
    cr = state.get("check_results")
    if isinstance(cr, dict):
        summary["checks_passed"] = sum(1 for r in cr.values() if (r or {}).get("passed"))
        summary["checks_total"] = len(cr)
    return summary


def _update_summary(update: dict[str, Any]) -> dict[str, Any]:
    """Return concise summary of what a node update contains."""
    summary: dict[str, Any] = {}
    for key in _SUMMARY_KEYS:
        val = update.get(key)
        if val is None:
            continue
        if isinstance(val, str):
            summary[key] = val[:200]
        elif isinstance(val, list):
            summary[key] = len(val)
        else:
            summary[key] = val
    gf = update.get("generated_files")
    if isinstance(gf, dict):
        summary["file_count"] = len(gf)
    return summary


class BaseNode(ABC):
    """Abstract node. Subclasses implement `run`."""

    #: unique registry name
    name: str = ""
    #: prompt key this node uses (optional)
    prompt_key: str | None = None

    def __init__(self, llm: BaseChatModel, prompts: PromptRegistry) -> None:
        self.llm = llm
        self.prompts = prompts
        self.log = get_logger(self.name or self.__class__.__name__)

    async def __call__(self, state: AgentState) -> dict[str, Any]:
        thread_id = state.get("thread_id", "")
        start = time.perf_counter()
        self.log.info(
            "node_enter",
            extra={
                "thread_id": thread_id,
                "node": self.name,
                "event": "enter",
                "state_summary": _state_summary(state),
            },
        )
        try:
            update = await self.run(state)
        except Exception as e:
            self.log.exception(
                "node_error",
                extra={"thread_id": thread_id, "node": self.name, "event": "error"},
            )
            raise e
        duration_ms = int((time.perf_counter() - start) * 1000)
        self.log.info(
            "node_exit",
            extra={
                "thread_id": thread_id,
                "node": self.name,
                "event": "exit",
                "duration_ms": duration_ms,
                "update_summary": _update_summary(update),
            },
        )
        # append event for SSE streaming
        events = update.setdefault("events", [])
        events.append(
            {"type": f"node:{self.name}", "duration_ms": duration_ms, "node": self.name}
        )
        return update

    @abstractmethod
    async def run(self, state: AgentState) -> dict[str, Any]:
        """Return a partial state update dict."""
