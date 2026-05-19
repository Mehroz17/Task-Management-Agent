# Specification: Notification API

## Purpose

A deadline reminder service. It watches task deadlines in `task-mcp-server` and writes
notifications to an in-memory inbox whenever a task's due date is approaching. Anything
that wants to know about upcoming deadlines reads from the inbox via HTTP.

There is no email, Slack, or push delivery in this project. The inbox IS the delivery
mechanism — other services (or a developer with curl) poll it.

---

## How It Works

```
every 60 seconds
       │
       ▼
Background job
  └── for each watched project:
        └── call project_view on task-mcp-server (via MCP)
              └── for each task where due_date is within threshold AND status != done:
                    └── write Notification to in-memory inbox
                          (skip if already notified for this task in this window)
```

A consumer reads the inbox:
```
GET /notifications  →  list of pending notifications
POST /notifications/{id}/read  →  mark one as read
```

---

## Background Job

- **Trigger:** runs every `POLL_INTERVAL_SECONDS` (default: 60) using a FastAPI lifespan
  `asyncio` background task — no external scheduler needed
- **What it does:**
  1. For each rule in the rules store, call `project_view` on `task-mcp-server` via MCP
  2. Inspect each task's `due_date`
  3. If `due_date` is within `threshold_hours` of now AND `status` is not `done` → create a notification
  4. Deduplication: skip if a notification for the same `task_id` was already created within
     the current threshold window (prevents the same reminder from firing every 60s)
- **Error handling:** if `task-mcp-server` is unreachable, log the error and skip that
  cycle — never crash the service

---

## Data Models

### Rule
Defines which project to watch and how far ahead to look.

| Field | Type | Description |
|---|---|---|
| `id` | `str` (UUID) | Auto-generated |
| `project` | `str` | Project name to watch (matches `task-mcp-server` project names) |
| `threshold_hours` | `int` | How many hours before deadline to fire a reminder (default: 24) |
| `created_at` | `datetime` | When the rule was registered |

### Notification
A reminder record created by the background job.

| Field | Type | Description |
|---|---|---|
| `id` | `str` (UUID) | Auto-generated |
| `task_id` | `str` | The task this reminder is for |
| `task_title` | `str` | Task title (copied at notification time) |
| `project` | `str` | Project name |
| `due_date` | `datetime` | The task's due date |
| `message` | `str` | Human-readable reminder, e.g. `"Task 'Fix login bug' is due in 6 hours"` |
| `fired_at` | `datetime` | When this notification was created |
| `status` | `"unread" \| "read"` | Whether the notification has been acknowledged |

---

## Endpoints

### Health

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Returns service status and MCP server reachability |

Response:
```json
{
  "status": "ok",
  "mcp_url": "http://task-mcp-server.project-task-mcp.svc.cluster.local:8000/mcp",
  "mcp_reachable": true,
  "active_rules": 2,
  "poll_interval_seconds": 60
}
```

---

### Rules

| Method | Path | Description |
|---|---|---|
| `POST` | `/notify/rules` | Register a project to watch |
| `GET` | `/notify/rules` | List all active rules |
| `DELETE` | `/notify/rules/{rule_id}` | Remove a rule |

`POST /notify/rules` request body:
```json
{
  "project": "task-agent",
  "threshold_hours": 24
}
```

---

### Notifications (Inbox)

| Method | Path | Description |
|---|---|---|
| `GET` | `/notifications` | List notifications (newest first) |
| `POST` | `/notifications/{id}/read` | Mark a notification as read |
| `DELETE` | `/notifications` | Clear the entire inbox |

`GET /notifications` query params:
- `status` — filter by `unread` or `read` (omit for all)
- `project` — filter by project name

Example response:
```json
[
  {
    "id": "a1b2c3d4-...",
    "task_id": "19244de1-...",
    "task_title": "Write Step 3 integration",
    "project": "task-agent",
    "due_date": "2026-05-18T10:00:00Z",
    "message": "Task 'Write Step 3 integration' is due in 18 hours",
    "fired_at": "2026-05-17T16:00:00Z",
    "status": "unread"
  }
]
```

---

### Manual Trigger (for testing)

| Method | Path | Description |
|---|---|---|
| `POST` | `/notify/trigger` | Run an immediate deadline check right now |

This calls the same logic as the background job on demand — useful for testing without
waiting 60 seconds.

Response:
```json
{
  "checked_projects": ["task-agent"],
  "new_notifications": 2,
  "skipped_duplicates": 1
}
```

---

## Configuration (Environment Variables)

| Variable | Default | Description |
|---|---|---|
| `TASK_MCP_URL` | `http://localhost:8000/mcp` | MCP endpoint of `task-mcp-server` |
| `POLL_INTERVAL_SECONDS` | `60` | How often the background job runs |
| `DEFAULT_THRESHOLD_HOURS` | `24` | Default look-ahead window for new rules |
| `MAX_NOTIFICATIONS` | `200` | Max inbox size — oldest dropped when exceeded |

---

## MCP Client

The notification-api is **not** an agent — it only needs to call MCP tools directly, not
run an agent loop. It will use the `mcp` library's low-level `streamablehttp_client` to
call `project_view` and `task_get` on `task-mcp-server`.

This keeps the dependency footprint small: `fastapi[standard]`, `mcp[cli]`, `pydantic`.
No `openai-agents` SDK needed.

---

## State

All state is in-memory. Rules and notifications are lost on pod restart.

This is intentional for this project — persistence (Redis, database) is deferred.
The consequence: after a restart, you must re-register rules via `POST /notify/rules`.

---

## What This Service Does NOT Do

- Send email, SMS, Slack messages, or any external notification
- Persist rules or notifications across pod restarts
- Subscribe to a task event stream (there is none — it polls)
- Authenticate callers (no auth in this project)

---

## File Layout

```
notification-api/
├── pyproject.toml
├── uv.lock
├── Dockerfile
├── .dockerignore
├── .env.example
└── src/
    ├── api.py          # FastAPI app, lifespan, all endpoints
    ├── models.py       # Rule and Notification Pydantic models
    ├── store.py        # In-memory Rules store and Notification inbox
    ├── scheduler.py    # Background polling loop (asyncio task)
    └── mcp_client.py   # Thin wrapper around MCP streamablehttp_client
```

---

## Connections Summary

```
notification-api
    │
    └── MCP (Streamable HTTP) ──► task-mcp-server:8000/mcp
                                    (calls: project_view, task_get)
```

No connection to `task-agent`.
