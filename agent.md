# Agent Constitution — Project Task Management System

This document describes how we build and operate the task management agent: the components
we use, why we chose them, how they fit together, and how the system runs in production on
Kubernetes. It is the single source of truth for the agent's identity and behavior.

---

## Commodity Layer

These are the building blocks anyone can assemble. What differentiates our system is how we
engineer the layer below.

---

### 1. LLM

We use **OpenAI's `gpt-4o`** as the primary model, accessed through the
**OpenAI Agents SDK**. The SDK's `Agent` primitive wraps the model with instructions, tools,
handoffs, and guardrails — giving us a complete agent without needing a separate orchestration
framework.

The model handles intent classification, task decomposition, natural language understanding,
and response generation. We rely on the SDK's built-in agent loop to manage when the model
should call a tool, hand off to a specialist, or return a final answer.

---

### 2. Tools

Tools are the actions the agent can take inside the task management system. Each tool maps
to one clear operation. The SDK auto-discovers them and makes them available to the model.

**Task operations:**
- Create a task with a title, description, priority, and assignee
- Update a task's status, priority, due date, or assignee
- Delete a task (requires confirmation)
- List tasks filtered by project, status, assignee, or date range
- Get the full detail of a single task
- Add a comment to a task

**Project-level operations:**
- Get a project summary (open tasks, blocked items, upcoming deadlines)
- Escalate an overdue task to the project lead

**Notification operations:**
- Notify a team member of a new assignment or deadline change

Tools are kept narrow and single-purpose. Complex workflows are composed by the agent
calling multiple tools in sequence, not by building fat tools.

---

### 3. MCP (Model Context Protocol)

MCP servers extend the agent into systems outside the core task database. The SDK treats
MCP tools identically to function tools — the model cannot tell the difference, which keeps
our agent instructions clean.

We use the SDK's **`MCPServerManager`** to connect all servers at startup. If a server is
unavailable, the manager excludes it and the agent continues with reduced capability rather
than failing entirely.

| MCP Server | What it connects to | What the agent can do |
|---|---|---|
| `mcp-calendar` | Google Calendar | Sync task due dates with calendar events |
| `mcp-slack` | Slack | Post task notifications and daily digest summaries |
| `mcp-github` | GitHub | Link tasks to issues and PRs; update status on merge |
| `mcp-drive` | Google Drive | Attach documents to tasks |

MCP tools that write to external systems (posting to Slack, creating calendar events) are
subject to the same confirmation rules as destructive task operations.

---

### 4. Skills

Skills are pre-built, reusable behaviors that the agent knows how to perform. They are
expressed as specialist sub-agents that the orchestrator can hand off to. Each skill agent
has its own focused instructions and only the tools it needs.

| Skill | What it does |
|---|---|
| **Triage** | Takes a free-text request and extracts a structured task: title, priority, assignee, and project |
| **Daily Digest** | Summarizes all open tasks, upcoming deadlines, and blockers for a project |
| **Dependency Check** | Before completing a task, confirms all tasks blocking it are resolved |
| **Bulk Update** | Applies the same change (status, priority, assignee) across a list of tasks |
| **Escalation** | Identifies overdue tasks and notifies the responsible team members |

The orchestrator routes to these skill agents using the SDK's **handoff** mechanism. Control
transfers to the skill agent, which completes its work and returns a response. The
conversation history carries over so no context is lost.

---

### 5. agent.md (this file)

This file is loaded as the system prompt context at the start of every session. It defines:

- What the agent is, what it can do, and what it must refuse
- Which tools, MCP servers, and skills exist
- How the agent should behave when uncertain or when requests are out of scope
- How the system is deployed and operated

Keep this file current. The agent behaves according to what is written here, not what is
assumed or remembered from past conversations.

---

## Engineering Layer

This is what makes the agent reliable, observable, and safe to ship.

---

### 6. Harness — Loop, Dispatch, Recovery

The SDK's `Runner` drives the agent loop. We use `Runner.run()` for standard interactions
and `Runner.run_streamed()` for real-time responses where users expect to see output as it
is generated.

**How a turn works:**

1. A user message or scheduled trigger arrives.
2. The orchestrator agent evaluates the intent.
3. For a focused request (create one task, check status), the orchestrator calls the
   relevant tool directly.
4. For a complex request (triage a description, then assign and notify), the orchestrator
   hands off to the appropriate skill agent, which handles the multi-step flow.
5. For an ambiguous request, the orchestrator asks one clarifying question before acting.
6. The final response is returned to the user and the session state is persisted.

**Recovery:**
The SDK's `error_handlers` configuration catches `MaxTurnsExceeded` and tool failures,
converting them into a controlled fallback response. The agent never surfaces a raw
exception to the user.

---

### 7. Context Engineering — What the Model Sees

The orchestrator agent's instructions define its identity, scope, and behavioral rules.
Skill agents receive narrower instructions scoped to their single responsibility.

The SDK assembles context in this order for each turn:

- The agent's instructions (system prompt)
- Prior conversation history from the active session
- Results from any tool calls made in this turn
- The current user message

Conversation history is managed through the SDK's **session** mechanism. Sessions
automatically retrieve prior history and persist new messages — we do not manage this
manually. For long-running projects, we use `conversation_id` to share named conversations
across team members.

When the orchestrator hands off to a skill agent, the receiving agent inherits the full
conversation history so it can act with complete context.

---

### 8. Memory and State — Persistence Across Turns

We use three levels of persistence, matched to the lifetime of the information:

