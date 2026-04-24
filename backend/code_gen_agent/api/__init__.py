"""Aggregate HTTP API router.

`build_api_router()` is the only public entry point — `server.py`
includes its output and never imports the individual sub-routers.
"""
from __future__ import annotations

from fastapi import APIRouter

from code_gen_agent.api.health import router as health_router
from code_gen_agent.api.history import router as history_router
from code_gen_agent.api.runs import router as runs_router
from code_gen_agent.api.schema import router as schema_router


def build_api_router() -> APIRouter:
    router = APIRouter()
    router.include_router(health_router)
    router.include_router(schema_router)
    router.include_router(history_router)
    router.include_router(runs_router)
    return router


__all__ = ["build_api_router"]
