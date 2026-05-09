"""节点基类，提供统一的日志记录能力。"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from code_gen_agent.graph.state import AgentState
from code_gen_agent.observability.logger import get_logger
from code_gen_agent.prompts.loader import PromptRegistry

# 纳入节点状态摘要的字段（稳定、低基数）
_SUMMARY_KEYS = (
    "repair_attempts",
    "verify_failures",
    "clarify_questions",
    "user_input",
    "hitl_decision",
    "error",
)


def _state_summary(state: AgentState) -> dict[str, Any]:
    """返回关键状态字段的简洁快照。

    避免转储 generated_files / 完整代码体（可能达 MB 级）。
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
    # 只记录文件数，不含内容
    gf = state.get("generated_files")
    if isinstance(gf, dict):
        summary["file_count"] = len(gf)
    # 记录检查通过/失败汇总
    cr = state.get("check_results")
    if isinstance(cr, dict):
        summary["checks_passed"] = sum(1 for r in cr.values() if (r or {}).get("passed"))
        summary["checks_total"] = len(cr)
    return summary


def _update_summary(update: dict[str, Any]) -> dict[str, Any]:
    """返回节点更新内容的简洁摘要。"""
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
    """抽象节点基类，子类实现 `run` 方法。"""

    #: 注册表中的唯一名称
    name: str = ""
    #: 该节点使用的 prompt key（可选）
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
        # 追加事件供 SSE 流式推送
        events = update.setdefault("events", [])
        events.append(
            {"type": f"node:{self.name}", "duration_ms": duration_ms, "node": self.name}
        )
        return update

    @abstractmethod
    async def run(self, state: AgentState) -> dict[str, Any]:
        """返回局部状态更新字典。"""
