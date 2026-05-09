"""启动初始化工具函数。

每个 init_* 函数只做一件事并返回其产物。无模块级单例，
调用方（FastAPI create_app、CLI 入口、库用户）自行决定如何组装。

注意：configure_logging 已在 CodeGenAgent.__init__ 中调用，
因此此处没有单独的 init_logging 函数。
构造 agent 时日志处理器即已挂载。
"""
from __future__ import annotations

import os

from code_gen_agent import AgentConfig, CodeGenAgent
from code_gen_agent.observability.logger import get_logger
from code_gen_agent.persistence import RequestStore
from code_gen_agent.runtime import Runner

log = get_logger("bootstrap")


def _mask(v: str | None, keep: int = 4) -> str:
    if not v:
        return ""
    return v[:keep] + "…" + v[-keep:] if len(v) > keep * 2 else "***"


def init_config_from_env() -> AgentConfig:
    """从环境变量构建 AgentConfig。

    各组件开关默认为最小启动子集，冷启动时只运行 lint + compile，
    运维人员可通过环境变量按需开启其余 checker。
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
    """请求级文件存储，与图检查点解耦。"""
    return RequestStore(cfg.requests_dir)


def init_runner() -> Runner:
    """创建后台运行管理器（每个应用实例一个）。"""
    return Runner()


def init_agent(cfg: AgentConfig | None = None) -> CodeGenAgent:
    """构建 CodeGenAgent 并输出 server_boot 结构化日志。

    agent 尚未执行 setup()，异步初始化延迟到 FastAPI lifespan
    或调用方自己的事件循环中进行。
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
