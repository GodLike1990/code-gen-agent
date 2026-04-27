"""FastAPI dependencies shared by the router modules.

Each router uses `Depends(...)` to pull its collaborators from
`app.state`, so routers never reach into `request.app.state` directly
and stay easy to unit-test.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Path, Request

from code_gen_agent import CodeGenAgent
from code_gen_agent.persistence import RequestStore
from code_gen_agent.runtime import Runner


def get_agent(request: Request) -> CodeGenAgent:
    agent = getattr(request.app.state, "agent", None)
    if agent is None:
        raise HTTPException(500, "agent not initialised")
    return agent


def get_request_store(request: Request) -> RequestStore:
    store = getattr(request.app.state, "request_store", None)
    if store is None:
        raise HTTPException(500, "request store not initialised")
    return store


def get_runner(request: Request) -> Runner:
    runner = getattr(request.app.state, "runner", None)
    if runner is None:
        raise HTTPException(500, "runner not initialised")
    return runner


def valid_tid(thread_id: str = Path(...)) -> str:
    """Reject empty / path-separator thread ids early with HTTP 400."""
    if not thread_id or "/" in thread_id or "\\" in thread_id or ".." in thread_id:
        raise HTTPException(400, "invalid thread_id")
    return thread_id


# Re-export `Depends` so routers can `from .deps import Depends, ...`
# if they prefer a single import source.
__all__ = ["Depends", "get_agent", "get_request_store", "get_runner", "valid_tid"]
