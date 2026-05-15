# ─── Builder ──────────────────────────────────────────────────────────────────
FROM python:3.13-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# ─── Runtime ──────────────────────────────────────────────────────────────────
FROM python:3.13-slim AS runtime

RUN groupadd --system agent && \
    useradd --system --gid agent --no-create-home agent

WORKDIR /app

COPY --from=builder --chown=agent:agent /app/.venv .venv
COPY --chown=agent:agent src/ src/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    PYTHONUNBUFFERED=1

USER agent

# Requires at runtime: GEMINI_API_KEY, OPENAI_API_KEY, TASK_MCP_URL
CMD ["python", "src/task_mcp_sandbox.py"]
