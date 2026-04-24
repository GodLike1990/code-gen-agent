"""SSE streaming for agent runs.

`stream_run` is a pure async generator: it has zero hidden dependencies,
accepting the LangGraph iterator, the thread id, a `RequestStore`, and a
logger. That keeps it unit-testable in isolation from FastAPI.

The SSE frame contract (`event` names + `data` JSON keys) is identical
to the pre-refactor implementation — frontend code depends on it.
"""
from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

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
    final_status = "done"
    last_node: str | None = None
    try:
        async for item in coro_iter:
            stream_tid = item.get("thread_id") or tid
            update = item.get("update") or {}
            for node, partial in update.items():
                last_node = node

                # LangGraph emits special updates like `__interrupt__` whose
                # value is a tuple of Interrupt objects (not a dict). Translate
                # that into an SSE `interrupt` / `clarify` / `hitl` event so
                # the frontend can react, instead of crashing on `.get`.
                if node == "__interrupt__" or not isinstance(partial, dict):
                    interrupts = partial if isinstance(partial, (list, tuple)) else [partial]
                    for itp in interrupts:
                        val = getattr(itp, "value", None)
                        if not isinstance(val, dict):
                            continue
                        final_status = "interrupted"
                        itype = val.get("type") or "interrupt"
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
                        "event": "state_delta",
                        "data": json.dumps({"thread_id": stream_tid, "node": node}),
                    }
                    continue

                events = (partial or {}).get("events") or []
                for ev in events:
                    if ev.get("type") == "interrupt":
                        final_status = "interrupted"
                    yield {
                        "event": ev.get("type", "update"),
                        "data": json.dumps({"thread_id": stream_tid, "node": node, **ev}),
                    }
                yield {
                    "event": "state_delta",
                    "data": json.dumps({"thread_id": stream_tid, "node": node}),
                }
        yield {"event": "done", "data": json.dumps({})}
    except Exception as e:
        final_status = "failed"
        logger.exception(
            "stream_failed",
            extra={
                "thread_id": tid,
                "node": last_node,
                "event": "error",
                "error_type": type(e).__name__,
                "error": str(e),
            },
        )
        yield {
            "event": "error",
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