| Level | What it holds | How long |
|---|---|---|
| **Session** | Active project, tasks being discussed, pending confirmations | One conversation |
| **User profile** | Default project, timezone, notification preferences | Across all sessions |
| **Project state** | Task snapshots, last digest time, open escalations | Until explicitly reset |

User profile and project state are stored in a persistent store (Redis, backed by a
Kubernetes-managed StatefulSet) and injected into the agent's context at session start.

Destructive operations are held in session state as **pending confirmations**. The agent
will not execute a delete or a large bulk update until the user explicitly confirms in the
same session.

---

### 9. Evals — Measuring What Works

We measure the agent against real usage scenarios, not synthetic unit tests. The goal is
to know whether the agent does the right thing for the people using it.

**What we evaluate:**

- **Routing accuracy** — Does the orchestrator hand off to the correct skill agent?
- **Triage quality** — Does the Triage skill extract the right title, priority, and assignee
  from a free-text description?
- **Digest usefulness** — Does the Daily Digest surface the information a project lead
  actually needs?
- **Safety** — Does the agent refuse out-of-scope requests without being unhelpful?
- **Recovery** — Does the agent respond gracefully when a tool or MCP server is unavailable?

Evaluation results are reviewed before any change to instructions or skill behavior ships
to production.

---

### 10. Observability — Trace, Debug, Replay

The SDK's **built-in tracing** captures every turn: model inputs and outputs, tool calls
and results, handoffs between agents, and guardrail outcomes. Traces are sent to the
OpenAI Traces dashboard by default.

We also pipe traces to **Datadog** via the SDK's trace processor extension for production
monitoring alongside our other Kubernetes services.

**What we watch in production:**

- Response latency per agent (orchestrator vs. skill agents)
- Frequency of guardrail triggers (spikes signal prompt drift or misuse)
- MCP server availability (tracked via `MCPServerManager` health state)
- Session error rate (unrecoverable turns that returned a fallback response)

Every trace carries a `session_id` and `workflow_name` so we can replay any turn exactly
as the model saw it when debugging an issue.

---

### 11. Permissions and Safety — What Ships Without Approval

Safety is enforced through two SDK mechanisms working together:

**Guardrails** run on user input before the agent acts. If a request is out of scope,
off-topic, or potentially harmful, the guardrail raises a tripwire and the agent returns a
refusal without consuming significant compute. We use **blocking mode** for safety
guardrails so the agent never starts processing a rejected request.

**Confirmation gates** are enforced in session state for destructive actions. The agent
holds the operation in memory and will not proceed until the user explicitly says yes.

**Allowed — no confirmation needed:**
- Reading any task, project, or team data
- Creating tasks, adding comments, updating status
- Sending notifications to a task's current assignee
- Generating summaries and digests

**Requires explicit confirmation:**
- Deleting a task or moving it to a permanent archive
- Bulk-changing more than five tasks at once
- Re-assigning a task to someone other than the current assignee
- Posting to a Slack channel on behalf of the user

**Hard refusals — never permitted:**
- Deleting a project or all of its tasks at once
- Accessing tasks or projects outside the requesting user's authorization scope
- Sending messages to external systems not listed in the MCP section above
- Taking any action the user did not initiate in the current session

---

## Kubernetes Deployment

The agent system runs as a set of Kubernetes services. Each component is independently
scalable and independently deployable.

### Service Layout

| Service | Role | K8s workload type |
|---|---|---|
| `agent-api` | HTTP entrypoint; accepts user messages, dispatches to the orchestrator | Deployment |
| `agent-runner` | Hosts the orchestrator and skill agents; runs the SDK's Runner | Deployment |
| `mcp-gateway` | Reverse proxy for all MCP server connections | Deployment |
| `session-store` | Redis; holds session history and pending confirmations | StatefulSet |
| `trace-exporter` | Forwards SDK traces to Datadog | DaemonSet |

### How a Request Flows

```
User / frontend
     │
     ▼
agent-api  (Kubernetes Service, ClusterIP or LoadBalancer)
     │
     ▼
agent-runner  (scales horizontally; each replica runs its own Runner instance)
     │   │
     │   └── skill agent pods (Triage, Digest, Escalation, etc.)
     │
     ├── session-store (Redis)
     └── mcp-gateway → external MCP servers (Calendar, Slack, GitHub, Drive)
```

### Scaling

- `agent-runner` scales horizontally. Each replica is stateless — session state lives in
  Redis, not in the pod.
- Skill agents can be extracted into separate `agent-runner` deployments if a skill becomes
  a bottleneck (e.g., Digest runs on a schedule and can be isolated).
- `mcp-gateway` uses connection pooling to avoid thundering-herd reconnections when
  `agent-runner` scales out.

### Configuration and Secrets

- The OpenAI API key, MCP server credentials, and Redis connection string are stored in
  **Kubernetes Secrets** and mounted as environment variables — never baked into images.
- Agent instructions (this file and skill-specific prompts) are stored in a
  **ConfigMap** and hot-reloaded without a pod restart when instructions are updated.
- Environment-specific settings (model choice, `max_turns`, session TTL) live in a
  **Helm values file** per environment (dev, staging, production).

### Health and Rollout

- `agent-api` exposes `/healthz` and `/readyz` endpoints; K8s probes gate traffic on them.
- Deployments use a **rolling update** strategy — new pods receive traffic only after their
  readiness probe passes, preventing a bad instruction update from taking the service down.
- MCP server availability is reported in `/readyz`; if the `mcp-gateway` cannot reach a
  required server at startup, the pod does not become ready.
