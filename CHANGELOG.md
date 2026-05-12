# Changelog

All significant milestones are recorded here in reverse chronological order.

---

## [2026-05-12] — Published Code and Docker Image

**What was done**
- Git code pushed to `https://github.com/Mehroz17/Task-Management-Agent` (branch: main)
- Docker image pushed to GHCR: `ghcr.io/mehroz17/task-management-agent/task-mcp-server:latest`
- Authenticated Docker with GHCR via `gh` CLI token (`write:packages` scope)

**Verified**
- Push succeeded, image digest: `sha256:bd106cb11f766f7ae41e0bdd6de2c9caf4d5026096bf466e10fea4cc40063722`
- Image visible under repo Packages tab on GitHub

---

## [2026-05-12] — Task MCP Server: Production Dockerfile

**What was done**
- Added multi-stage `Dockerfile` to `task-mcp-server/`
- Builder stage: UV installs production deps into `.venv`; source copied separately for layer-cache efficiency
- Runtime stage: `python:3.13-slim`, non-root `mcp` user, only `.venv` and `src/` — no build tools
- `PYTHONPATH=/app/src` set so `python -m task_mcp` resolves correctly
- TCP healthcheck on port 8000
- Added `.dockerignore` to keep build context clean
- Updated `agent.md` with image registry (GHCR), `deployments/` layout convention, Dockerfile placement convention, and "verify every edit" rule

**Verified**
- `docker build` passed, server started, `GET /mcp` with `Accept: text/event-stream` returned HTTP 200

---

## [2026-05-12] — Task MCP Server: Implementation Complete

**What was done**
- Built full in-memory Task MCP server with 6 workflow tools: `task_create`, `task_get`,
  `task_transition`, `task_update`, `task_delete`, `project_view`
- Pydantic v2 models: `Task`, `Comment`, `TaskStatus`, `Priority`
- FastMCP with Streamable HTTP transport on port 8000, stateless sessions
- 36 TDD tests across 8 cycles (models, store, each tool) — all passing
- 11-step live end-to-end validation through MCP Inspector: all tools exercised against running server

**Verified**
- `uv run pytest -v` → 36/36 passed
- Server ran at `http://0.0.0.0:8000/mcp`, all 11 inspector steps confirmed

---

## [2026-05-12] — Project Specification: MCP Transport and Tool Design

**What was done**
- `spc/mcp_dic.md` — transport decision: Streamable HTTP over stdio; rationale documented
- `spc/task-server-tools.md` — workflow-oriented tool design spec; explains why CRUD/REST
  fail for agents and how the 6 tools map to human intent
- `spc/implementation-plan.md` — 7-step build plan with TDD cycle order and live validation sequence

---

## [2026-05-10] — Agent Constitution

**What was done**
- `agent.md` created — full two-layer architecture (Commodity + Engineering)
- Tech stack table: Python 3.12+, UV, OpenAI Agents SDK, gpt-4o, Redis, Kubernetes, GHCR
- 11 sections covering LLM, Tools, MCP servers, Skills, Harness, Context, Memory, Evals,
  Observability, Permissions, and Working Principles
- Kubernetes deployment section: 5 services, request flow diagram, scaling and config notes
- `README.md` added to repo root

**Verified**
- Committed and pushed to `https://github.com/Mehroz17/Task-Management-Agent`
