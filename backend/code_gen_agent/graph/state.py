"""AgentState: the graph's shared state."""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class AgentState(TypedDict, total=False):
    # input
    user_input: str
    thread_id: str
    workspace_dir: str

    # intent & clarification
    intent: dict[str, Any] | None
    clarifications: list[dict[str, Any]]
    clarify_questions: list[str]

    # planning
    language: str
    tasks: list[dict[str, Any]]

    # generation
    generated_files: dict[str, str]

    # checks
    check_results: dict[str, Any]

    # repair
    repair_attempts: int
    max_repairs: int
    repair_history: Annotated[list[dict[str, Any]], operator.add]

    # routing
    next_action: str
    escalated: bool
    hitl_decision: dict[str, Any] | None

    # verify (semantic requirement check) + final artifact
    verify_result: dict[str, Any] | None
    verify_failures: int
    artifact: dict[str, Any] | None

    # observability
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
