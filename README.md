# Code Generation AI Agent

基于 LangGraph 的代码生成 AI Agent，内置 ReAct 自修复与 Human-in-the-Loop（HITL）交互；前端 Web UI 提供需求录入、图 / 状态可观测、HITL 处理，以及 LangSmith 链路追踪。

## 架构

```
┌────────────────┐    HTTP/SSE    ┌────────────────────────┐
│  frontend/     │◀──────────────▶│  backend/              │
│  React + Vite  │                │  FastAPI + LangGraph   │
│  AntD/ReactFlow│                │  multi-provider LLM    │
└────────────────┘                └────────────────────────┘
                                           │
                                           ▼
                  ┌────────────────────────────────────────────┐
                  │ intent → clarify (HITL)                    │
                  │    ↓                                        │
                  │ decompose → codegen → checks(×5)           │
                  │                 fail ↓       pass ↓        │
                  │      hitl ← repair        → verify         │
                  │ (abort→END)  (ReAct, max_repairs)   ↓      │
                  │                              gaps → repair  │
                  │                              accepted ↓     │
                  │                            package (zip)    │
                  └────────────────────────────────────────────┘
```

## 项目结构

```
.
├── docker-compose.yml        # 一键全栈启动（backend + frontend + prometheus + grafana）
├── backend/
│   ├── Dockerfile            # Python 多阶段镜像
│   ├── .dockerignore
│   ├── code_gen_agent/
│   │   ├── agent.py          # 顶层门面
│   │   ├── bootstrap.py      # agent / runner / request_store 构建装配
│   │   ├── config.py         # AgentConfig
│   │   ├── server.py         # FastAPI 入口 + 生命周期
│   │   ├── sandbox.py        # 生成代码的工作区隔离
│   │   ├── api/              # REST / SSE 路由、依赖、中间件、响应模型
│   │   ├── runtime/          # 后台 Runner：每线程一个 asyncio.Task + SSE 重放缓冲
│   │   ├── llm/              # 多供应商适配 + token/cost 统计
│   │   ├── persistence/      # sqlite / redis / postgres / memory checkpointer
│   │   ├── observability/    # 结构化日志 + LangSmith + Prometheus 指标
│   │   ├── prompts/          # 节点 YAML 模板（Jinja2）
│   │   ├── graph/
│   │   │   ├── builder.py    # StateGraph 拼装
│   │   │   ├── registry.py   # 可插拔节点注册表
│   │   │   └── nodes/        # 9 个图节点实现
│   │   └── checkers/         # 五维检查 + 注册表
│   ├── tests/
│   ├── examples/
│   └── configs/
├── frontend/                 # React + TypeScript UI
│   ├── Dockerfile            # Node → nginx 多阶段镜像
│   ├── .dockerignore
│   ├── nginx.conf            # SPA 路由 + /agent/* 代理 + SSE 配置
│   └── src/
│       ├── api/              # 客户端 + SSE 读取器 + 类型
│       ├── store/            # Zustand 会话 store
│       ├── components/       # Layout / Timeline / GraphCanvas / CodeViewer 等
│       └── pages/            # Requirement / Graph / History / Observability
└── monitoring/               # Prometheus + Grafana 监控栈
    ├── prometheus/prometheus.yml
    ├── grafana/provisioning/ # datasource + dashboard provider（自动加载）
    ├── grafana/dashboards/code-gen-agent.json
    └── README.md
```

## 启动与运行

### Docker

```bash
cp backend/.env.example backend/.env
# 编辑 backend/.env，至少填写 AGENT_API_KEY
docker compose up --build
```

访问：
- 前端：http://localhost
- 后端 API：http://localhost:8000
- Backend metrics：http://localhost:9464/metrics
- Prometheus：http://localhost:9090
- Grafana：http://localhost:3000（默认 `admin` / `admin`）

**`backend/.env` 关键配置项：**

| Key | 取值 | 作用 |
|---|---|---|
| `AGENT_API_KEY` | LLM API key | **必填** |
| `APP_ENV` | `dev`（默认）/ `prod` / `full` | 控制安装依赖范围 |
| `ENABLE_LANGSMITH` | `true` / `false` | 接入 LangSmith 链路追踪 |
| `ENABLE_LLM_REVIEW` | `true` / `false` | 启用 LLM 自审 checker |
| `ENABLE_SECURITY_CHECK` | `true` / `false` | 启用安全 checker（Semgrep/Bandit） |
| `ENABLE_TEST_CHECK` | `true` / `false` | 启用测试运行 checker |
| `AGENT_METRICS_ENABLED` | `true`（默认）/ `false` | 是否启用 Prometheus 指标端点 |
| `AGENT_METRICS_PORT` | `9464`（默认） | 指标暴露端口 |

完整配置见 `backend/.env.example` 与 `backend/code_gen_agent/config.py`。

### 运行时数据布局

Backend 采用 **三份职责解耦的磁盘存储**：

| 路径 | 归属 | 内容 |
|---|---|---|
| `backend/.agent_state.sqlite` | LangGraph checkpointer | 每个 thread 的图状态（自动管理） |
| `backend/data/requests/{tid}.json` | `RequestStore` | 原始需求 + 状态 / summary |
| `backend/data/workspaces/{tid}/` | codegen 节点 | 该线程生成的代码文件 |
| `backend/logs/agent.log` | RotatingFileHandler | JSON 行日志（10MB × 5 滚动） |

