# Monitoring 模块

为 `code-gen-agent` 提供基于 **prometheus_client + Prometheus + Grafana** 的可观测性栈。

## 目录结构

```
monitoring/
├── prometheus/
│   └── prometheus.yml                    # scrape 配置，拉取 backend:9464
├── grafana/
│   ├── provisioning/
│   │   ├── datasources/prometheus.yml    # Prometheus 数据源
│   │   └── dashboards/dashboards.yml     # 仪表盘 provider
│   └── dashboards/
│       └── code-gen-agent.json           # 预置仪表盘
└── README.md
```

## 启动

监控服务已内置到根目录 `docker-compose.yml`：

```bash
docker compose up --build
```

## 访问

| 服务 | URL | 默认账号 |
| --- | --- | --- |
| Frontend | http://localhost | — |
| Backend API | http://localhost:8000 | — |
| **Backend metrics** | http://localhost:9464/metrics | — |
| **Prometheus** | http://localhost:9090 | — |
| **Grafana** | http://localhost:3000 | admin / admin |

Grafana 管理员账号密码可通过根目录 `.env` 中的 `GF_ADMIN_USER` / `GF_ADMIN_PASSWORD` 覆盖。

## 指标清单

| 指标 | 类型 | 标签 |
| --- | --- | --- |
| `agent_node_runs_total` | Counter | `node`, `status` |
| `agent_node_duration_seconds` | Histogram | `node` |
| `agent_node_in_progress` | Gauge | `node` |
| `agent_llm_tokens_total` | Counter | `provider`, `model`, `kind` |
| `agent_llm_calls_total` | Counter | `provider`, `model`, `status` |
| `agent_run_active` | Gauge | — |
| `agent_build_info` | Gauge | `version`, `provider` |
| `agent_http_requests_total` | Counter | `method`, `route`, `status` |
| `agent_http_request_duration_seconds` | Histogram | `method`, `route` |

## 开关

- 关闭指标：`AGENT_METRICS_ENABLED=false`（不启动 9464 端口）。
- 更改端口：`AGENT_METRICS_PORT=xxxx`。

## 常见排障

### Prometheus targets 显示 DOWN
- 登录 Prometheus UI → Status → Targets 查看错误。
- 确认 backend 已启动：`docker compose ps`，healthcheck 为 `healthy`。
- 确认同网络：`docker compose exec prometheus wget -qO- http://backend:9464/metrics | head`。

### Grafana 仪表盘为空
- 首次启动需等待 15s 左右完成第一次 scrape。
- 触发一次业务请求（例如通过前端提交一个需求）以产生指标。
- 在 Explore 中直接查询 `agent_node_runs_total` 确认有数据。

### 端口冲突
- 9090 / 3000 / 9464 / 8000 被占用时修改 `docker-compose.yml` 映射端口，
  或停止宿主机对应服务。

### 多进程警告
- 当前 uvicorn 单 worker 模式可直接工作。
- 如改为 `--workers > 1`，需按 `prometheus_client` 多进程模式配置
  `PROMETHEUS_MULTIPROC_DIR`，本期未实现。

## 扩展

新增 metric：
1. 在 `backend/code_gen_agent/observability/metrics.py` 的对应 `*_metrics()` 中创建 Counter / Gauge / Histogram。
2. 在业务点调用 `.inc()` / `.observe()` / `.set()`，避免高基数 label。
3. 在 `monitoring/grafana/dashboards/code-gen-agent.json` 中追加 panel（或通过 UI 新建后导出 JSON 覆盖）。

新增告警：
1. 创建 `monitoring/prometheus/rules/xxx.yml`。
2. 在 `prometheus.yml` 的 `rule_files` 中引用。
3. 如需 Alertmanager，另加 `monitoring/alertmanager/` 目录和 compose 服务。
