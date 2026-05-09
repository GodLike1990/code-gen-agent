"""Agent 配置。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal

Provider = Literal["openai", "anthropic", "deepseek", "ernie"]
StateBackend = Literal["sqlite", "redis", "db", "memory"]
CheckerName = Literal["lint", "security", "compile", "test", "llm_review"]


@dataclass
class AgentConfig:
    """简洁配置：传入 api_key 即可启动。

    Example:
        >>> cfg = AgentConfig(provider="openai", api_key="sk-...")
        >>> agent = CodeGenAgent(cfg)
    """

    # ---- 模型 ----
    provider: Provider = "openai"
    api_key: str = ""
    model: str | None = None
    base_url: str | None = None
    temperature: float = 0.2
    request_timeout: float = 60.0

    # ---- 修复 ----
    max_repairs: int = 5

    # ---- 检查器 ----
    enable_checks: list[CheckerName] = field(
        default_factory=lambda: ["lint", "security", "compile", "test", "llm_review"]
    )
    checker_timeout: float = 60.0

    # ---- 状态持久化 ----
    state_backend: StateBackend = "sqlite"
    state_dsn: str = ".agent_state.sqlite"  # 文件路径 / redis url / db url

    # ---- 可观测性 ----
    langsmith_enabled: bool = False
    langsmith_api_key: str | None = None
    langsmith_project: str = "code-gen-agent"
    log_level: str = "INFO"
    log_file: str | None = "logs/agent.log"

    # ---- Prompt 模板 ----
    prompts_dir: str | None = None  # 默认使用内置包路径

    # ---- 沙盒 ----
    workspace_root: str = "data/workspaces"

    # ---- 请求记录（与图状态解耦） ----
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
