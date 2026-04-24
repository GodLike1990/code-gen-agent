"""Assemble a LangGraph StateGraph from registered nodes."""
from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import END, START, StateGraph

from code_gen_agent.graph.registry import NodeRegistry
from code_gen_agent.graph.routing import (
    route_after_checks,
    route_after_intent,
    route_after_repair,
    route_after_verify,
)
from code_gen_agent.graph.state import AgentState
from code_gen_agent.prompts.loader import PromptRegistry


# Static topology description (also used by the frontend graph page).
GRAPH_TOPOLOGY: dict[str, Any] = {
    "nodes": [
        {"id": "intent", "label": "Intent"},
        {"id": "clarify", "label": "Clarify (HITL)"},
        {"id": "decompose", "label": "Decompose"},
        {"id": "codegen", "label": "Code Gen"},
        {"id": "checks", "label": "Checks"},
        {"id": "repair", "label": "Repair"},
        {"id": "hitl", "label": "HITL Escalation"},
        {"id": "verify", "label": "Verify (acceptance)"},
        {"id": "package", "label": "Package (zip)"},
    ],
    "edges": [
        {"source": "__start__", "target": "intent"},
        {"source": "intent", "target": "clarify", "label": "need info"},
        {"source": "intent", "target": "decompose", "label": "ok"},
        {"source": "clarify", "target": "intent"},
        {"source": "decompose", "target": "codegen"},
        {"source": "codegen", "target": "checks"},
        {"source": "checks", "target": "verify", "label": "all pass"},
        {"source": "checks", "target": "repair", "label": "fail"},
        {"source": "repair", "target": "codegen", "label": "attempts<max"},
        {"source": "repair", "target": "hitl", "label": "attempts>=max"},
        {"source": "hitl", "target": "codegen"},
        {"source": "verify", "target": "package", "label": "accepted"},
        {"source": "verify", "target": "repair", "label": "gaps (retry)"},
        {"source": "verify", "target": "hitl", "label": "gaps persist"},
        {"source": "package", "target": "__end__"},
    ],
}


def get_graph_schema() -> dict[str, Any]:
    """Return the static topology for the frontend visualization."""
    return GRAPH_TOPOLOGY


def build_graph(
    llm: BaseChatModel,
    prompts: PromptRegistry,
    checkpointer: Any,
    enabled_nodes: list[str] | None = None,
):
    """Instantiate registered nodes and build the LangGraph.

    `enabled_nodes` lets callers disable nodes by name; unknown names raise.
    """
    # Ensure all built-in nodes are imported/registered.
    import code_gen_agent.graph.nodes  # noqa: F401

    required = [
        "intent",
        "clarify",
        "decompose",
        "codegen",
        "checks",
        "repair",
        "hitl",
        "verify",
        "package",
    ]
    missing = [n for n in required if n not in NodeRegistry.names()]
    if missing:
        raise RuntimeError(f"missing nodes in registry: {missing}")

    graph = StateGraph(AgentState)

    # Instantiate all nodes with shared llm/prompts
    node_instances = {}
    for name in required:
        if enabled_nodes is not None and name not in enabled_nodes:
            continue
        cls = NodeRegistry.get(name)
        node_instances[name] = cls(llm=llm, prompts=prompts)
        graph.add_node(name, node_instances[name])

    # Wire topology
    graph.add_edge(START, "intent")
    graph.add_conditional_edges(
        "intent", route_after_intent, {"clarify": "clarify", "decompose": "decompose"}
    )
    graph.add_edge("clarify", "intent")
    graph.add_edge("decompose", "codegen")
    graph.add_edge("codegen", "checks")
    graph.add_conditional_edges(
        "checks", route_after_checks, {"verify": "verify", "repair": "repair"}
    )
    graph.add_conditional_edges(
        "repair", route_after_repair, {"codegen": "codegen", "hitl": "hitl"}
    )
    graph.add_edge("hitl", "codegen")
    graph.add_conditional_edges(
        "verify", route_after_verify, {"package": "package", "repair": "repair", "hitl": "hitl"}
    )
    graph.add_edge("package", END)

    return graph.compile(checkpointer=checkpointer)
