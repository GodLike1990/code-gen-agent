"""Agent 运行生命周期端点。

涵盖：创建、恢复、事件订阅、状态、日志、用量、interrupt、下载。

架构（A1）：
- POST /agent/runs           → 调度后台任务，立即返回 {"thread_id", "status"}
- POST /agent/runs/{tid}/resume → 同上：调度恢复任务，立即返回
- GET  /agent/runs/{tid}/events → 从每线程重放缓冲区 SSE 流式推送
"""
from __future__ import annotations

from pathlib import Path as _Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse

from code_gen_agent import CodeGenAgent
from code_gen_agent.api.deps import get_agent, get_request_store, get_runner, valid_tid
from code_gen_agent.api.schemas import CreateRunRequest, ResumeRequest
from code_gen_agent.graph.constants import STATUS_RUNNING
from code_gen_agent.observability.logger import get_logger
from code_gen_agent.persistence import RequestStore
from code_gen_agent.runtime import RunConflictError, RunNotFoundError, Runner

log = get_logger("server")

router = APIRouter(prefix="/agent/runs")


def _track(request: Request, tid: str) -> None:
    """将 thread id 追加到仅用于开发的内存列表，通过成员检测去重。"""
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
    runner: Runner = Depends(get_runner),
) -> dict:
    """在后台启动新运行并立即返回。"""
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
    try:
        runner.start_run(agent, tid, req.user_input, store, log)
    except RunConflictError as e:
        raise HTTPException(409, str(e))
    return {"thread_id": tid, "status": STATUS_RUNNING}


@router.post("/{thread_id}/resume")
async def resume(
    req: ResumeRequest,
    request: Request,
    thread_id: str = Depends(valid_tid),
    agent: CodeGenAgent = Depends(get_agent),
    store: RequestStore = Depends(get_request_store),
    runner: Runner = Depends(get_runner),
) -> dict:
    """在后台恢复暂停的运行并立即返回。"""
    _track(request, thread_id)
    log.info("run_resume", extra={"thread_id": thread_id, "event": "run_resume"})
    store.update(thread_id, status=STATUS_RUNNING)
    try:
        runner.resume_run(agent, thread_id, req.human_feedback, store, log)
    except RunConflictError as e:
        raise HTTPException(409, str(e))
    return {"thread_id": thread_id, "status": STATUS_RUNNING}


@router.get("/{thread_id}/events")
async def stream_events(
    thread_id: str = Depends(valid_tid),
    runner: Runner = Depends(get_runner),
) -> Any:
    """SSE 端点：先重放缓冲帧，再流式推送实时帧。

    客户端在收到 POST /agent/runs 返回的 thread_id 后连接此端点。
    可随时重连，缓冲帧确保不遗漏历史数据。
    """
    try:
        gen = runner.subscribe(thread_id)
    except RunNotFoundError as e:
        raise HTTPException(404, str(e))
    return EventSourceResponse(gen)


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

    # 以 (ts, event) 为去重键合并；内存记录优先
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
    """返回待处理的 interrupt（如有），供 UI 页面刷新后恢复。"""
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
    """流式传输已完成运行的 ZIP 打包文件。"""
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
