# Code Generation AI Agent

A LangGraph-based code generation AI agent featuring ReAct self-repair and Human-in-the-Loop (HITL) interaction, with a web UI for requirement intake, graph/state observation, HITL handling, and LangSmith observability.

## Architecture

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

Graph nodes:

- **intent** – classify user request, detect missing info
- **clarify** – `interrupt()` for interactive clarification
- **decompose** – split into file-level tasks
- **codegen** – generate full files or apply repair diff
- **checks** – parallel: lint / security / compile / test / llm_review
- **repair** – ReAct strategist (patch / regen / reclarify)
- **hitl** – escalate after `max_repairs` attempts (default 5); user can retry, patch, or abort
- **verify** – LLM acceptance review; gaps trigger repair or HITL escalation
- **package** – zip generated workspace into a downloadable artifact

## Project Structure

```
.
├── docker-compose.yml        # One-command full-stack startup
├── backend/
│   ├── Dockerfile            # Multi-stage Python image
│   ├── .dockerignore
│   ├── code_gen_agent/
│   │   ├── agent.py          # top-level facade
│   │   ├── config.py         # AgentConfig
│   │   ├── server.py         # FastAPI + SSE
│   │   ├── sandbox.py
│   │   ├── llm/              # provider adapters + usage tracker
│   │   ├── persistence/      # sqlite/redis/db/memory checkpointers
│   │   ├── observability/    # logging + LangSmith + usage aggregation
│   │   ├── prompts/          # YAML templates per node
│   │   ├── graph/
│   │   │   ├── builder.py    # StateGraph assembly
│   │   │   ├── registry.py   # pluggable node registry
│   │   │   └── nodes/        # 7 nodes
│   │   └── checkers/         # 5-dim checks with registry
│   ├── tests/
│   ├── examples/
│   └── configs/
└── frontend/             # React + TypeScript UI
    ├── Dockerfile            # Multi-stage Node → nginx image
    ├── .dockerignore
    ├── nginx.conf            # SPA routing + /agent/* proxy + SSE config
    └── src/
        ├── api/          # client + SSE reader + types
        ├── store/        # Zustand session store
        ├── components/   # Layout, Timeline, GraphCanvas, CodeViewer, ...
        └── pages/        # Requirement / Graph / HITL / Observability
```

## Setup & Run

### Docker

```bash
cp backend/.env.example backend/.env
# 编辑 backend/.env，至少填写 AGENT_API_KEY
docker compose up --build
```

访问：
- 前端：http://localhost
- 后端 API：http://localhost:8000

**`backend/.env` 关键配置项：**

| Key | Values | Effect |
|---|---|---|
| `AGENT_API_KEY` | your LLM API key | **必填** |
| `APP_ENV` | `dev` (default) / `prod` / `full` | 控制安装的依赖范围 |
| `ENABLE_LANGSMITH` | `true` / `false` | 开启 LangSmith tracing |
| `ENABLE_LLM_REVIEW` | `true` / `false` | 开启 LLM 自审 checker |
| `ENABLE_SECURITY_CHECK` | `true` / `false` | 开启安全 checker |
| `ENABLE_TEST_CHECK` | `true` / `false` | 开启测试运行 checker |

完整配置项见 `backend/.env.example` 和 `backend/code_gen_agent/config.py`。

### Runtime data layout

The backend uses **three decoupled on-disk stores** — each with a single responsibility:

| Path | Owner | Content |
|---|---|---|
| `backend/.agent_state.sqlite` | LangGraph checkpointer | Graph state per thread (auto-managed) |
| `backend/data/requests/{tid}.json` | `RequestStore` | Original user request + status/summary |
| `backend/data/workspaces/{tid}/` | codegen node | Generated code files for that thread |
| `backend/logs/agent.log` | RotatingFileHandler | JSON-line logs (10 MB × 5) |

The frontend **History** page (`/history`) reads `data/requests/` via `GET /agent/history`
to show all past sessions; clicking a row restores `threadId` and jumps to `/graph`
where the checkpointer replays the saved state.

