"""Assemble a LangGraph StateGraph from registered nodes.

GRAPH TOPOLOGY
──────────────
The GRAPH_TOPOLOGY constant below serves dual purpose:
1. It is the authoritative definition of every node id and edge label.
2. It is serialised and returned by GET /agent/graph/schema so the frontend
   ReactFlow canvas can render the live graph without any hard-coding.

Any topology change (add/remove node, change edge) must be reflected here
*and* in the actual add_node / add_edge calls in build_graph().
"""
from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import END, START, StateGraph

from code_gen_agent.graph.constants import (
    NODE_CHECKS,
    NODE_CLARIFY,
    NODE_CODEGEN,
    NODE_DECOMPOSE,
    NODE_HITL,
    NODE_INTENT,
    NODE_PACKAGE,
    NODE_REPAIR,
    NODE_VERIFY,
    ROUTE_END,
)
from code_gen_agent.graph.registry import NodeRegistry
from code_gen_agent.graph.routing import (
    route_after_checks,
    route_after_hitl,
    route_after_intent,
    route_after_repair,
    route_after_verify,
)
from code_gen_agent.graph.state import AgentState
from code_gen_agent.prompts.loader import PromptRegistry


# Static topology description — also consumed by the frontend graph visualisation
# via GET /agent/graph/schema.  Node ids here must match the add_node() keys
# in build_graph(), and edge sources/targets must be valid node ids or the
# special sentinels "__start__" / "__end__".
GRAPH_TOPOLOGY: dict[str, Any] = {
    "nodes": [
        {"id": NODE_INTENT,    "label": "Intent"},
        {"id": NODE_CLARIFY,   "label": "Clarify (HITL)"},
        {"id": NODE_DECOMPOSE, "label": "Decompose"},
        {"id": NODE_CODEGEN,   "label": "Code Gen"},
        {"id": NODE_CHECKS,    "label": "Checks"},
        {"id": NODE_REPAIR,    "label": "Repair"},
        {"id": NODE_HITL,      "label": "HITL Escalation"},
        {"id": NODE_VERIFY,    "label": "Verify (acceptance)"},
        {"id": NODE_PACKAGE,   "label": "Package (zip)"},
    ],
    "edges": [
        {"source": "__start__",  "target": NODE_INTENT},
        {"source": NODE_INTENT,  "target": NODE_CLARIFY,  "label": "need info"},
        {"source": NODE_INTENT,  "target": NODE_DECOMPOSE, "label": "ok"},
        {"source": NODE_CLARIFY, "target": NODE_INTENT},
        {"source": NODE_DECOMPOSE, "target": NODE_CODEGEN},
        {"source": NODE_CODEGEN,   "target": NODE_CHECKS},
        {"source": NODE_CHECKS,    "target": NODE_VERIFY,  "label": "all pass"},
        {"source": NODE_CHECKS,    "target": NODE_REPAIR,  "label": "fail"},
        {"source": NODE_REPAIR,    "target": NODE_CODEGEN, "label": "attempts<max"},
        {"source": NODE_REPAIR,    "target": NODE_HITL,    "label": "attempts>=max"},
        {"source": NODE_HITL,      "target": NODE_CODEGEN, "label": "retry/patch"},
        {"source": NODE_HITL,      "target": "__end__",    "label": "abort"},
        {"source": NODE_VERIFY,    "target": NODE_PACKAGE, "label": "accepted"},
        {"source": NODE_VERIFY,    "target": NODE_REPAIR,  "label": "gaps (retry)"},
        {"source": NODE_VERIFY,    "target": NODE_HITL,    "label": "gaps persist"},
        {"source": NODE_PACKAGE,   "target": "__end__"},
    ],
}


def get_graph_schema() -> dict[str, Any]:
    """Return the static topology for the frontend visualisation."""
    return GRAPH_TOPOLOGY


def build_graph(
    llm: BaseChatModel,
    prompts: PromptRegistry,
    checkpointer: Any,
    enabled_nodes: list[str] | None = None,
):
    """Instantiate registered nodes and build the compiled LangGraph.

    Args:
        llm: Shared chat model instance passed to every node.
        prompts: Loaded prompt registry (YAML templates).
        checkpointer: LangGraph state persistence backend.
        enabled_nodes: Optional allowlist of node names.  When provided, only
            nodes in this list are added to the graph; any name not in the
            registry raises RuntimeError.  Pass None to enable all nodes.
            Note: disabling required nodes will produce an incomplete graph
            that may raise at runtime — use only for testing partial flows.
    """
    # Ensure all built-in nodes are imported/registered before checking.
    import code_gen_agent.graph.nodes  # noqa: F401

    required = [
        NODE_INTENT,
        NODE_CLARIFY,
        NODE_DECOMPOSE,
        NODE_CODEGEN,
        NODE_CHECKS,
        NODE_REPAIR,
        NODE_HITL,
        NODE_VERIFY,
        NODE_PACKAGE,
    ]
    missing = [n for n in required if n not in NodeRegistry.names()]
    if missing:
        raise RuntimeError(f"missing nodes in registry: {missing}")

    graph = StateGraph(AgentState)

    # Instantiate all (or allowed) nodes with shared llm/prompts.
    node_instances = {}
    for name in required:
        if enabled_nodes is not None and name not in enabled_nodes:
            continue
        cls = NodeRegistry.get(name)
        node_instances[name] = cls(llm=llm, prompts=prompts)
        graph.add_node(name, node_instances[name])

    # Wire topology — must mirror GRAPH_TOPOLOGY edges above.
    graph.add_edge(START, NODE_INTENT)
    graph.add_conditional_edges(
        NODE_INTENT, route_after_intent,
        {NODE_CLARIFY: NODE_CLARIFY, NODE_DECOMPOSE: NODE_DECOMPOSE},
    )
    graph.add_edge(NODE_CLARIFY, NODE_INTENT)
    graph.add_edge(NODE_DECOMPOSE, NODE_CODEGEN)
    graph.add_edge(NODE_CODEGEN, NODE_CHECKS)
    graph.add_conditional_edges(
        NODE_CHECKS, route_after_checks,
        {NODE_VERIFY: NODE_VERIFY, NODE_REPAIR: NODE_REPAIR},
    )
    graph.add_conditional_edges(
        NODE_REPAIR, route_after_repair,
        {NODE_CODEGEN: NODE_CODEGEN, NODE_HITL: NODE_HITL},
    )
    graph.add_conditional_edges(
        NODE_HITL, route_after_hitl,
        {NODE_CODEGEN: NODE_CODEGEN, ROUTE_END: END},
    )
    graph.add_conditional_edges(
        NODE_VERIFY, route_after_verify,
        {NODE_PACKAGE: NODE_PACKAGE, NODE_REPAIR: NODE_REPAIR, NODE_HITL: NODE_HITL},
    )
    graph.add_edge(NODE_PACKAGE, END)

    return graph.compile(checkpointer=checkpointer)
