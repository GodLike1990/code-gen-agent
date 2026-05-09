"""CodeGenAgent 顶层门面类。"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, AsyncIterator

from langgraph.types import Command

from code_gen_agent.config import AgentConfig
from code_gen_agent.graph.builder import build_graph, get_graph_schema
from code_gen_agent.graph.state import initial_state
from code_gen_agent.llm.factory import create_chat_model
from code_gen_agent.observability.logger import configure_logging, get_collector
from code_gen_agent.observability.tracing import configure_langsmith, get_langsmith_run_url
from code_gen_agent.observability.usage import UsageAggregator
from code_gen_agent.persistence import create_checkpointer
from code_gen_agent.prompts.loader import PromptRegistry


class CodeGenAgent:
    """一行代码启动的 agent：`CodeGenAgent(AgentConfig(api_key='sk-...'))`。"""

    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        self._log_collector = configure_logging(config.log_level, config.log_file)
        self._langsmith_enabled = configure_langsmith(config)
        self.usage = UsageAggregator()
        self.prompts = PromptRegistry(config.prompts_dir)
        # sqlite 后端在 setup() 中惰性创建 saver，
        # 因为 AsyncSqliteSaver 在构造时会捕获当前事件循环。
        self.checkpointer = create_checkpointer(config)
        self._aio_conn: Any = None
        self._setup_done = False
        # LLM 按 thread 创建以附加各线程的用量追踪器，以 thread_id 缓存
        self._llms: dict[str, Any] = {}
        self._graphs: dict[str, Any] = {}

    async def setup(self) -> None:
        """完成异步初始化（为 sqlite 后端打开 aiosqlite 连接）。

        首次调用 astream() 前必须 await 此方法（使用 sqlite 时）。
        可安全多次调用。
        """
        if self._setup_done:
            return
        if self.config.state_backend == "sqlite" and self.checkpointer is None:
            from code_gen_agent.persistence.sqlite import (
                create_async_sqlite_checkpointer,
            )

            self.checkpointer, self._aio_conn = await create_async_sqlite_checkpointer(
                self.config.state_dsn
            )
        self._setup_done = True

    async def aclose(self) -> None:
        """释放资源（关闭 aiosqlite 连接）。"""
        if self._aio_conn is not None:
            try:
                await self._aio_conn.close()
            finally:
                self._aio_conn = None

    # ---- 公共 API ----

    def new_thread_id(self) -> str:
        return "t-" + uuid.uuid4().hex[:12]

    def get_graph_schema(self) -> dict[str, Any]:
        return get_graph_schema()

    def get_state(self, thread_id: str) -> dict[str, Any] | None:
        graph = self._graph_for(thread_id)
        snap = graph.get_state({"configurable": {"thread_id": thread_id}})
        if snap is None:
            return None
        return {
            "values": snap.values,
            "next": list(snap.next or []),
            "tasks": [t._asdict() if hasattr(t, "_asdict") else str(t) for t in (snap.tasks or [])],
            "langsmith_url": get_langsmith_run_url(self.config.langsmith_project, thread_id)
            if self._langsmith_enabled
            else None,
        }

    def get_usage(self, thread_id: str) -> dict[str, Any] | None:
        return self.usage.snapshot(thread_id)

    def get_logs(self, thread_id: str) -> list[dict[str, Any]]:
        collector = get_collector()
        return collector.get(thread_id) if collector else []

    async def astream(
        self, user_input: str, thread_id: str | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        await self.setup()
        tid = thread_id or self.new_thread_id()
        graph = self._graph_for(tid)
        workspace = self._prepare_workspace(tid)
        init = initial_state(user_input, tid, workspace, self.config.max_repairs)
        async for chunk in graph.astream(
            init,
            config={"configurable": {"thread_id": tid}, "recursion_limit": 50},
            stream_mode="updates",
        ):
            yield {"thread_id": tid, "update": chunk}

    async def aresume(
        self, thread_id: str, human_feedback: Any
    ) -> AsyncIterator[dict[str, Any]]:
        await self.setup()
        graph = self._graph_for(thread_id)
        async for chunk in graph.astream(
            Command(resume=human_feedback),
            config={"configurable": {"thread_id": thread_id}, "recursion_limit": 50},
            stream_mode="updates",
        ):
            yield {"thread_id": thread_id, "update": chunk}

    def run(self, user_input: str, thread_id: str | None = None) -> dict[str, Any]:
        """同步单次运行，发生 HITL interrupt 时抛出异常。"""
        import asyncio

        async def _collect():
            out = []
            async for ev in self.astream(user_input, thread_id):
                out.append(ev)
            return out

        events = asyncio.run(_collect())
        return {"events": events}

    # ---- 内部方法 ----

    def _graph_for(self, thread_id: str):
        if thread_id in self._graphs:
            return self._graphs[thread_id]
        tracker = self.usage.get_or_create(thread_id)
        llm = create_chat_model(self.config, usage=tracker, thread_id=thread_id)
        self._llms[thread_id] = llm
        graph = build_graph(
            llm=llm,
            prompts=self.prompts,
            checkpointer=self.checkpointer,
            enabled_nodes=None,
        )
        self._graphs[thread_id] = graph
        return graph

    def _prepare_workspace(self, thread_id: str) -> str:
        root = Path(self.config.workspace_root).resolve()
        path = root / thread_id
        path.mkdir(parents=True, exist_ok=True)
        return str(path)
