"""Tests for graph builder and registry."""
from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver

from code_gen_agent.graph import NodeRegistry, build_graph, get_graph_schema
from code_gen_agent.prompts import PromptRegistry


def test_schema_contains_all_nodes() -> None:
    schema = get_graph_schema()
    ids = {n["id"] for n in schema["nodes"]}
    assert {"intent", "clarify", "decompose", "codegen", "checks", "repair", "hitl"} <= ids


def test_registry_has_all_builtin_nodes() -> None:
    import code_gen_agent.graph.nodes  # noqa: F401

    for name in ("intent", "clarify", "decompose", "codegen", "checks", "repair", "hitl"):
        assert name in NodeRegistry.names()


def test_build_graph_compiles() -> None:
    class _FakeLLM:
        pass

    graph = build_graph(
        llm=_FakeLLM(),  # type: ignore[arg-type]
        prompts=PromptRegistry(),
        checkpointer=MemorySaver(),
    )
    assert graph is not None
