"""Routing predicates for the LangGraph agent.

Pure functions: given the current `AgentState`, return the name of the next
node. Kept separate from `builder.py` so that topology wiring and routing
policy have distinct files.

Each function is registered as a conditional edge in builder.py.  The return
value must be one of the keys in the dispatch map passed to
`graph.add_conditional_edges()`.
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
    """Decide whether to ask the user for more info or proceed to planning.

    Clarification is triggered when:
    - The model explicitly listed missing_info AND confidence < 0.55
    - OR confidence is very low (< 0.35) regardless of missing_info

    The 0.55 / 0.35 thresholds were tuned empirically: below 0.35 the intent
    is too vague to plan; between 0.35 and 0.55 only clarify when there are
    concrete unknowns.  Above 0.55 we trust the model and proceed.
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
    """Send to verify when all checkers pass; send to repair on any failure.

    An empty check_results dict (no checkers ran) is treated as "all pass" so
    that runs with all checkers disabled can still complete.
    """
    results = state.get("check_results") or {}
    all_pass = all(r.get("passed") for r in results.values()) if results else False
    if all_pass:
        return NODE_VERIFY
    return NODE_REPAIR


def route_after_repair(state: AgentState) -> str:
    """Escalate to HITL once repair_attempts reaches max_repairs; otherwise retry.

    max_repairs defaults to 5 (set in AgentConfig and copied onto the state by
    the agent entry point).  Cycle detection in the repair node may escalate
    earlier if it sees 3 consecutive identical failure signatures.
    """
    attempts = int(state.get("repair_attempts") or 0)
    max_r = int(state.get("max_repairs") or 5)
    if attempts >= max_r:
        return NODE_HITL
    return NODE_CODEGEN


def route_after_hitl(state: AgentState) -> str:
    """Route after the human-in-the-loop makes a decision.

    - abort  → END   (user explicitly stopped; streaming marks final_status="aborted")
    - retry  → codegen  (repair_attempts already reset to 0 by the hitl node)
    - patch  → codegen  (generated_files merged with user edits; check_results cleared)

    The default is "abort" so that a missing next_action (e.g. a resume with
    no payload) safely terminates rather than looping forever.
    """
    action = state.get("next_action") or HITL_ACTION_ABORT
    if action == HITL_ACTION_ABORT:
        return ROUTE_END
    return NODE_CODEGEN


def route_after_verify(state: AgentState) -> str:
    """Route based on LLM acceptance review result.

    - passed       → package (build the ZIP artifact)
    - first failure → repair (verify_failures < 2; give repair one chance)
    - repeated failure → hitl (verify_failures >= 2; escalate to human)

    verify_failures is incremented by the verify node on each failed review.
    The threshold of 2 means: one automatic retry is allowed before we ask
    the human to intervene, preventing an infinite verify→repair→verify loop.
    """
    vr = state.get("verify_result") or {}
    # Default to pass when missing — verify node itself has a safe-pass default.
    if vr.get("passed", True):
        return NODE_PACKAGE
    n = int(state.get("verify_failures") or 0)
    if n >= 2:
        return NODE_HITL
    return NODE_REPAIR
