# Task MCP Server — Tool Design

## The Problem with CRUD and REST

Five design options were considered:

**Pure CRUD (4 tools)** — create, read, update, delete. Minimal surface. The agent
composes everything. Problem: a status change and a title fix are both just `update`. No
semantic meaning. The agent needs multiple round trips to do anything meaningful.

**REST principles** — resources (tasks, comments, projects) with their own CRUD. Clean
for humans calling an API. Bad for agents — it explodes tool count and still does not
capture intent. Agents do not think in resources, they think in goals.

**CRUD + notify** — same problems as CRUD with an extra notification tool bolted on.

**Merge some** — reduces tool count by collapsing overlaps. Better, but still maps to
database surface rather than to work.

**Human intent / workflow** — design around what a human actually *does*, not what the
database can do. Each tool = one complete unit of work. A single call achieves something
meaningful end-to-end.

## Why Workflow-Oriented Design

Agents are fulfilling human intent, not talking to a database. When someone says "block
this task — it's waiting on the API spec", that is one human action. The tool should
accept it as one call, not `update(status=blocked)` followed by `add_comment(...)`.

The key insight: **status changes are events, not field patches**. Every real status
change has a reason. Enforcing a note on transitions makes the history self-explanatory
without a separate comment step.

## What Humans Actually Do in a Task System

- Open a task (create it fully set up — title, assignee, priority in one action)
- Move a task forward (change status and say why)
- Correct something (fix a title, change a due date, add a note)
- Look at one task in detail
- Get a project health overview
- Delete something that should not exist

These six actions map directly to six tools.

## The Final 6 Tools

### `task_create`
Full task setup in one call. Accepts everything a human fills in when opening a new
ticket: title, description, project, assignee, priority, due date, tags. Returns the
created task. One human action = one tool call.

### `task_transition`
Status changes only — `todo → in_progress → blocked → done` — with a **required** `note`
field. The note is mandatory because every meaningful status change has a reason:
- "Blocked — waiting on API spec from platform team"
- "Done — deployed to staging, smoke tested"

This makes the task history self-explanatory without needing a separate comment step.
This is the most important tool in the set.

### `task_update`
Handles two things merged into one tool:
- **Field edits** — title, description, assignee, priority, due date, tags (all optional,
  partial update pattern)
- **Adding a note/comment** — optional `comment` field

Merged because both are non-event changes to a task. Pass only a comment, only field
changes, or both together. No reason to split them into separate tools.

### `task_delete`
Removes a task permanently. Annotated `destructiveHint: true`. The confirmation gate
(asking the user before executing) is enforced at the agent level, not inside this server.

### `task_get`
Full detail on one task — all fields, all comments, full history. Single call gives the
agent everything it needs to reason about a task.

### `project_view`
Project health in one call: total tasks, breakdown by status, overdue count, blocked
tasks with their blocking reasons, tasks grouped by assignee. Designed so the Digest
skill agent completes its entire job in one tool call.

## Efficiency Comparison

| Scenario | CRUD calls | Workflow calls |
|---|---|---|
| Create and assign a task | 2 (create + update) | 1 (`task_create`) |
| Block a task with a reason | 2 (update status + add comment) | 1 (`task_transition`) |
| Morning project review | 3–4 (list + filter + summarize) | 1 (`project_view`) |
| Correct a title and add a note | 2 (update + comment) | 1 (`task_update`) |

## Tool Annotations

| Tool | readOnly | destructive | idempotent |
|---|---|---|---|
| `task_create` | No | No | No |
| `task_transition` | No | No | No |
| `task_update` | No | No | Yes |
| `task_delete` | No | **Yes** | Yes |
| `task_get` | Yes | No | Yes |
| `project_view` | Yes | No | Yes |

## Naming Convention

Tools use `task_` or `project_` prefix (no redundant `_task` suffix on the verb). This
avoids collisions when multiple MCP servers are connected simultaneously (Slack, GitHub,
Calendar). `task_create` not `tasks_create_task`.
