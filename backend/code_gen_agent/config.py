"""Agent configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal

Provider = Literal["openai", "anthropic", "deepseek", "ernie"]
StateBackend = Literal["sqlite", "redis", "db", "memory"]
CheckerName = Literal["lint", "security", "compile", "test", "llm_review"]


@dataclass
class AgentConfig:
    """Simple configuration: pass api_key and go.

    Example:
        >>> cfg = AgentConfig(provider="openai", api_key="sk-...")
        >>> agent = CodeGenAgent(cfg)
    """

    # ---- Model ----
    provider: Provider = "openai"
    api_key: str = ""
    model: str | None = None
    base_url: str | None = None
    temperature: float = 0.2
    request_timeout: float = 60.0

    # ---- Repair ----
    max_repairs: int = 5

    # ---- Checkers ----
    enable_checks: list[CheckerName] = field(
        default_factory=lambda: ["lint", "security", "compile", "test", "llm_review"]
    )
    checker_timeout: float = 60.0

    # ---- State persistence ----
    state_backend: StateBackend = "sqlite"
    state_dsn: str = ".agent_state.sqlite"  # file path / redis url / db url

    # ---- Observability ----
    langsmith_enabled: bool = False
    langsmith_api_key: str | None = None
    langsmith_project: str = "code-gen-agent"
    log_level: str = "INFO"
    log_file: str | None = "logs/agent.log"

    # ---- Prompt templates ----
    prompts_dir: str | None = None  # default: package builtin

    # ---- Sandbox ----
    workspace_root: str = "data/workspaces"

    # ---- Request records (decoupled from graph state) ----
    requests_dir: str = "data/requests"

    def __post_init__(self) -> None:
        if not self.api_key:
            self.api_key = os.environ.get(self._env_key_for_provider(), "")
        if self.langsmith_enabled and not self.langsmith_api_key:
            self.langsmith_api_key = os.environ.get("LANGSMITH_API_KEY") or os.environ.get(
                "LANGCHAIN_API_KEY"
            )

    def _env_key_for_provider(self) -> str:
        return {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "ernie": "QIANFAN_ACCESS_KEY",
        }[self.provider]
