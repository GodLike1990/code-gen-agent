# Code Generation AI Agent — Backend

LangGraph-based code generation agent with ReAct self-repair and
Human-in-the-Loop, served over FastAPI + SSE.

## Quick Start

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
cp .env.example .env     # defaults to APP_ENV=dev; just fill in AGENT_API_KEY
make install             # picks dependencies based on APP_ENV from .env
make run                 # starts the server
```

Service runs on `http://localhost:8000`.

## Environment Switching

All environment and component toggles live in **`.env`**; the Makefile just
reads it:

```bash
APP_ENV=dev     # default — runtime + pytest/ruff/mypy
APP_ENV=prod    # production — runtime deps only (smallest image)
APP_ENV=full    # full — adds redis + postgres checkpointer support
```

Minimum-surface component switches (all enabled by default; disable per need):

```bash
ENABLE_LANGSMITH=false        # LangSmith tracing
ENABLE_LLM_REVIEW=true        # LLM self-review checker (consumes tokens)
ENABLE_SECURITY_CHECK=true    # Semgrep / Bandit security scan
ENABLE_TEST_CHECK=true        # run tests against generated code
```

After editing `.env`:

```bash
make install && make run
```

## Usage (library)

```python
from code_gen_agent import CodeGenAgent, AgentConfig

agent = CodeGenAgent(AgentConfig(provider="openai", api_key="sk-..."))
result = agent.run("Create a FastAPI TODO service")
```

## Configuration

All settings live in `AgentConfig` (see `code_gen_agent/config.py`):

| Field | Default | Notes |
|---|---|---|
| `provider` | openai | `openai` / `anthropic` / `deepseek` / `ernie` |
| `api_key` | — | required (or env var) |
| `model` | provider default | override if needed |
| `base_url` | — | for OpenAI-compatible endpoints |
| `max_repairs` | 5 | ReAct retry ceiling before HITL. Cycle detection escalates after 3 consecutive identical failure signatures; verify-gap failures get one repair round before escalation. |
| `enable_checks` | all 5 | `lint`, `security`, `compile`, `test`, `llm_review` |
| `state_backend` | sqlite | `sqlite` / `redis` / `db` / `memory` |
| `state_dsn` | `.agent_state.sqlite` | path / URL |
| `langsmith_enabled` | false | sets `LANGCHAIN_TRACING_V2` |

## HTTP API

| Route | Method | Description |
|---|---|---|
| `POST /agent/runs` | POST | Create run, returns SSE stream |
| `POST /agent/runs/{id}/resume` | POST | Resume from an `interrupt` (clarify or HITL) |
| `GET /agent/runs/{id}/state` | GET | Current state snapshot |
| `GET /agent/runs/{id}/logs` | GET | Structured logs (memory ∪ disk) |
| `GET /agent/runs/{id}/usage` | GET | Token / cost usage |
| `GET /agent/runs/{id}/interrupt` | GET | Pending interrupt (clarify / HITL) for UI recovery |
| `GET /agent/runs/{id}/download` | GET | Packaged ZIP of the generated workspace |
| `GET /agent/history` | GET | List persisted request records |
| `GET /agent/history/{id}` | GET | Fetch a single persisted request record |
| `GET /agent/graph/schema` | GET | Graph topology for the frontend |
| `GET /health` | GET | Liveness probe |

All `/{id}` routes reject empty, `/`, `\` or `..` thread ids with HTTP 400.

## Extending

- **Add a node**: subclass `BaseNode`, decorate with `@register_node("myname")`.
- **Add a checker**: subclass with `@register_checker("myname")`, add to `enable_checks`.
- **Customize prompts**: pass `prompts_dir` in `AgentConfig` with your own YAMLs.
- **Swap state backend**: set `state_backend` and `state_dsn`.

## Tests

```bash
pytest -v
```
