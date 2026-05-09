"""基于 SQLite 文件的异步检查点。

使用 AsyncSqliteSaver + aiosqlite，因为 agent 运行 graph.astream()（异步）。
同步的 SqliteSaver 在异步调用时抛出 NotImplementedError，
会静默中止每次运行。

AsyncSqliteSaver.__init__ 会捕获当前事件循环，
因此必须在异步上下文中构造（如 FastAPI 启动）。
此工厂为 async 函数并返回 (saver, conn)，以便调用方在关闭时关闭连接。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


async def create_async_sqlite_checkpointer(dsn: str) -> tuple[Any, Any]:
    """打开 aiosqlite 连接并包装为 AsyncSqliteSaver。

    返回 (saver, conn)，调用方负责管理连接生命周期，
    关闭时需 await conn.close()。
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
