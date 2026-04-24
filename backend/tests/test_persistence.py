"""Tests for persistence backends."""
from __future__ import annotations

import pytest

from code_gen_agent.config import AgentConfig
from code_gen_agent.persistence import create_checkpointer


def test_memory_backend() -> None:
    cfg = AgentConfig(provider="openai", api_key="x", state_backend="memory")
    saver = create_checkpointer(cfg)
    assert saver is not None


def test_sqlite_backend(tmp_path) -> None:
    cfg = AgentConfig(
        provider="openai",
        api_key="x",
        state_backend="sqlite",
        state_dsn=str(tmp_path / "state.sqlite"),
    )
    saver = create_checkpointer(cfg)
    assert saver is not None


def test_unknown_backend_raises() -> None:
    cfg = AgentConfig(provider="openai", api_key="x")
    cfg.state_backend = "nope"  # type: ignore[assignment]
    with pytest.raises(ValueError, match="unknown state_backend"):
        create_checkpointer(cfg)
