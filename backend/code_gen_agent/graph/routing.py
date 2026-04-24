"""Routing predicates for the LangGraph agent.

Pure functions: given the current `AgentState`, return the name of the next
node. Kept separate from `builder.py` so that topology wiring and routing
policy have distinct files.
"""
from __future__ import annotations

from code_gen_agent.graph.state import AgentState


def route_after_intent(state: AgentState) -> str:
    intent = state.get("intent") or {}
    missing = intent.get("missing_info") or []
    confidence = float(intent.get("confidence") or 0.0)
    # Only clarify when signal is strong: either the model explicitly listed
    # missing_info AND confidence is not high, or confidence is very low.
    if missing and confidence < 0.55:
        return "clarify"
    if confidence < 0.35:
        return "clarify"
    return "decompose"


def route_after_checks(state: AgentState) -> str:
    results = state.get("check_results") or {}
    all_pass = all(r.get("passed") for r in results.values()) if results else False
    if all_pass:
        return "verify"
    return "repair"


def route_after_repair(state: AgentState) -> str:
    attempts = int(state.get("repair_attempts") or 0)
    max_r = int(state.get("max_repairs") or 5)
    if attempts >= max_r:
        return "hitl"
    return "codegen"


def route_after_verify(state: AgentState) -> str:
    vr = state.get("verify_result") or {}
    # Default to pass when missing — verify node itself has a safe-pass default.
    if vr.get("passed", True):
        return "package"
    # First verify failure: give repair one chance with gaps as context.
    # Second or later failures: escalate to HITL.
    n = int(state.get("verify_failures") or 0)
    if n >= 2:
        return "hitl"
    return "repair"
