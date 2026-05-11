"""进程内异步运行的后台任务管理器。

设计：
- 每个 thread_id 最多映射一个活跃的 asyncio.Task。
- 有界环形缓冲区存储最近 REPLAY_BUFFER_SIZE 条 SSE 帧，
  重连的订阅者可通过重放补齐历史，不会漏事件。
- 订阅者通过 asyncio.Queue 接收帧；同一线程支持多个并发订阅者。
- 终态结果恰好更新一次 RequestStore。
- 同一 thread_id 并发执行时抛出 RunConflictError
  （API 层将其映射为 HTTP 409）。
"""
from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import Any, AsyncIterator

from code_gen_agent import CodeGenAgent
from code_gen_agent.api.streaming import stream_run
from code_gen_agent.observability.logger import get_logger
from code_gen_agent.observability.metrics import runtime_metrics
from code_gen_agent.persistence import RequestStore

# 每线程重放缓冲区保留的最大 SSE 帧数
REPLAY_BUFFER_SIZE = 500

log = get_logger("runner")


def _runner_active_inc() -> None:
    try:
        runtime_metrics()["active"].inc()
    except Exception:  # noqa: BLE001
        pass


def _runner_active_dec() -> None:
    try:
        runtime_metrics()["active"].dec()
    except Exception:  # noqa: BLE001
        pass


class RunConflictError(RuntimeError):
    """当已有活跃任务的线程再次启动运行时抛出。"""


class RunNotFoundError(RuntimeError):
    """订阅未知线程时抛出。"""


class _ThreadState:
    """单个活跃或已完成线程的运行时状态。"""

    def __init__(self) -> None:
        self.task: asyncio.Task | None = None
        self.buffer: deque[dict[str, Any]] = deque(maxlen=REPLAY_BUFFER_SIZE)
        self.subscribers: list[asyncio.Queue[dict[str, Any] | None]] = []
        self.finished: bool = False


class Runner:
    """应用级后台运行管理器。

    实例化一次并挂载到 app.state.runner。
    每次 start_run / resume_run 调度一个 asyncio.Task，
    驱动 LangGraph 迭代器并将 SSE 帧推送到线程缓冲区和所有活跃订阅队列。

    订阅者（SSE 端点处理器）调用 subscribe(tid)，
    先接收缓冲帧，再接收实时帧，最后收到 None 哨兵表示运行结束。
    """

    def __init__(self) -> None:
        self._threads: dict[str, _ThreadState] = {}

    # ------------------------------------------------------------------
    # 公共入口
    # ------------------------------------------------------------------

    def start_run(
        self,
        agent: CodeGenAgent,
        tid: str,
        user_input: str,
        store: RequestStore,
        logger: logging.Logger | None = None,
    ) -> None:
        """以后台 asyncio.Task 启动新运行。

        若 tid 已有活跃任务则抛出 RunConflictError。
        """
        self._ensure_no_active(tid)
        st = _ThreadState()
        self._threads[tid] = st
        _runner_active_inc()

        async def _body() -> None:
            coro_iter = agent.astream(user_input, thread_id=tid)
            await self._pump(st, coro_iter, tid=tid, store=store, logger=logger or log)

        st.task = asyncio.get_event_loop().create_task(_body(), name=f"run:{tid}")
        st.task.add_done_callback(lambda t: self._on_done(tid, t))

    def resume_run(
        self,
        agent: CodeGenAgent,
        tid: str,
        human_feedback: Any,
        store: RequestStore,
        logger: logging.Logger | None = None,
    ) -> None:
        """以后台 asyncio.Task 恢复暂停的运行。

        若 tid 已有活跃任务则抛出 RunConflictError。
        """
        self._ensure_no_active(tid)
        # 保留现有缓冲区，恢复时追加帧，订阅者可获得完整历史
        st = self._threads.get(tid) or _ThreadState()
        self._threads[tid] = st
        st.finished = False
        _runner_active_inc()

        async def _body() -> None:
            coro_iter = agent.aresume(tid, human_feedback)
            await self._pump(st, coro_iter, tid=tid, store=store, logger=logger or log)

        st.task = asyncio.get_event_loop().create_task(_body(), name=f"resume:{tid}")
        st.task.add_done_callback(lambda t: self._on_done(tid, t))

    async def subscribe(self, tid: str) -> AsyncIterator[dict[str, Any]]:
        """异步生成器，为 tid 产出 SSE 帧字典。

        先重放缓冲帧，再推送实时帧，任务结束时（收到 None 哨兵）退出。

        tid 无任何记录时抛出 RunNotFoundError。
        """
        st = self._threads.get(tid)
        if st is None:
            raise RunNotFoundError(f"no run record for thread_id={tid!r}")

        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        st.subscribers.append(queue)
        try:
            # 先重放缓冲帧，让客户端补齐历史
            for frame in list(st.buffer):
                yield frame

            # 任务在订阅前已结束，重放缓冲即足够，无需等待队列
            if st.finished:
                return

            while True:
                frame = await queue.get()
                if frame is None:  # 哨兵：运行已结束
                    return
                yield frame
        finally:
            try:
                st.subscribers.remove(queue)
            except ValueError:
                pass

    def is_active(self, tid: str) -> bool:
        """tid 有活跃任务时返回 True。"""
        st = self._threads.get(tid)
        return st is not None and st.task is not None and not st.task.done()

    async def shutdown(self) -> None:
        """取消所有活跃任务并等待其结束。

        在 FastAPI lifespan 的 finally 块中调用。
        """
        tasks = [
            st.task
            for st in self._threads.values()
            if st.task and not st.task.done()
        ]
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    # ------------------------------------------------------------------
    # 内部辅助方法
    # ------------------------------------------------------------------

    def _ensure_no_active(self, tid: str) -> None:
        if self.is_active(tid):
            raise RunConflictError(
                f"run already in progress for thread_id={tid!r}"
            )

    async def _pump(
        self,
        st: _ThreadState,
        coro_iter: AsyncIterator[dict],
        *,
        tid: str,
        store: RequestStore,
        logger: logging.Logger,
    ) -> None:
        """驱动 stream_run 并将每帧发布到缓冲区和订阅者队列。"""
        async for frame in stream_run(coro_iter, tid=tid, store=store, logger=logger):
            st.buffer.append(frame)
            for q in list(st.subscribers):
                q.put_nowait(frame)

    def _on_done(self, tid: str, task: asyncio.Task) -> None:
        """后台任务退出（任意结果）时的回调。"""
        st = self._threads.get(tid)
        if st is None:
            return
        st.finished = True
        st.task = None
        _runner_active_dec()
        # 向所有等待中的订阅者发送哨兵，使其干净退出
        for q in list(st.subscribers):
            try:
                q.put_nowait(None)
            except asyncio.QueueFull:
                pass
        if task.cancelled():
            log.info("runner_task_cancelled", extra={"thread_id": tid, "event": "runner_task_cancelled"})
        elif task.exception():
            log.warning(
                "runner_task_failed",
                extra={
                    "thread_id": tid,
                    "event": "runner_task_failed",
                    "error": str(task.exception()),
                },
            )