前端 **History** 页（`/history`）通过 `GET /agent/history` 读取 `data/requests/`，
点击记录可恢复 `threadId` 并跳转至 `/graph`，由 checkpointer 回放保存的状态。

上述路径均已加入 `.gitignore`（通过 `.gitkeep` 保留空目录）；可通过 `.env` 中的
`AGENT_LOG_FILE` / `AGENT_REQUESTS_DIR` / `AGENT_WORKSPACE_ROOT` / `AGENT_STATE_DSN` 覆盖。

### 作为库使用

```python
from code_gen_agent import CodeGenAgent, AgentConfig

agent = CodeGenAgent(AgentConfig(
    provider="openai",
    api_key="sk-...",
))
result = agent.run("Create a FastAPI TODO service with JWT auth")
```

切换供应商只需改 `provider` + `api_key`，无需改代码。

## 特性

- **一行初始化**：只需 `provider` + `api_key`
- **多供应商**：OpenAI / Anthropic / DeepSeek / ERNIE 通过统一 factory 接入
- **ReAct 自修复**：最多 5 次尝试，失败自动升级 HITL
- **HITL**：基于 LangGraph `interrupt()` + checkpointer，可跨请求暂停 / 恢复
- **五维检查**：lint（Ruff/ESLint）、security（Semgrep/Bandit）、compile、test（pytest/jest）、LLM 自审，并行执行
- **可插拔**：`@register_node` 与 `@register_checker` 装饰器
- **Prompt 外置**：Jinja2 YAML 模板，支持热加载
- **多种状态后端**：sqlite（默认）/ redis / postgres / memory
- **可观测**：LangSmith 链路追踪、分 thread 的结构化 JSON 日志、token 用量与成本核算、**Prometheus 指标 + Grafana 仪表盘**
- **Web UI**（四个页面）：
  - `/requirement` — 需求录入、澄清问答、HITL 失败检阅与人工 patch、文件预览、ZIP 下载
  - `/graph` — ReactFlow 实时拓扑，逐节点状态与颜色图例
  - `/history` — 历史会话；点击某行恢复会话
  - `/observability` — 内嵌 LangSmith、日志表、token 统计

## 端到端验证场景

1. **Happy path**：提交简单需求 → intent / decompose / codegen / checks 全部通过 → 完成
2. **澄清流程**：模糊需求 → intent 置信度低 → 弹出澄清窗 → 恢复
3. **ReAct 修复**：注入一个会失败的 checker → repair 节点生成修复 → 重跑 checks
4. **HITL 升级**：超过 `max_repairs` 次失败 → 升级至 HITL → 在 Requirement 页选择重试 / 打补丁 / 放弃

## 配置参考

详见 `backend/code_gen_agent/config.py`（`AgentConfig`）与 `backend/.env.example`。

## 测试

```bash
cd backend && pytest -v
```

仓库内置五套测试：

| 文件 | 覆盖范围 |
|---|---|
| `tests/test_llm_factory.py` | 供应商适配器 + `base_url` 处理 |
| `tests/test_persistence.py` | sqlite / memory / redis / db checkpointer factory |
| `tests/test_checkers.py` | checker 注册表 + `CheckResult` 序列化 |
| `tests/test_graph_builder.py` | 图拓扑拼装 |
| `tests/test_graph_flow.py` | 端到端 happy path（mock LLM） |

## 指标与仪表盘

完整监控栈（Prometheus + Grafana）随 `docker compose up` 一起启动。

- 指标端点：`http://localhost:9464/metrics`（由 backend 独立线程暴露，与业务 8000 端口解耦）
- 所有 9 个图节点通过 `BaseNode` 统一埋点，上报：
  - `agent_node_runs_total{node,status}` — 执行次数
  - `agent_node_duration_seconds{node}` — 耗时分布
  - `agent_node_in_progress{node}` — 当前并发
- FastAPI 所有 HTTP 接口由自实现的 `HttpMetricsMiddleware`（ASGI 中间件）统一采集
  `agent_http_requests_total` 与 `agent_http_request_duration_seconds`。
- LLM 层额外上报 `agent_llm_tokens_total` / `agent_llm_calls_total`。
- Runner 层上报 `agent_run_active` 后台活跃任务数。

Grafana 在 `http://localhost:3000` 自动加载 "Code Gen Agent" 仪表盘，覆盖：
节点 QPS / P95 / 错误率 / 并发、LLM token 与调用量、HTTP P95、活跃任务数。

详细说明、排障与扩展见 [`monitoring/README.md`](monitoring/README.md)。

如需关闭指标：设置 `AGENT_METRICS_ENABLED=false` 后重启 backend。

## 常见问题

- **History 页为空** —— backend 会将需求记录写入
  `backend/data/requests/{tid}.json`。请确认目录存在且可写，以及
  `AGENT_REQUESTS_DIR`（若设置）指向预期路径。
- **Observability → LangSmith 页面空白** —— 需设置 `ENABLE_LANGSMITH=true`
  并在 `.env` 中填入有效的 `LANGCHAIN_API_KEY`，然后重启 backend；
  至少完整跑完一次任务后，LangSmith 才会出现对应 project。
- **下载 ZIP 返回 404** —— 压缩包仅在成功完成的任务 `package` 节点执行后才生成。
  若任务停在 HITL / clarify 阶段，产物尚不存在；先 resume 完成后再下载。
- **前端无法访问 backend** —— nginx 会将 `/agent/*` 代理到容器内的 `http://backend:8000`。
  确认两个服务均已启动（`docker compose ps`），且宿主机 80 / 8000 端口未被占用。

## License

MIT
