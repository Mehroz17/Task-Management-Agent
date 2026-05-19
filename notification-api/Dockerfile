# ─── Builder ──────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install dependencies first (cached unless pyproject.toml/uv.lock change)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# ─── Runtime ──────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Explicit UID/GID 999 so K8s runAsUser: 999 + runAsNonRoot: true works
RUN groupadd --system --gid 999 notification && \
    useradd --system --uid 999 --gid 999 --no-create-home notification

WORKDIR /app

COPY --from=builder --chown=notification:notification /app/.venv .venv
COPY --chown=notification:notification src/ src/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    PYTHONUNBUFFERED=1

USER notification

EXPOSE 8090

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8090/health')"

CMD ["fastapi", "run", "src/notification_api/api.py", "--host", "0.0.0.0", "--port", "8090"]
