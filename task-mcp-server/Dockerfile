# ─── Builder ──────────────────────────────────────────────────────────────────
FROM python:3.13-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# ─── Runtime ──────────────────────────────────────────────────────────────────
FROM python:3.13-slim AS runtime

RUN groupadd --system mcp && \
    useradd --system --gid mcp --no-create-home mcp

WORKDIR /app

COPY --from=builder --chown=mcp:mcp /app/.venv .venv
COPY --chown=mcp:mcp src/ src/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    PYTHONUNBUFFERED=1

USER mcp

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c \
    "import socket; s=socket.create_connection(('localhost',8000),timeout=3); s.close()" \
    2>/dev/null || exit 1

CMD ["python", "-m", "task_mcp"]