All three locations are gitignored (empty dirs kept via `.gitkeep`); override with
`AGENT_LOG_FILE` / `AGENT_REQUESTS_DIR` / `AGENT_WORKSPACE_ROOT` / `AGENT_STATE_DSN` in `.env`.

### Library Usage

```python
from code_gen_agent import CodeGenAgent, AgentConfig

agent = CodeGenAgent(AgentConfig(
    provider="openai",
    api_key="sk-...",
))
result = agent.run("Create a FastAPI TODO service with JWT auth")
```

Switch providers by changing `provider` and `api_key` — no code changes needed.

## Features

- **One-line model init** — only `provider` + `api_key` required
- **Multi-provider** — OpenAI / Anthropic / DeepSeek / ERNIE via a unified factory
- **ReAct self-repair** — up to 5 attempts, auto-escalates to HITL
- **HITL** — LangGraph `interrupt()` + checkpointer enables pause/resume across requests
- **5-dim checks** — lint (Ruff/ESLint), security (Semgrep/Bandit), compile, test (pytest/jest), LLM self-review — all parallel
- **Pluggable** — `@register_node` and `@register_checker` decorators
- **Prompt externalization** — YAML templates with Jinja2, hot-reloadable
- **Multi-backend state** — sqlite (default) / redis / postgres / memory
- **Observability** — LangSmith tracing, structured per-thread JSON logs, token usage + cost accounting
- **Web UI** — four pages:
  - `/requirement` — intake, clarification Q&A, HITL failure review & manual patch, file preview, ZIP download
  - `/graph` — live ReactFlow topology with per-node status and colour legend
  - `/history` — past sessions; click a row to restore the session
  - `/observability` — embedded LangSmith, log table, token stats

## End-to-end Verification Scenarios

1. **Happy path**: submit a simple request → intent/decompose/codegen/checks all pass → done
2. **Clarification**: vague request → intent low confidence → clarify modal → resume
3. **ReAct repair**: inject a failing check → repair node generates fix → checks re-run
4. **HITL escalation**: max_repairs failures → escalate → user chooses retry/patch/abort on the Requirement page

## Extending

Add a checker:

```python
from code_gen_agent.checkers.base import register_checker, CheckResult

@register_checker("custom")
class MyChecker:
    name = "custom"
    async def run(self, workspace, files, context=None):
        return CheckResult(name=self.name, passed=True)
```

Then set `enable_checks=[..., "custom"]` in `AgentConfig`.

Add a node: subclass `BaseNode`, decorate with `@register_node("myname")`, and re-wire topology in `graph/builder.py`.

## Config Reference

See `backend/code_gen_agent/config.py` (`AgentConfig`) and `backend/.env.example`.

## Tests

```bash
cd backend && pytest -v
```

Five suites ship with the repo:

| File | Covers |
|---|---|
| `tests/test_llm_factory.py` | provider adapters + `base_url` handling |
| `tests/test_persistence.py` | sqlite / memory / redis / db checkpointer factory |
| `tests/test_checkers.py` | checker registry + `CheckResult` serialization |
| `tests/test_graph_builder.py` | graph topology assembly |
| `tests/test_graph_flow.py` | end-to-end happy path with a mocked LLM |

## Troubleshooting

- **History page is empty** — the backend writes request records to
  `backend/data/requests/{tid}.json`. Check that the directory exists and is
  writable, and that `AGENT_REQUESTS_DIR` (if set) points where you expect.
- **Observability → LangSmith tab is blank** — set `ENABLE_LANGSMITH=true`
  and provide a valid `LANGCHAIN_API_KEY` in `.env`, then restart the
  backend. Projects appear only after at least one run completes.
- **Download ZIP returns 404** — the archive is only built by the `package`
  node at the end of a successful run. If a run stops at HITL / clarify, the
  artifact does not exist yet; resume and let it finish first.
- **Frontend cannot reach backend** — nginx proxies `/agent/*` to `http://backend:8000` inside the container. Confirm both services started (`docker compose ps`) and that nothing else is occupying port 80 or 8000 on the host.

## License

MIT
