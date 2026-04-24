"""Redis-backed checkpointer."""
from __future__ import annotations


def create_redis_checkpointer(dsn: str):
    """Create a RedisSaver. Requires `langgraph-checkpoint-redis`."""
    try:
        from langgraph.checkpoint.redis import RedisSaver
    except ImportError as e:
        raise ImportError(
            "langgraph-checkpoint-redis is required for state_backend='redis'. "
            "Install with `pip install langgraph-checkpoint-redis`."
        ) from e
    return RedisSaver.from_conn_string(dsn)
