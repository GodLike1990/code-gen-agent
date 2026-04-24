"""Relational DB checkpointer via Postgres (preferred) or any SQLAlchemy URL."""
from __future__ import annotations


def create_db_checkpointer(dsn: str):
    """Create a Postgres-backed checkpointer.

    The DSN is a Postgres connection string like
    `postgresql://user:pass@host:5432/db`.
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
        # setup is idempotent but may fail on restricted DBs; ignore.
        pass
    return saver
