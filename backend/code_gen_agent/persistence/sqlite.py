"""SQLite file-based async checkpointer.

Uses `AsyncSqliteSaver` + `aiosqlite` because the agent runs `graph.astream(...)`
(async). The synchronous `SqliteSaver` raises `NotImplementedError` on async
calls, which silently aborts every run — see logs/agent.log from earlier.

`AsyncSqliteSaver.__init__` captures the running event loop, so it MUST be
constructed from inside async context (e.g. FastAPI startup). Hence this
factory is async and returns (saver, conn) so the caller can close the conn on
shutdown.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


async def create_async_sqlite_checkpointer(dsn: str) -> tuple[Any, Any]:
    """Open an aiosqlite connection and wrap it in AsyncSqliteSaver.

    Returns (saver, conn). Caller owns the connection and should `await
    conn.close()` on shutdown.
    """
    try:
        import aiosqlite
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            "aiosqlite and langgraph-checkpoint-sqlite are required for sqlite "
            "backend. Install with `pip install aiosqlite "
            "langgraph-checkpoint-sqlite`."
        ) from e

    Path(dsn).parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(dsn)
    saver = AsyncSqliteSaver(conn)
    return saver, conn
