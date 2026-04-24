"""End-to-end graph flow test with a mocked LLM."""
from __future__ import annotations

import json
from typing import Any

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver

from code_gen_agent.graph import build_graph
from code_gen_agent.graph.state import initial_state
from code_gen_agent.prompts import PromptRegistry


class FakeLLM:
    """Scripted LLM returning pre-baked JSON responses by call index."""

    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.calls = 0

    async def ainvoke(self, messages, **kwargs):
        if not self._responses:
            content = "{}"
        else:
            r = self._responses.pop(0)
            content = r if isinstance(r, str) else json.dumps(r)
        self.calls += 1
        return AIMessage(content=content)


@pytest.mark.asyncio
async def test_happy_path_generates_and_passes(tmp_path) -> None:
    responses = [
        # intent
        {"type": "new_project", "summary": "hello", "confidence": 0.9, "missing_info": []},
        # decompose
        {
            "language": "python",
            "tasks": [{"path": "hello.py", "purpose": "print hello", "deps": [], "acceptance": "prints"}],
        },
        # codegen
        {"files": [{"path": "hello.py", "content": "print('hello')\n"}]},
        # llm_review (invoked by LLMReviewChecker)
        {"passed": True, "issues": []},
    ]
    llm = FakeLLM(responses)
    graph = build_graph(llm=llm, prompts=PromptRegistry(), checkpointer=MemorySaver())  # type: ignore[arg-type]

    workspace = tmp_path / "ws"
    workspace.mkdir()
    state = initial_state("hi", "t-1", str(workspace), max_repairs=3)

    final = None
    async for chunk in graph.astream(
        state, config={"configurable": {"thread_id": "t-1"}, "recursion_limit": 30}
    ):
        final = chunk

    assert final is not None
    # generated file exists
    assert (workspace / "hello.py").exists()
