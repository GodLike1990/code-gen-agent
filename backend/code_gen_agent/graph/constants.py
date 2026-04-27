"""Central string constants for the agent graph, API, and streaming layers.

Having all literals in one place means:
- A single grep shows every usage
- Typos produce NameError instead of silent wrong behaviour
- The SSE contract between backend and frontend is visible at a glance

BACKEND ↔ FRONTEND CONTRACT
────────────────────────────
The EVENT_* and STATUS_* constants here are mirrored in the frontend at
  frontend/src/constants/events.ts   (SSE_EVENT object)
  frontend/src/constants/status.ts   (RUN_STATUS_* objects)
Any rename here must be accompanied by a matching change on the frontend side.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Graph node names
# Must match the string keys passed to StateGraph.add_node() in builder.py.
# ---------------------------------------------------------------------------
NODE_INTENT    = "intent"
NODE_CLARIFY   = "clarify"
NODE_DECOMPOSE = "decompose"
NODE_CODEGEN   = "codegen"
NODE_CHECKS    = "checks"
NODE_REPAIR    = "repair"
NODE_HITL      = "hitl"
NODE_VERIFY    = "verify"
NODE_PACKAGE   = "package"

# Ordered pipeline — useful for iteration and documentation only.
ALL_NODES = [
    NODE_INTENT, NODE_CLARIFY, NODE_DECOMPOSE, NODE_CODEGEN,
    NODE_CHECKS, NODE_REPAIR, NODE_HITL, NODE_VERIFY, NODE_PACKAGE,
]

# ---------------------------------------------------------------------------
# HITL decision actions
# Set by the hitl node on AgentState["next_action"]; consumed by route_after_hitl.
# Frontend sends these in the ResumeRequest.human_feedback["action"] field.
# ---------------------------------------------------------------------------
HITL_ACTION_RETRY = "retry"   # Reset repair_attempts and re-run codegen
HITL_ACTION_PATCH = "patch"   # Merge user-provided files, re-run checks
HITL_ACTION_ABORT = "abort"   # Route to END; streaming marks final_status="aborted"

# ---------------------------------------------------------------------------
# Routing targets returned by routing.py functions
# These are the string keys in the conditional-edge dispatch maps in builder.py.
# ---------------------------------------------------------------------------
ROUTE_END      = "end"
ROUTE_CODEGEN  = NODE_CODEGEN
ROUTE_REPAIR   = NODE_REPAIR
ROUTE_HITL     = NODE_HITL
ROUTE_CLARIFY  = NODE_CLARIFY
ROUTE_DECOMPOSE = NODE_DECOMPOSE
ROUTE_VERIFY   = NODE_VERIFY
ROUTE_PACKAGE  = NODE_PACKAGE

# ---------------------------------------------------------------------------
# SSE event types emitted by streaming.py
# The frontend subscribes to GET /agent/runs/{tid}/events and dispatches on
# these names.  See frontend/src/constants/events.ts for the mirror.
# ---------------------------------------------------------------------------
EVENT_STATE_DELTA   = "state_delta"    # Emitted after every node update; triggers state poll
EVENT_INTERRUPT     = "interrupt"      # Generic LangGraph interrupt (clarify or hitl)
EVENT_CLARIFY       = "clarify"        # Agent needs clarification from the user
EVENT_HITL          = "hitl"           # Agent escalated to human-in-the-loop
EVENT_HITL_DECISION = "hitl_decision"  # HITL node recorded user's action
EVENT_DONE          = "done"           # Run finished (carries final_status in data)
EVENT_ERROR         = "error"          # Unhandled exception during execution
# Node-level events use prefix + node name, e.g. "node:intent", "node:codegen"
EVENT_NODE_PREFIX   = "node:"

# ---------------------------------------------------------------------------
# Run final_status values
# Written to RequestStore by streaming.py and returned in the "done" SSE event.
# The frontend RequirementRecord.status union must include all of these values.
#
# Mapping to frontend RunStatus:
#   STATUS_INTERRUPTED → RunStatus "hitl"  (frontend alias for HITL pause)
#   STATUS_RUNNING     → RunStatus "running"
#   all others         → same name
# ---------------------------------------------------------------------------
STATUS_RUNNING     = "running"
STATUS_DONE        = "done"
STATUS_INTERRUPTED = "interrupted"  # Agent paused at interrupt(); waiting for human input
STATUS_ABORTED     = "aborted"      # User explicitly stopped the run via HITL abort action
STATUS_CANCELLED   = "cancelled"    # Client disconnected mid-stream (CancelledError)
STATUS_FAILED      = "failed"       # Unhandled exception; agent could not recover

# ---------------------------------------------------------------------------
# Interrupt type strings
# Set in the interrupt() value dict by clarify/hitl nodes.
# Read by runs.py GET /interrupt to tell the frontend which form to show.
# ---------------------------------------------------------------------------
INTERRUPT_TYPE_CLARIFY = "clarify"
INTERRUPT_TYPE_HITL    = "hitl"
