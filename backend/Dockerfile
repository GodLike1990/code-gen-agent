# =============================================================================
# backend/Dockerfile
# Multi-stage build: install deps → copy source → runtime image
#
# External checker tools (ruff, semgrep, bandit) are installed via pip because
# checkers/lint.py and checkers/security.py detect them with shutil.which().
# They are NOT in pyproject.toml runtime deps — install them explicitly here.
#
# No system packages (gcc etc.) are needed: all runtime deps ship as pure-Python
# wheels or pre-compiled binaries (pyyaml pure fallback, psycopg[binary]).
# =============================================================================

# ---- Stage 1: dependency installer ----
FROM python:3.11-slim AS builder
WORKDIR /app

# Copy only the package manifest first so Docker can cache the pip layer
# independently of source code changes.
COPY pyproject.toml ./
# Create a minimal stub so pip can find the package metadata
RUN mkdir -p code_gen_agent && touch code_gen_agent/__init__.py

# Install runtime dependencies (no dev extras: no pytest/ruff-dev/mypy)
RUN pip install --no-cache-dir --prefix=/install \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    --trusted-host pypi.tuna.tsinghua.edu.cn \
    .

# Install external CLI tools used by checkers at runtime.
# - ruff: Python linter (lint checker)
# - semgrep: multi-language security scanner (security checker)
# - bandit: Python security linter fallback (security checker)
RUN pip install --no-cache-dir --prefix=/install \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    --trusted-host pypi.tuna.tsinghua.edu.cn \
    ruff semgrep bandit

# ---- Stage 2: runtime image ----
FROM python:3.11-slim
WORKDIR /app

# Copy installed packages from builder stage
COPY --from=builder /install /usr/local

# Copy application source
COPY code_gen_agent/ ./code_gen_agent/

# Pre-create runtime directories so bind-mount volumes work without
# permission errors on first start (Docker creates missing dirs as root).
RUN mkdir -p data/requests data/workspaces logs

EXPOSE 8000 9464

# Default env — overridden by docker-compose environment / env_file
ENV AGENT_HOST=0.0.0.0 \
    AGENT_PORT=8000 \
    AGENT_METRICS_ENABLED=true \
    AGENT_METRICS_PORT=9464 \
    AGENT_STATE_DSN=/app/data/.agent_state.sqlite \
    AGENT_REQUESTS_DIR=/app/data/requests \
    AGENT_WORKSPACE_ROOT=/app/data/workspaces \
    AGENT_LOG_FILE=/app/logs/agent.log

CMD ["python", "-m", "code_gen_agent.server"]
