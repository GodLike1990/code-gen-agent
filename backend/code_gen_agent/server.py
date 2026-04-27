"""FastAPI server exposing the agent over HTTP + SSE.

This module is intentionally thin: it only wires together the
components built in `bootstrap` and `api`. Anything more than
construction + lifespan belongs in one of those packages.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from code_gen_agent import CodeGenAgent
from code_gen_agent.api import build_api_router
from code_gen_agent.api.middleware import HttpLoggingMiddleware
from code_gen_agent.bootstrap import init_agent, init_request_store, init_runner
from code_gen_agent.observability.logger import get_logger

log = get_logger("server")


def create_app(agent: CodeGenAgent | None = None) -> FastAPI:
    if agent is None:
        agent = init_agent()

    runner = init_runner()

    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        await agent.setup()
        log.info(
            "agent_ready",
            extra={
                "event": "agent_ready",
                "state_backend": agent.config.state_backend,
                "checkpointer": type(agent.checkpointer).__name__
                if agent.checkpointer
                else None,
            },
        )
        try:
            yield
        finally:
            await runner.shutdown()
            await agent.aclose()

    app = FastAPI(title="Code Gen Agent", version="0.1.0", lifespan=_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(HttpLoggingMiddleware)

    # Shared state accessed via FastAPI Depends in api/deps.py.
    app.state.agent = agent
    app.state.request_store = init_request_store(agent.config)
    app.state.runner = runner
    app.state.threads = []  # dev-only in-memory list of known thread ids

    app.include_router(build_api_router())
    return app


app = create_app()


def main() -> None:
    import logging
    import uvicorn

    # Silence uvicorn's own access log — HttpLoggingMiddleware handles it.
    # Route uvicorn error/startup messages through our JSON root logger so all
    # output shares the same structured format.
    logging.getLogger("uvicorn.access").handlers = []
    logging.getLogger("uvicorn.access").propagate = False
    for name in ("uvicorn", "uvicorn.error"):
        uv_log = logging.getLogger(name)
        for h in list(uv_log.handlers):
            uv_log.removeHandler(h)
        uv_log.propagate = True

    uvicorn.run(
        "code_gen_agent.server:app",
        host=os.environ.get("AGENT_HOST", "0.0.0.0"),
        port=int(os.environ.get("AGENT_PORT", "8000")),
        reload=False,
        access_log=False,  # disabled — HttpLoggingMiddleware covers it
    )


if __name__ == "__main__":
    main()
