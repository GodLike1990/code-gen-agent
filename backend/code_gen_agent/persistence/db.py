"""通过 Postgres（或任意 SQLAlchemy URL）实现的关系型数据库检查点。"""
from __future__ import annotations


def create_db_checkpointer(dsn: str):
    """创建 Postgres 检查点。

    dsn 为 Postgres 连接串，格式如：
    postgresql://user:pass@host:5432/db
    """
    try:
        from langgraph.checkpoint.postgres import PostgresSaver
    except ImportError as e:
        raise ImportError(
            "langgraph-checkpoint-postgres is required for state_backend='db'. "
            "Install with `pip install langgraph-checkpoint-postgres`."
        ) from e
    saver = PostgresSaver.from_conn_string(dsn)
    try:
        saver.setup()
    except Exception:
        # setup 幂等，在受限数据库上可能失败，忽略即可
        pass
    return saver
