"""LangSmith tracing configuration."""
from __future__ import annotations

import os

from code_gen_agent.config import AgentConfig


def configure_langsmith(cfg: AgentConfig) -> bool:
    """Enable LangSmith tracing via env vars. Returns True if enabled."""
    if not cfg.langsmith_enabled:
        return False
    api_key = cfg.langsmith_api_key or os.environ.get("LANGSMITH_API_KEY")
    if not api_key:
        return False
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = api_key
    os.environ["LANGCHAIN_PROJECT"] = cfg.langsmith_project
    return True


def get_langsmith_run_url(project: str, thread_id: str | None = None) -> str:
    """Build a best-effort LangSmith dashboard URL for a project/thread."""
    base = "https://smith.langchain.com"
    if thread_id:
        return f"{base}/o/-/projects/p/{project}?searchModel=%7B%22filter%22%3A%22has(metadata%2C%20'thread_id'%3A%20'{thread_id}')%22%7D"
    return f"{base}/o/-/projects/p/{project}"
