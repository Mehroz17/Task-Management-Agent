# Task Management Agent

An AI-powered task management system built on the OpenAI Agents SDK, deployed on Kubernetes.

## What's Built

| Component | Status | Details |
|---|---|---|
| `task-mcp-server` | ✅ Complete | MCP server with 6 workflow tools, Streamable HTTP transport |
| CI/CD pipeline | ✅ Complete | GitHub Actions — test → build → push to GHCR on every push |
| Agent constitution | ✅ Complete | `agent.md` — full architecture, rules, and deployment spec |
| Orchestrator agent | 🔜 Planned | OpenAI Agents SDK, `gpt-4o` |
| Kubernetes manifests | 🔜 Planned | Deployments, Services, Helm charts in `deployments/` |

---

## task-mcp-server

The task MCP server is the data and workflow layer. It exposes 6 tools over Streamable HTTP that any MCP-compatible agent can call.

### Tools

| Tool | What it does |
|---|---|
| `task_create` | Create a task with title, project, priority, assignee, due date, tags |
| `task_get` | Get full detail of a task including comment history |
| `task_transition` | Move a task to a new status with a mandatory note explaining why |
| `task_update` | Edit any task fields and/or add a comment in one call |
| `task_delete` | Permanently delete a task |
| `project_view` | Project health: totals, status breakdown, overdue, blocked, by assignee |

### Run locally

```bash
cd task-mcp-server
PYTHONPATH=src uv run python -m task_mcp
# server starts at http://0.0.0.0:8000/mcp
```

### Run with Docker

```bash
docker pull ghcr.io/mehroz17/task-management-agent/task-mcp-server:latest
docker run -p 8000:8000 ghcr.io/mehroz17/task-management-agent/task-mcp-server:latest
```

### Connect to Claude Code

Add this to your `.mcp.json`:

```json
{
  "mcpServers": {
    "task-mcp": {
      "type": "http",
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

### Run tests

```bash
cd task-mcp-server
uv run pytest -v
```

---

## Architecture

The system follows a two-layer design:

**Commodity Layer** — the building blocks:
- **LLM** — OpenAI `gpt-4o` via the OpenAI Agents SDK
- **Tools** — task operations, project summaries, notifications
- **MCP** — Slack, GitHub, Google Calendar, Google Drive
- **Skills** — Triage, Daily Digest, Dependency Check, Bulk Update, Escalation
- **agent.md** — the agent constitution (this repo)

**Engineering Layer** — what makes it shippable:
- **Harness** — SDK `Runner` with loop, dispatch, and recovery
- **Context engineering** — session-based history, orchestrator → skill handoffs
- **Memory and state** — Redis-backed session, user profile, and project state
- **Evals** — scenario-based evaluation of routing, triage, safety, and recovery
- **Observability** — OpenAI Traces + Datadog via SDK trace processors
- **Permissions and safety** — input guardrails (blocking mode) + confirmation gates

---

## Repository Layout

```
.
├── agent.md                  # Agent constitution — single source of truth
├── CHANGELOG.md              # Milestone log
├── task-mcp-server/          # MCP server (complete)
│   ├── Dockerfile
│   ├── src/task_mcp/
│   └── tests/
└── deployments/              # Kubernetes manifests and Helm charts (coming)
```

---

## CI/CD

Every push to `task-mcp-server/` on `main` triggers the pipeline:

1. Runs all 36 tests
2. Builds the Docker image
3. Pushes to GHCR with `:latest` and `:sha-<commit>` tags

Image: `ghcr.io/mehroz17/task-management-agent/task-mcp-server`

---

## Docs

See [`agent.md`](./agent.md) for the full agent constitution — architecture decisions, tool design, MCP server list, memory design, observability, safety rules, and Kubernetes deployment spec.
