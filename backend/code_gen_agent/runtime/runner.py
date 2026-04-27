"""Background run manager for same-process async execution.

Design:
- Each thread_id maps to at most one live ``asyncio.Task``.
- A bounded ring-buffer stores the last REPLAY_BUFFER_SIZE SSE frames so a
  reconnecting subscriber can catch up without missing events.
- Subscribers receive frames via an ``asyncio.Queue``; multiple simultaneous
  subscribers for the same thread are supported.
- Terminal outcomes always update the ``RequestStore`` exactly once.
- Duplicate concurrent execution for the same thread_id raises ``RunConflictError``
  (API layer maps it to HTTP 409).
"""
from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import Any, AsyncIterator

from code_gen_agent import CodeGenAgent
from code_gen_agent.api.streaming import stream_run
from code_gen_agent.observability.logger import get_logger
from code_gen_agent.persistence import RequestStore

# Maximum SSE frames kept in the per-thread replay buffer.
REPLAY_BUFFER_SIZE = 500

log = get_logger("runner")


class RunConflictError(RuntimeError):
    """Raised when a second run is started for an already-active thread."""


class RunNotFoundError(RuntimeError):
    """Raised when subscribing to a thread that has no known record."""


class _ThreadState:
    """Bookkeeping for one active or recently-finished thread."""

    def __init__(self) -> None:
        self.task: asyncio.Task | None = None
        self.buffer: deque[dict[str, Any]] = deque(maxlen=REPLAY_BUFFER_SIZE)
        self.subscribers: list[asyncio.Queue[dict[str, Any] | None]] = []
        self.finished: bool = False


class Runner:
    """Per-application background run manager.

    Instantiate once and attach to ``app.state.runner``.  Each
    ``start_run`` / ``resume_run`` call schedules an ``asyncio.Task`` that
    drives the LangGraph iterator and publishes SSE frames into a per-thread
    buffer + all live subscriber queues.

    Subscribers (SSE endpoint handlers) call ``subscribe(tid)`` which yields
    buffered frames first, then live frames as they arrive, and finally
    ``None`` as a sentinel when the run ends.
    """

    def __init__(self) -> None:
        self._threads: dict[str, _ThreadState] = {}

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    def start_run(
        self,
        agent: CodeGenAgent,
        tid: str,
        user_input: str,
        store: RequestStore,
        logger: logging.Logger | None = None,
    ) -> None:
        """Schedule a fresh run as a background ``asyncio.Task``.

        Raises ``RunConflictError`` if a live task already exists for *tid*.
        """
        self._ensure_no_active(tid)
        st = _ThreadState()
        self._threads[tid] = st

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
        """Schedule a resume as a background ``asyncio.Task``.

        Raises ``RunConflictError`` if a live task already exists for *tid*.
        """
        self._ensure_no_active(tid)
        # Keep existing buffer; resuming appends to it so subscribers get
        # the full history in order.
        st = self._threads.get(tid) or _ThreadState()
        self._threads[tid] = st
        st.finished = False

        async def _body() -> None:
            coro_iter = agent.aresume(tid, human_feedback)
            await self._pump(st, coro_iter, tid=tid, store=store, logger=logger or log)

        st.task = asyncio.get_event_loop().create_task(_body(), name=f"resume:{tid}")
        st.task.add_done_callback(lambda t: self._on_done(tid, t))

    async def subscribe(self, tid: str) -> AsyncIterator[dict[str, Any]]:
        """Async generator that yields SSE frame dicts for *tid*.

        Replay buffered frames first, then live frames.  Yields until the
        task finishes (sentinel ``None`` received from queue).

        Raises ``RunNotFoundError`` when *tid* has no record at all.
        """
        st = self._threads.get(tid)
        if st is None:
            raise RunNotFoundError(f"no run record for thread_id={tid!r}")

        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        st.subscribers.append(queue)
        try:
            # Replay buffered frames first so the client catches up.
            for frame in list(st.buffer):
                yield frame

            # If the task already finished before we subscribed, buffer
            # replay is sufficient — no need to wait on the queue.
            if st.finished:
                return

            while True:
                frame = await queue.get()
                if frame is None:  # sentinel: run ended
                    return
                yield frame
        finally:
            try:
                st.subscribers.remove(queue)
            except ValueError:
                pass

    def is_active(self, tid: str) -> bool:
        """Return True if a live task is running for *tid*."""
        st = self._threads.get(tid)
        return st is not None and st.task is not None and not st.task.done()

    async def shutdown(self) -> None:
        """Cancel all active tasks and wait for them to finish.

        Call this in the FastAPI lifespan ``finally`` block.
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
    # Internal helpers
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
        """Drive ``stream_run`` and publish every frame to buffer + subscribers."""
        async for frame in stream_run(coro_iter, tid=tid, store=store, logger=logger):
            st.buffer.append(frame)
            for q in list(st.subscribers):
                q.put_nowait(frame)

    def _on_done(self, tid: str, task: asyncio.Task) -> None:
        """Callback fired when the background task exits (any outcome)."""
        st = self._threads.get(tid)
        if st is None:
            return
        st.finished = True
        st.task = None
        # Send sentinel to all waiting subscribers so they exit cleanly.
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
