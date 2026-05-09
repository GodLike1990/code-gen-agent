"""从注册节点组装 LangGraph StateGraph。

图拓扑
──────
下方 GRAPH_TOPOLOGY 常量具有双重用途：
1. 是所有节点 id 和边标签的权威定义。
2. 被序列化后由 GET /agent/graph/schema 返回，
   供前端 ReactFlow 画布无需硬编码即可渲染实时图形。

任何拓扑变更（增减节点、修改边）都必须在此处以及
build_graph() 中的 add_node / add_edge 调用中同步更新。
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


# 静态拓扑描述 — 同时供前端图形可视化使用（GET /agent/graph/schema）
# 节点 id 必须与 build_graph() 中 add_node() 的键一致，
# 边的 source/target 必须是有效节点 id 或特殊哨兵 "__start__" / "__end__"
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
    """返回静态拓扑供前端可视化使用。"""
    return GRAPH_TOPOLOGY


def build_graph(
    llm: BaseChatModel,
    prompts: PromptRegistry,
    checkpointer: Any,
    enabled_nodes: list[str] | None = None,
):
    """实例化注册节点并构建已编译的 LangGraph。

    Args:
        llm: 传递给每个节点的共享聊天模型实例。
        prompts: 已加载的 prompt 注册表（YAML 模板）。
        checkpointer: LangGraph 状态持久化后端。
        enabled_nodes: 可选的节点名称白名单。提供时仅添加列表中的节点，
            不在注册表中的名称会抛出 RuntimeError。传入 None 则启用所有节点。
            注意：禁用必要节点将产生不完整的图，运行时可能抛出异常，
            仅用于测试局部流程。
    """
    # 确保所有内置节点在检查前已导入并注册
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

    # 实例化所有（或白名单内）节点，注入共享的 llm/prompts
    node_instances = {}
    for name in required:
        if enabled_nodes is not None and name not in enabled_nodes:
            continue
        cls = NodeRegistry.get(name)
        node_instances[name] = cls(llm=llm, prompts=prompts)
        graph.add_node(name, node_instances[name])

    # 连接拓扑 — 必须与上方 GRAPH_TOPOLOGY 的边保持一致
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
