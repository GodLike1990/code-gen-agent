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
from code_gen_agent.bootstrap import init_agent, init_request_store
from code_gen_agent.observability.logger import get_logger

log = get_logger("server")


def create_app(agent: CodeGenAgent | None = None) -> FastAPI:
    if agent is None:
        agent = init_agent()

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
            await agent.aclose()

    app = FastAPI(title="Code Gen Agent", version="0.1.0", lifespan=_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Shared state accessed via FastAPI Depends in api/deps.py.
    app.state.agent = agent
    app.state.request_store = init_request_store(agent.config)
    app.state.threads = []  # dev-only in-memory list of known thread ids

    app.include_router(build_api_router())
    return app


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run(
        "code_gen_agent.server:app",
        host=os.environ.get("AGENT_HOST", "0.0.0.0"),
        port=int(os.environ.get("AGENT_PORT", "8000")),
        reload=False,
    )


if __name__ == "__main__":
    main()
