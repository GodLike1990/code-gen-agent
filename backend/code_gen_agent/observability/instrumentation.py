"""HTTP 请求指标与 /metrics 端点初始化入口。

基于 prometheus_client 直接实现，不依赖 OpenTelemetry SDK，
避免 exporter 与 SDK 版本错位。
"""
from __future__ import annotations

import time
from typing import Any

from code_gen_agent.observability.logger import get_logger
from code_gen_agent.observability.metrics import (
    http_metrics,
    init_metrics,
    is_enabled,
    record_build_info,
)

log = get_logger("instrumentation")


class HttpMetricsMiddleware:
    """ASGI 中间件，以低基数 label（method, route, status）采集 HTTP 请求量 / 延迟。"""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET")
        status_code_holder: dict[str, int] = {"status": 500}

        async def _send(message: dict) -> None:
            if message.get("type") == "http.response.start":
                status_code_holder["status"] = int(message.get("status", 500))
            await send(message)

        start = time.perf_counter()
        try:
            await self.app(scope, receive, _send)
        finally:
            route = _route_template(scope)
            elapsed = time.perf_counter() - start
            try:
                m = http_metrics()
                m["requests"].labels(
                    method=method,
                    route=route,
                    status=str(status_code_holder["status"]),
                ).inc()
                m["duration"].labels(method=method, route=route).observe(elapsed)
            except Exception:  # noqa: BLE001
                pass


def _route_template(scope: dict) -> str:
    """返回 FastAPI 路由模板（`/agent/runs/{tid}`），回退到原始 path。"""
    route = scope.get("route")
    if route is not None:
        path = getattr(route, "path", None)
        if path:
            return str(path)
    return str(scope.get("path", "unknown"))


def setup_metrics(metrics_port: int | None = None,
                  service_name: str = "code-gen-agent",
                  version: str = "0.1.0",
                  provider_name: str = "") -> bool:
    """启动 Prometheus /metrics 端点并记录 build info。

    HTTP 请求指标由 `HttpMetricsMiddleware` 采集，中间件须在 `create_app`
    中通过 `app.add_middleware(HttpMetricsMiddleware)` 在构建期挂载。

    必须在首个请求前调用（通常在 lifespan 进入处）。
    返回 True 表示成功启用。所有失败均降级为 WARN 日志。
    `metrics_port` 为 None 时，`init_metrics` 会回退读取 `AGENT_METRICS_PORT`。
    """
    if not is_enabled():
        log.info("metrics_disabled", extra={"event": "metrics_disabled"})
        return False

    init_metrics(service_name=service_name, port=metrics_port)
    record_build_info(version=version, provider=provider_name or "unknown")
    return True
