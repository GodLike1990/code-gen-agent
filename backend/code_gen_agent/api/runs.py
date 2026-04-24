"""Agent run lifecycle endpoints.

Covers: create, resume, state, logs, usage, interrupt, download.
"""
from __future__ import annotations

from pathlib import Path as _Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse

from code_gen_agent import CodeGenAgent
from code_gen_agent.api.deps import get_agent, get_request_store, valid_tid
from code_gen_agent.api.schemas import CreateRunRequest, ResumeRequest
from code_gen_agent.api.streaming import stream_run
from code_gen_agent.observability.logger import get_logger
from code_gen_agent.persistence import RequestStore

log = get_logger("server")

router = APIRouter(prefix="/agent/runs")


def _track(request: Request, tid: str) -> None:
    """Append thread id to the dev-only in-memory list, dedup by membership."""
    threads = getattr(request.app.state, "threads", None)
    if threads is None:
        return
    if tid not in threads:
        threads.append(tid)


@router.post("")
async def create_run(
    req: CreateRunRequest,
    request: Request,
    agent: CodeGenAgent = Depends(get_agent),
    store: RequestStore = Depends(get_request_store),
) -> Any:
    tid = req.thread_id or agent.new_thread_id()
    _track(request, tid)
    log.info(
        "run_start",
        extra={
            "thread_id": tid,
            "event": "run_start",
            "input_len": len(req.user_input or ""),
            "input_preview": (req.user_input or "")[:120],
        },
    )
    store.save(tid, req.user_input)
    return EventSourceResponse(
        stream_run(
            agent.astream(req.user_input, thread_id=tid),
            tid=tid,
            store=store,
            logger=log,
        )
    )


@router.post("/{thread_id}/resume")
async def resume(
    req: ResumeRequest,
    request: Request,
    thread_id: str = Depends(valid_tid),
    agent: CodeGenAgent = Depends(get_agent),
    store: RequestStore = Depends(get_request_store),
) -> Any:
    _track(request, thread_id)
    log.info("run_resume", extra={"thread_id": thread_id, "event": "run_resume"})
    store.update(thread_id, status="running")
    return EventSourceResponse(
        stream_run(
            agent.aresume(thread_id, req.human_feedback),
            tid=thread_id,
            store=store,
            logger=log,
        )
    )


@router.get("/{thread_id}/state")
def get_state(
    thread_id: str = Depends(valid_tid),
    agent: CodeGenAgent = Depends(get_agent),
) -> dict:
    try:
        snap = agent.get_state(thread_id)
    except Exception as e:
        log.exception(
            "get_state_failed",
            extra={
                "thread_id": thread_id,
                "event": "error",
                "error_type": type(e).__name__,
            },
        )
        raise HTTPException(500, f"{type(e).__name__}: {e}")
    if snap is None:
        raise HTTPException(404, "thread not found")
    return snap


@router.get("/{thread_id}/logs")
def get_logs(
    thread_id: str = Depends(valid_tid),
    agent: CodeGenAgent = Depends(get_agent),
) -> dict:
    from code_gen_agent.observability.log_reader import read_log_file

    mem = agent.get_logs(thread_id) or []
    disk: list[dict] = []
    if agent.config.log_file:
        disk = read_log_file(agent.config.log_file, thread_id)

    # Merge with (ts, event) as dedup key; memory wins.
    bucket: dict[tuple, dict] = {}
    for r in disk:
        bucket[(r.get("ts"), r.get("event"))] = r
    for r in mem:
        bucket[(r.get("ts"), r.get("event"))] = r
    merged = sorted(bucket.values(), key=lambda r: r.get("ts") or 0)

    if mem and disk:
        source = "merged"
    elif disk:
        source = "disk"
    else:
        source = "memory"
    return {"thread_id": thread_id, "source": source, "logs": merged}


@router.get("/{thread_id}/interrupt")
def get_interrupt(
    thread_id: str = Depends(valid_tid),
    agent: CodeGenAgent = Depends(get_agent),
) -> dict:
    """Return the pending interrupt (if any) so the UI can recover on reload.

    We derive the payload from `get_state(tid)` — which already exposes
    `next` and `values` — instead of stashing the original interrupt value
    anywhere. That avoids a second source of truth.
    """
    try:
        snap = agent.get_state(thread_id)
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {e}")
    if snap is None:
        raise HTTPException(404, "thread not found")
    next_nodes = snap.get("next") or []
    values = snap.get("values") or {}
    if "hitl" in next_nodes:
        summary = {
            "attempts": values.get("repair_attempts"),
            "failed_checks": [
                name
                for name, r in (values.get("check_results") or {}).items()
                if not (r or {}).get("passed")
            ],
            "files": list((values.get("generated_files") or {}).keys()),
            "history": values.get("repair_history") or [],
        }
        return {
            "pending": True,
            "type": "hitl",
            "thread_id": thread_id,
            "summary": summary,
        }
    if "clarify" in next_nodes:
        return {
            "pending": True,
            "type": "clarify",
            "thread_id": thread_id,
            "questions": values.get("clarify_questions") or [],
        }
    return {"pending": False, "thread_id": thread_id}


@router.get("/{thread_id}/usage")
def get_usage(
    thread_id: str = Depends(valid_tid),
    agent: CodeGenAgent = Depends(get_agent),
) -> dict:
    u = agent.get_usage(thread_id)
    return {"thread_id": thread_id, "usage": u or {}}


@router.get("/{thread_id}/download")
def download_artifact(
    thread_id: str = Depends(valid_tid),
    agent: CodeGenAgent = Depends(get_agent),
) -> FileResponse:
    """Stream the packaged ZIP for a completed run."""
    try:
        snap = agent.get_state(thread_id)
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {e}")
    if snap is None:
        raise HTTPException(404, "thread not found")
    art = (snap.get("values") or {}).get("artifact") or {}
    zp = art.get("zip_path")
    if not zp or not _Path(zp).exists():
        raise HTTPException(404, "artifact not built yet")
    return FileResponse(
        zp,
        filename=f"{thread_id}.zip",
        media_type="application/zip",
    )
