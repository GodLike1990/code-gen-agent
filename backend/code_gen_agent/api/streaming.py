"""SSE streaming for agent runs.

`stream_run` is a pure async generator: it has zero hidden dependencies,
accepting the LangGraph iterator, the thread id, a `RequestStore`, and a
logger. That keeps it unit-testable in isolation from FastAPI.

SSE FRAME CONTRACT
──────────────────
Every frame is a dict with {"event": <str>, "data": <json-str>}.
Event names and data shapes the frontend depends on:

  state_delta   {"thread_id", "node"}                   — triggers a state poll
  clarify       {"thread_id", "node", "type", "questions", ...}
  hitl          {"thread_id", "node", "type", "summary", ...}
  interrupt     {"thread_id", "node", "type", ...}       — generic interrupt
  hitl_decision {"thread_id", "node", "type", "action"}  — user's HITL decision
  done          {"final_status"}                         — run finished
  error         {"thread_id", "error_type", "message", "last_node"}

FINAL STATUS STATE MACHINE
───────────────────────────
  "done"        — default; set at start, kept if the run completes normally
  "interrupted" — overwritten when a LangGraph interrupt is detected
  "aborted"     — overwritten when hitl_decision action == "abort"
  "cancelled"   — overwritten in CancelledError handler (client disconnected)
  "failed"      — overwritten in Exception handler (unhandled error)

The final_status is written to RequestStore in the `finally` block and also
included in the "done" SSE frame so the frontend can update its local state.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator

from code_gen_agent.graph.constants import (
    EVENT_CLARIFY,
    EVENT_DONE,
    EVENT_ERROR,
    EVENT_HITL,
    EVENT_HITL_DECISION,
    EVENT_INTERRUPT,
    EVENT_STATE_DELTA,
    HITL_ACTION_ABORT,
    STATUS_ABORTED,
    STATUS_CANCELLED,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_INTERRUPTED,
)
from code_gen_agent.persistence import RequestStore


async def stream_run(
    coro_iter: AsyncIterator[dict],
    *,
    tid: str | None,
    store: RequestStore,
    logger: logging.Logger,
) -> AsyncIterator[dict[str, Any]]:
    """Translate LangGraph stream items into SSE frames.

    Emits `state_delta`, node-specific event types, `interrupt` /
    `clarify` / `hitl`, `done`, and `error` frames. Updates the request
    store with a `final_status` + `summary` in the `finally` block.
    """
    final_status = STATUS_DONE
    last_node: str | None = None
    try:
        async for item in coro_iter:
            stream_tid = item.get("thread_id") or tid
            update = item.get("update") or {}
            for node, partial in update.items():
                last_node = node

                # LangGraph emits special updates under the synthetic key
                # "__interrupt__" when a node calls interrupt().  The value
                # is a tuple/list of Interrupt objects (not a dict), each
                # carrying a `.value` dict that the node passed to interrupt().
                # We translate each Interrupt into a clarify/hitl SSE frame
                # so the frontend can render the appropriate UI.
                if node == "__interrupt__" or not isinstance(partial, dict):
                    interrupts = partial if isinstance(partial, (list, tuple)) else [partial]
                    for itp in interrupts:
                        val = getattr(itp, "value", None)
                        if not isinstance(val, dict):
                            continue
                        # Any interrupt means the run is paused waiting for input.
                        final_status = STATUS_INTERRUPTED
                        itype = val.get("type") or EVENT_INTERRUPT
                        yield {
                            "event": itype,
                            "data": json.dumps({
                                "thread_id": stream_tid,
                                "node": node,
                                "type": itype,
                                **{k: v for k, v in val.items() if k != "type"},
                            }),
                        }
                    yield {
                        "event": EVENT_STATE_DELTA,
                        "data": json.dumps({"thread_id": stream_tid, "node": node}),
                    }
                    continue

                events = (partial or {}).get("events") or []
                for ev in events:
                    if ev.get("type") == EVENT_INTERRUPT:
                        final_status = STATUS_INTERRUPTED
                    # The hitl node emits a "hitl_decision" event that records
                    # the user's chosen action.  We detect abort here — before
                    # routing — so the "done" frame carries "aborted" rather
                    # than the default "done", giving the frontend an immediate
                    # signal to update status without waiting for the next poll.
                    if ev.get("type") == EVENT_HITL_DECISION and ev.get("action") == HITL_ACTION_ABORT:
                        final_status = STATUS_ABORTED
                    yield {
                        "event": ev.get("type", "update"),
                        "data": json.dumps({"thread_id": stream_tid, "node": node, **ev}),
                    }
                yield {
                    "event": EVENT_STATE_DELTA,
                    "data": json.dumps({"thread_id": stream_tid, "node": node}),
                }
        yield {"event": EVENT_DONE, "data": json.dumps({"final_status": final_status})}
    except asyncio.CancelledError:
        # Client disconnected / ASGI task cancelled.  DO NOT swallow: re-raise
        # so uvicorn + starlette can clean up correctly.  Also DO NOT yield a
        # frame — the client is already gone and yielding would raise again.
        final_status = STATUS_CANCELLED
        logger.info(
            "stream_cancelled",
            extra={
                "thread_id": tid,
                "node": last_node,
                "event": "cancelled",
            },
        )
        raise
    except Exception as e:
        final_status = STATUS_FAILED
        logger.exception(
            "stream_failed",
            extra={
                "thread_id": tid,
                "node": last_node,
                "event": EVENT_ERROR,
                "error_type": type(e).__name__,
                "error": str(e),
            },
        )
        yield {
            "event": EVENT_ERROR,
            "data": json.dumps({
                "thread_id": tid,
                "error_type": type(e).__name__,
                "message": str(e),
                "last_node": last_node,
            }),
        }
    finally:
        if tid:
            summary = f"last_node={last_node}" if last_node else None
            store.update(tid, status=final_status, summary=summary)
            logger.info(
                "run_end",
                extra={
                    "thread_id": tid,
                    "event": "run_end",
                    "final_status": final_status,
                    "last_node": last_node,
                },
            )
