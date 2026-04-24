"""Checkpointer factory."""
from __future__ import annotations

from code_gen_agent.config import AgentConfig


def create_checkpointer(cfg: AgentConfig):
    """Create a LangGraph checkpointer based on `state_backend`."""
    backend = cfg.state_backend
    dsn = cfg.state_dsn

    if backend == "memory":
        from langgraph.checkpoint.memory import MemorySaver

        return MemorySaver()
    if backend == "sqlite":
        # Sqlite uses the async saver, which must be created inside a running
        # event loop. See `CodeGenAgent.setup()` — the agent builds it lazily
        # during FastAPI startup. Return None here so callers that skip setup
        # (e.g. raw script usage) fall back to MemorySaver semantics.
        return None
    if backend == "redis":
        from code_gen_agent.persistence.redis import create_redis_checkpointer

        return create_redis_checkpointer(dsn)
    if backend == "db":
        from code_gen_agent.persistence.db import create_db_checkpointer

        return create_db_checkpointer(dsn)
    raise ValueError(f"unknown state_backend: {backend}")
