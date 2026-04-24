"""Build a LangChain ChatModel from AgentConfig."""
from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from code_gen_agent.config import AgentConfig
from code_gen_agent.llm.providers import get_spec
from code_gen_agent.llm.usage import UsageTracker


def create_chat_model(cfg: AgentConfig, usage: UsageTracker | None = None) -> BaseChatModel:
    """Create a chat model using only `provider` + `api_key` (+ optional overrides)."""
    if not cfg.api_key:
        raise ValueError(
            f"api_key is required for provider={cfg.provider}. "
            f"Pass it via AgentConfig or env."
        )
    spec = get_spec(cfg.provider)
    model = cfg.model or spec.default_model
    raw_base = cfg.base_url or spec.default_base_url
    # Only trim whitespace. Some corporate OpenAI-compatible proxies
    # REQUIRE a trailing '#' as a routing sentinel and must NOT be sanitized.
    base_url = raw_base.strip() if raw_base else None
    callbacks = [usage] if usage is not None else None

    common: dict[str, Any] = {
        "temperature": cfg.temperature,
        "timeout": cfg.request_timeout,
    }
    if callbacks is not None:
        common["callbacks"] = callbacks

    if cfg.provider in ("openai", "deepseek"):
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            api_key=cfg.api_key,
            model=model,
            base_url=base_url,
            **common,
        )
    if cfg.provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        kwargs: dict[str, Any] = {
            "api_key": cfg.api_key,
            "model": model,
            **common,
        }
        if base_url:
            kwargs["base_url"] = base_url
        return ChatAnthropic(**kwargs)
    if cfg.provider == "ernie":
        from langchain_community.chat_models import QianfanChatEndpoint

        return QianfanChatEndpoint(
            qianfan_ak=cfg.api_key,
            model=model,
            **common,
        )
    raise ValueError(f"unknown provider: {cfg.provider}")
