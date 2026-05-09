"""基于 Redis 的检查点。"""
from __future__ import annotations


def create_redis_checkpointer(dsn: str):
    """创建 RedisSaver，需要 langgraph-checkpoint-redis。"""
    try:
        from langgraph.checkpoint.redis import RedisSaver
    except ImportError as e:
        raise ImportError(
            "langgraph-checkpoint-redis is required for state_backend='redis'. "
            "Install with `pip install langgraph-checkpoint-redis`."
        ) from e
    return RedisSaver.from_conn_string(dsn)
