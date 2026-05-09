"""AgentState：图的共享状态。"""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class AgentState(TypedDict, total=False):
    # 输入
    user_input: str
    thread_id: str
    workspace_dir: str

    # 意图与澄清
    intent: dict[str, Any] | None
    clarifications: list[dict[str, Any]]
    clarify_questions: list[str]

    # 规划
    language: str
    tasks: list[dict[str, Any]]

    # 生成
    generated_files: dict[str, str]

    # 检查
    check_results: dict[str, Any]

    # 修复
    repair_attempts: int
    max_repairs: int
    repair_history: Annotated[list[dict[str, Any]], operator.add]

    # 路由
    next_action: str
    escalated: bool
    hitl_decision: dict[str, Any] | None

    # 语义验收 + 最终产物
    verify_result: dict[str, Any] | None
    verify_failures: int
    artifact: dict[str, Any] | None

    # 可观测性
    events: Annotated[list[dict[str, Any]], operator.add]


def initial_state(user_input: str, thread_id: str, workspace_dir: str, max_repairs: int) -> AgentState:
    return AgentState(
        user_input=user_input,
        thread_id=thread_id,
        workspace_dir=workspace_dir,
        intent=None,
        clarifications=[],
        clarify_questions=[],
        language="",
        tasks=[],
        generated_files={},
        check_results={},
        repair_attempts=0,
        max_repairs=max_repairs,
        repair_history=[],
        next_action="",
        escalated=False,
        hitl_decision=None,
        verify_result=None,
        verify_failures=0,
        artifact=None,
        events=[],
    )
