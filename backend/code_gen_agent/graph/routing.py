"""LangGraph 路由谓词函数。

纯函数：接受当前 AgentState，返回下一个节点名称。
与 builder.py 分离，使拓扑连线和路由策略各司其职。

每个函数在 builder.py 中注册为条件边。
返回值必须是传给 graph.add_conditional_edges() 的 dispatch map 中的某个键。
"""
from __future__ import annotations

from code_gen_agent.graph.constants import (
    HITL_ACTION_ABORT,
    NODE_CLARIFY,
    NODE_CODEGEN,
    NODE_DECOMPOSE,
    NODE_HITL,
    NODE_PACKAGE,
    NODE_REPAIR,
    NODE_VERIFY,
    ROUTE_END,
)
from code_gen_agent.graph.state import AgentState


def route_after_intent(state: AgentState) -> str:
    """决定是向用户补充信息还是直接进入规划阶段。

    触发澄清的条件：
    - 模型明确列出 missing_info 且 confidence < 0.55
    - 或 confidence < 0.35（无论是否有 missing_info）

    阈值 0.55 / 0.35 经验调优：低于 0.35 意图过于模糊无法规划；
    0.35~0.55 之间仅在有具体未知项时才澄清；高于 0.55 直接信任模型推进。
    """
    intent = state.get("intent") or {}
    missing = intent.get("missing_info") or []
    confidence = float(intent.get("confidence") or 0.0)
    if missing and confidence < 0.55:
        return NODE_CLARIFY
    if confidence < 0.35:
        return NODE_CLARIFY
    return NODE_DECOMPOSE


def route_after_checks(state: AgentState) -> str:
    """全部通过则进入 verify，任一失败则进入 repair。

    check_results 为空（未运行任何 checker）视为"全部通过"，
    确保禁用所有 checker 时流程仍能正常完成。
    """
    results = state.get("check_results") or {}
    all_pass = all(r.get("passed") for r in results.values()) if results else False
    if all_pass:
        return NODE_VERIFY
    return NODE_REPAIR


def route_after_repair(state: AgentState) -> str:
    """repair_attempts 达到 max_repairs 时升级 HITL，否则重试。

    max_repairs 默认为 5（由 AgentConfig 设置并写入 state）。
    repair 节点的循环检测可能在此之前更早触发升级。
    """
    attempts = int(state.get("repair_attempts") or 0)
    max_r = int(state.get("max_repairs") or 5)
    if attempts >= max_r:
        return NODE_HITL
    return NODE_CODEGEN


def route_after_hitl(state: AgentState) -> str:
    """根据人工决策结果路由。

    - abort  → END（用户主动终止，流式层将 final_status 标为 "aborted"）
    - retry  → codegen（hitl 节点已重置 repair_attempts 为 0）
    - patch  → codegen（generated_files 已合并用户编辑，check_results 已清空）

    默认为 "abort"，防止 next_action 缺失时（如无 payload 的 resume）陷入死循环。
    """
    action = state.get("next_action") or HITL_ACTION_ABORT
    if action == HITL_ACTION_ABORT:
        return ROUTE_END
    return NODE_CODEGEN


def route_after_verify(state: AgentState) -> str:
    """根据 LLM 验收结果路由。

    - passed       → package（生成 ZIP 产物）
    - 首次失败     → repair（verify_failures < 2，给 repair 一次机会）
    - 多次失败     → hitl（verify_failures >= 2，升级人工介入）

    verify 节点每次失败都会递增 verify_failures。
    阈值 2 意味着允许一次自动重试，之后交由人工处理，
    防止 verify→repair→verify 死循环。
    """
    vr = state.get("verify_result") or {}
    # verify 节点本身有安全通过默认值，缺失时默认通过
    if vr.get("passed", True):
        return NODE_PACKAGE
    n = int(state.get("verify_failures") or 0)
    if n >= 2:
        return NODE_HITL
    return NODE_REPAIR
