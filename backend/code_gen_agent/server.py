"""通过 HTTP + SSE 暴露 agent 的 FastAPI 服务。

本模块刻意保持精简：只负责组装 bootstrap 和 api 包中构建的组件。
除构造和生命周期管理之外的逻辑应放入对应的子包。
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

    # 通过 api/deps.py 中的 FastAPI Depends 访问共享状态
    app.state.agent = agent
    app.state.request_store = init_request_store(agent.config)
    app.state.runner = runner
    app.state.threads = []  # 仅开发用的内存线程 id 列表

    app.include_router(build_api_router())
    return app


app = create_app()


def main() -> None:
    import logging
    import uvicorn

    # 禁用 uvicorn 自带的 access log，由 HttpLoggingMiddleware 统一处理
    # 将 uvicorn 的 error/startup 日志转发到我们的 JSON 根 logger，
    # 确保所有输出使用相同的结构化格式
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
        access_log=False,  # 已禁用，由 HttpLoggingMiddleware 覆盖
    )


if __name__ == "__main__":
    main()
