"""Prometheus 指标定义与导出（使用 prometheus_client 直连实现）。

本模块集中管理所有业务指标：
- 图节点：执行次数、耗时、并发
- HTTP：由 FastAPI 中间件 `HttpMetricsMiddleware` 采集
- LLM：token 用量与调用次数
- Runner：活跃任务数
- Build info：版本等常量

设计取舍：直接使用 prometheus_client 而不引入 OpenTelemetry SDK，
避免 exporter 与 SDK 版本错位，并减少依赖面。
"""
from __future__ import annotations

import os
import threading
from functools import lru_cache
from typing import Any

from code_gen_agent.observability.logger import get_logger

log = get_logger("metrics")

_INIT_LOCK = threading.Lock()
_INITIALIZED = False


def init_metrics(service_name: str = "code-gen-agent",
                 port: int | None = None) -> bool:
    """启动 Prometheus /metrics HTTP 端点。幂等。

    失败（缺依赖 / 端口占用）降级为 WARN 日志，业务不受影响。
    返回 True 表示本次触发了初始化。
    """
    global _INITIALIZED
    with _INIT_LOCK:
        if _INITIALIZED:
            return False
        try:
            from prometheus_client import start_http_server
        except ImportError as e:
            log.warning("metrics_import_failed",
                        extra={"event": "metrics_init_skip", "reason": str(e)})
            return False

        bind_port = port if port is not None else int(os.getenv("AGENT_METRICS_PORT", "9464"))
        try:
            start_http_server(bind_port)
            log.info("metrics_http_server_started",
                     extra={"event": "metrics_ready",
                            "port": bind_port, "service": service_name})
        except OSError as e:
            log.warning("metrics_http_server_bind_failed",
                        extra={"event": "metrics_bind_failed",
                               "port": bind_port, "error": str(e)})
            return False

        _INITIALIZED = True
        return True


@lru_cache(maxsize=1)
def node_metrics() -> dict[str, Any]:
    """图节点相关指标单例。"""
    from prometheus_client import Counter, Gauge, Histogram
    return {
        "runs": Counter(
            "agent_node_runs_total",
            "Total LangGraph node executions",
            labelnames=("node", "status"),
        ),
        "duration": Histogram(
            "agent_node_duration_seconds",
            "LangGraph node execution duration in seconds",
            labelnames=("node",),
            buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60, 120, 300),
        ),
        "in_progress": Gauge(
            "agent_node_in_progress",
            "Currently running LangGraph nodes",
            labelnames=("node",),
        ),
    }


@lru_cache(maxsize=1)
def llm_metrics() -> dict[str, Any]:
    """LLM 调用相关指标单例。"""
    from prometheus_client import Counter
    return {
        "tokens": Counter(
            "agent_llm_tokens_total",
            "Total LLM tokens (prompt/completion)",
            labelnames=("provider", "model", "kind"),
        ),
        "calls": Counter(
            "agent_llm_calls_total",
            "Total LLM invocations",
            labelnames=("provider", "model", "status"),
        ),
    }


@lru_cache(maxsize=1)
def runtime_metrics() -> dict[str, Any]:
    """后台 Runner 相关指标单例。"""
    from prometheus_client import Gauge
    return {
        "active": Gauge(
            "agent_run_active",
            "Currently active background runner tasks",
        ),
    }


@lru_cache(maxsize=1)
def http_metrics() -> dict[str, Any]:
    """HTTP 请求相关指标单例（由中间件填充）。"""
    from prometheus_client import Counter, Histogram
    return {
        "requests": Counter(
            "agent_http_requests_total",
            "Total HTTP requests",
            labelnames=("method", "route", "status"),
        ),
        "duration": Histogram(
            "agent_http_request_duration_seconds",
            "HTTP request duration in seconds",
            labelnames=("method", "route"),
            buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
        ),
    }


def record_build_info(version: str, provider: str) -> None:
    """通过常量 Gauge 暴露 build info。幂等。"""
    try:
        from prometheus_client import Gauge
        g = _build_info_gauge()
        g.labels(version=version, provider=provider).set(1)
    except Exception as e:  # noqa: BLE001
        log.warning("build_info_register_failed",
                    extra={"event": "build_info_failed", "error": str(e)})


@lru_cache(maxsize=1)
def _build_info_gauge() -> Any:
    from prometheus_client import Gauge
    return Gauge(
        "agent_build_info",
        "Build info (always 1, labels carry metadata)",
        labelnames=("version", "provider"),
    )


def is_enabled() -> bool:
    """按环境变量判断是否启用指标。"""
    return os.getenv("AGENT_METRICS_ENABLED", "true").lower() in ("1", "true", "yes", "on")
