"""各路由模块共享的 FastAPI 依赖项。

每个路由通过 Depends(...) 从 app.state 获取协作对象，
避免路由直接访问 request.app.state，便于单元测试。
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
    """提前以 HTTP 400 拒绝空值或含路径分隔符的 thread id。"""
    if not thread_id or "/" in thread_id or "\\" in thread_id or ".." in thread_id:
        raise HTTPException(400, "invalid thread_id")
    return thread_id


# 重新导出 Depends，允许路由从单一入口导入
__all__ = ["Depends", "get_agent", "get_request_store", "get_runner", "valid_tid"]
