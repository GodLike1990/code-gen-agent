"""Startup initialization helpers.

Each `init_*` function does one thing and returns its artefact. No module-level
singletons — callers (FastAPI `create_app`, CLI entrypoint, library users)
decide how to wire them.

Note: `configure_logging` is already called inside `CodeGenAgent.__init__`,
so there is no separate `init_logging` function here. Log handlers are
attached when you construct an agent.
"""
from __future__ import annotations

import os

from code_gen_agent import AgentConfig, CodeGenAgent
from code_gen_agent.observability.logger import get_logger
from code_gen_agent.persistence import RequestStore

log = get_logger("bootstrap")


def _mask(v: str | None, keep: int = 4) -> str:
    if not v:
        return ""
    return v[:keep] + "…" + v[-keep:] if len(v) > keep * 2 else "***"


def init_config_from_env() -> AgentConfig:
    """Build an `AgentConfig` from environment variables.

    Component switches default to the minimal-start subset so a cold
    `APP_ENV=dev` install only runs lint + compile checkers unless the
    operator opts in to the rest.
    """
    provider = os.environ.get("AGENT_PROVIDER", "openai")

    def _bool(k: str, default: bool) -> bool:
        return os.environ.get(k, str(default)).lower() in ("1", "true", "yes", "on")

    enable_langsmith = _bool("ENABLE_LANGSMITH", False)
    enable_llm_review = _bool("ENABLE_LLM_REVIEW", True)
    enable_security = _bool("ENABLE_SECURITY_CHECK", True)
    enable_test = _bool("ENABLE_TEST_CHECK", True)

    checks = ["lint", "compile"]
    if enable_security:
        checks.append("security")
    if enable_test:
        checks.append("test")
    if enable_llm_review:
        checks.append("llm_review")

    return AgentConfig(
        provider=provider,  # type: ignore[arg-type]
        api_key=os.environ.get("AGENT_API_KEY", "")
        or os.environ.get("OPENAI_API_KEY", "")
        or os.environ.get("ANTHROPIC_API_KEY", "")
        or os.environ.get("DEEPSEEK_API_KEY", ""),
        model=os.environ.get("AGENT_MODEL") or None,
        base_url=os.environ.get("AGENT_BASE_URL") or None,
        enable_checks=checks,  # type: ignore[arg-type]
        state_backend=os.environ.get("AGENT_STATE_BACKEND", "sqlite"),  # type: ignore[arg-type]
        state_dsn=os.environ.get("AGENT_STATE_DSN", ".agent_state.sqlite"),
        langsmith_enabled=enable_langsmith,
        langsmith_project=os.environ.get("AGENT_LANGSMITH_PROJECT", "code-gen-agent"),
        log_level=os.environ.get("AGENT_LOG_LEVEL", "INFO"),
        log_file=os.environ.get("AGENT_LOG_FILE") or "logs/agent.log",
        requests_dir=os.environ.get("AGENT_REQUESTS_DIR") or "data/requests",
        workspace_root=os.environ.get("AGENT_WORKSPACE_ROOT") or "data/workspaces",
    )


def init_request_store(cfg: AgentConfig) -> RequestStore:
    """Per-request file store, decoupled from the graph checkpointer."""
    return RequestStore(cfg.requests_dir)


def init_agent(cfg: AgentConfig | None = None) -> CodeGenAgent:
    """Construct a `CodeGenAgent` and emit the `server_boot` structured log.

    The agent is NOT yet `setup()`-ed — async setup is deferred to the FastAPI
    lifespan (or the caller's own event loop).
    """
    if cfg is None:
        cfg = init_config_from_env()
    agent = CodeGenAgent(cfg)
    log.info(
        "server_boot",
        extra={
            "event": "server_boot",
            "provider": cfg.provider,
            "model": cfg.model,
            "base_url": cfg.base_url,
            "api_key": _mask(cfg.api_key),
            "log_file": cfg.log_file,
            "requests_dir": cfg.requests_dir,
            "workspace_root": cfg.workspace_root,
            "state_backend": cfg.state_backend,
            "state_dsn": cfg.state_dsn,
            "enable_checks": list(cfg.enable_checks),
            "langsmith_enabled": cfg.langsmith_enabled,
        },
    )
    return agent
