# Implementation Plan — Task MCP Server

## Context

Building the Task Management MCP server defined in `spc/task-server-tools.md` and
`spc/mcp_dic.md`. Six workflow-oriented tools over Streamable HTTP, in-memory Python
dicts for storage, FastMCP + Pydantic v2, built test-first. After unit tests pass the
server is started live and every tool is exercised through MCP Inspector before done.

---

## Step 1 — Project Setup (UV CLI)

Location: `class_32_project_dev/task-mcp-server/`

```bash
uv init task-mcp-server
cd task-mcp-server
uv add "mcp[cli]" pydantic
uv add --dev pytest pytest-asyncio
```

`mcp[cli]` installs FastMCP and the MCP Inspector CLI helper.
`pytest-asyncio` is required because all FastMCP tools are async functions.

---

## Step 2 — Project Structure

```
task-mcp-server/
├── pyproject.toml
├── src/
│   └── task_mcp/
│       ├── __init__.py
│       ├── server.py        ← FastMCP app + transport startup
│       ├── models.py        ← Pydantic models: Task, Comment, enums
│       ├── store.py         ← In-memory dict + all read/write functions
│       └── tools/
│           ├── __init__.py  ← registers all tools onto the FastMCP app
│           ├── task_create.py
│           ├── task_transition.py
│           ├── task_update.py
│           ├── task_delete.py
│           ├── task_get.py
│           └── project_view.py
└── tests/
    ├── conftest.py          ← shared fixtures: store reset, sample task factory
    ├── test_models.py
    ├── test_store.py
    ├── test_task_create.py
    ├── test_task_transition.py
    ├── test_task_update.py
    ├── test_task_delete.py
    ├── test_task_get.py
    └── test_project_view.py
```

---

## Step 3 — Data Models (`models.py`)

**Enums**
- `TaskStatus`: `todo | in_progress | blocked | done`
- `Priority`: `low | medium | high | urgent`

**Comment** — `id` (UUID), `author`, `body`, `created_at`

**Task** — `id` (UUID), `title`, `description`, `status`, `priority`, `assignee`,
`project_name`, `due_date`, `tags`, `comments: list[Comment]`, `created_at`, `updated_at`

`project_name` is the project identifier in v1 — no separate project entity needed.
`task_create` accepts a plain string. `project_view` groups tasks by it. This eliminates
the need for a `project_create` tool, keeping the surface at 6 tools.

---

## Step 4 — In-Memory Store (`store.py`)

A single module-level dict: `_tasks: dict[str, Task]`

Store exposes plain functions (not a class):

| Function | Purpose |
|---|---|
| `save_task(task)` | Insert or overwrite |
| `get_task(task_id)` | Return Task or None |
| `all_tasks()` | Return list of all tasks |
| `tasks_for_project(project_name)` | Filtered list |
| `delete_task(task_id)` | Remove, return bool |
| `reset()` | Clear all — used by tests only |

`reset()` is called in `conftest.py` before each test to guarantee isolation.

---

## Step 5 — TDD Build Order

Tests are written **before** the implementation file exists.
Each cycle: write test → run (red) → implement minimum code → run (green).

### Cycle 1 — `models.py`
- Valid Task construction
- Invalid status value rejected by Pydantic
- Priority defaults to `medium`
- Comment auto-assigns `created_at`

### Cycle 2 — `store.py`
- Save and retrieve a task
- Get non-existent task returns None
- Delete removes task, returns True
- Delete unknown ID returns False
- `all_tasks()` returns everything saved
- `tasks_for_project()` filters by project name
- `reset()` clears store

### Cycle 3 — `task_get`
- Returns full task with embedded comments
- Returns error message for unknown ID

### Cycle 4 — `task_create`
- Creates task with all fields provided
- Creates with only required fields (title + project_name)
- Auto-assigns UUID, `created_at`, `updated_at`
- Status starts at `todo`, priority defaults to `medium`

### Cycle 5 — `task_transition`
- Valid transition succeeds, appends comment with note
- Invalid status value is rejected
- Missing note is rejected
- Unknown task ID returns error
- `updated_at` changes after transition

### Cycle 6 — `task_update`
- Updating one field leaves all others unchanged
- Updating multiple fields at once
- Passing only a comment adds it, no other field changes
- Passing both field changes and comment does both
- Unknown task ID returns error

### Cycle 7 — `task_delete`
- Existing task is removed from store
- Subsequent `task_get` returns not-found error
- Deleting unknown ID returns descriptive error

### Cycle 8 — `project_view`
- Returns correct total task count
- Correct count per status
- Identifies overdue tasks (due_date in past + status not `done`)
- Lists blocked tasks with their blocking note
- Groups tasks by assignee
- Handles project with zero tasks gracefully

Run full suite after each cycle:
```bash
uv run pytest -v
```

---

## Step 6 — Server Entry Point (`server.py`)

FastMCP app named `task_mcp`. Imports all tools from `tools/__init__.py` which registers
them via `@mcp.tool` decorators.

Start command:
```bash
uv run python -m task_mcp
```

Transport: Streamable HTTP, host `0.0.0.0`, port `8000`.
Single endpoint: `http://localhost:8000/mcp`

---

## Step 7 — End-to-End Live Validation

With the server running, connect MCP Inspector:
```bash
npx @modelcontextprotocol/inspector http://localhost:8000/mcp
```

Execute this sequence to cover every tool and every meaningful state:

| Step | Tool | What it validates |
|---|---|---|
| 1 | `task_create` | Task A — "Implement login", project "auth", assignee "maya", high priority |
| 2 | `task_create` | Task B — "Write API spec", project "auth", no assignee, medium |
| 3 | `task_create` | Task C — "Deploy to staging", project "auth", assignee "john", urgent, due yesterday |
| 4 | `task_get` | Fetch task A — all fields present, comments empty |
| 5 | `task_transition` | Task A → `in_progress`, note: "Maya picking this up today" |
| 6 | `task_transition` | Task A → `blocked`, note: "Blocked on task B — need API spec first" |
| 7 | `task_update` | Task B — add assignee "sara" + comment "Sara owns this now" |
| 8 | `task_get` | Fetch task A — blocked status, two comments in history |
| 9 | `project_view` | "auth" — 3 total, 1 blocked with note, 1 overdue (task C), by-assignee breakdown |
| 10 | `task_delete` | Delete task C |
| 11 | `project_view` | "auth" again — 2 total, task C gone |

All 6 tools exercised. Blocked task with note, overdue detection, partial update, comment
threading, and delete all verified against a live running server.

---

## Files to Create

| File | Purpose |
|---|---|
| `task-mcp-server/pyproject.toml` | UV project config + dependencies |
| `task-mcp-server/src/task_mcp/models.py` | Pydantic data models + enums |
| `task-mcp-server/src/task_mcp/store.py` | In-memory storage functions |
| `task-mcp-server/src/task_mcp/tools/*.py` | One file per tool (6 files) |
| `task-mcp-server/src/task_mcp/server.py` | FastMCP app + transport startup |
| `task-mcp-server/tests/conftest.py` | Shared fixtures + store reset |
| `task-mcp-server/tests/test_*.py` | One test file per module (8 files) |
