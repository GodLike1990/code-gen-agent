"""Tests for LLM factory provider dispatch."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from code_gen_agent.config import AgentConfig
from code_gen_agent.llm.factory import create_chat_model
from code_gen_agent.llm.usage import UsageTracker


def test_missing_api_key_raises() -> None:
    cfg = AgentConfig(provider="openai", api_key="")
    with pytest.raises(ValueError, match="api_key is required"):
        create_chat_model(cfg)


def test_openai_factory_dispatch() -> None:
    cfg = AgentConfig(provider="openai", api_key="sk-test")
    with patch("langchain_openai.ChatOpenAI") as m:
        create_chat_model(cfg)
        m.assert_called_once()
        kwargs = m.call_args.kwargs
        assert kwargs["model"] == "gpt-4o-mini"
        assert kwargs["api_key"] == "sk-test"


def test_deepseek_uses_openai_compatible_base_url() -> None:
    cfg = AgentConfig(provider="deepseek", api_key="sk-ds")
    with patch("langchain_openai.ChatOpenAI") as m:
        create_chat_model(cfg)
        kwargs = m.call_args.kwargs
        assert kwargs["base_url"] == "https://api.deepseek.com/v1"
        assert kwargs["model"] == "deepseek-coder"


def test_anthropic_dispatch() -> None:
    cfg = AgentConfig(provider="anthropic", api_key="sk-ant")
    with patch("langchain_anthropic.ChatAnthropic") as m:
        create_chat_model(cfg)
        m.assert_called_once()


def test_usage_tracker_callback_wired() -> None:
    cfg = AgentConfig(provider="openai", api_key="sk-test")
    tracker = UsageTracker()
    with patch("langchain_openai.ChatOpenAI") as m:
        create_chat_model(cfg, usage=tracker)
        kwargs = m.call_args.kwargs
        assert tracker in kwargs.get("callbacks", [])


def test_usage_snapshot_empty() -> None:
    tracker = UsageTracker()
    snap = tracker.snapshot()
    assert snap["total_tokens"] == 0
    assert snap["by_model"] == {}
