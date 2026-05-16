# Deployments

This directory contains all Kubernetes manifests for the task-management-agent system.
Every service in the cluster is declared here — no manifests live inside service folders.

---

## Namespace

**`project-task-mcp`** — manually created via `kubectl create namespace project-task-mcp`.

All resources below belong to this namespace.

---

## Services

### task-mcp-server

| File | Purpose |
|------|---------|
| `task-mcp-server/deployment.yaml` | Runs the MCP server container |
| `task-mcp-server/service.yaml` | Exposes it inside the cluster on port 8000 |

**What it is:**
A FastMCP HTTP server that exposes task management tools (`task_create`, `task_get`,
`task_update`, `task_delete`, `task_transition`, `project_view`) over the Streamable HTTP
transport at `/mcp`.

**Why a Deployment:**
The server is stateless — all task data lives in memory inside the pod. A Deployment gives
us a self-healing pod (automatic restart on crash) with a clean rolling-update path for
future image upgrades.

**Why ClusterIP (not LoadBalancer or NodePort):**
The MCP server is an internal dependency of `task-agent`. It does not need to be reachable
from outside the cluster. ClusterIP keeps it private and reachable only within the cluster
via DNS: `http://task-mcp-server.project-task-mcp.svc.cluster.local:8000/mcp`.

For local testing you can port-forward:
```bash
kubectl port-forward svc/task-mcp-server 8000:8000 -n project-task-mcp
```

**Security decisions:**
- `runAsNonRoot: true` + `runAsUser: 999` — the Dockerfile creates a `mcp` system user
  (UID 999). The numeric UID is required because Kubernetes cannot verify non-root status
  from a named user alone.
- `readOnlyRootFilesystem: true` — the server never writes to disk; a read-only filesystem
  prevents an attacker from dropping payloads into the container.
- `allowPrivilegeEscalation: false` + `capabilities: drop: [ALL]` — least-privilege baseline.

**Health probes:**
Both liveness and readiness use `tcpSocket` on port 8000, matching the `HEALTHCHECK`
in the Dockerfile. FastMCP's `/mcp` endpoint only accepts POST/SSE — a plain HTTP GET
would return a non-200, so TCP socket is the right probe type here.

---

### task-agent

| File | Purpose |
|------|---------|
| `task-agent/secret.yaml` | Template for API keys (fill before applying) |
| `task-agent/deployment.yaml` | Runs the agent container |

**What it is:**
A Python agent built on the OpenAI Agents SDK. It connects to `task-mcp-server` via MCP,
uses Gemini as its inference model, and sends traces to OpenAI's trace dashboard.
Requires three runtime secrets: `GEMINI_API_KEY`, `OPENAI_API_KEY`, and `TASK_MCP_URL`.

**Why a Deployment (not a Job):**
The current image runs a two-turn demo script and exits, so the pod will enter
CrashLoopBackOff in this environment — that is expected and intentional for dev/testing.
A Deployment is used rather than a Job because the architecture is designed to evolve this
into a long-running agent service (`agent-runner`). Keeping it as a Deployment means the
manifest, RBAC, and networking patterns are already in place when the code makes that
transition.

**Why a Secret for API keys:**
`GEMINI_API_KEY` and `OPENAI_API_KEY` are sensitive credentials. They are stored in a
Kubernetes Secret and injected as environment variables at runtime — never baked into the
image or committed to git.

**`TASK_MCP_URL` is a plain env var** (not a Secret) because it is the in-cluster DNS
address of `task-mcp-server` — not sensitive, and deterministic:
`http://task-mcp-server.project-task-mcp.svc.cluster.local:8000/mcp`

**Security decisions:**
- `runAsNonRoot: true` + `runAsUser: 999` — same reasoning as `task-mcp-server`; the
  Dockerfile creates an `agent` system user at UID 999.
- `readOnlyRootFilesystem: false` — the agent uses `SQLiteSession` which writes a `.db`
  file to `/app` (the working directory). A read-only filesystem would crash the agent
  at session initialisation. This is a known trade-off; a future improvement is to mount
  an `emptyDir` volume at a dedicated path and point the session there.
- `allowPrivilegeEscalation: false` + `capabilities: drop: [ALL]` — least-privilege baseline.

---

## What Is Not Here Yet

These will be added in later phases:

| Resource | Reason deferred |
|----------|----------------|
| RBAC (ServiceAccount / Role / RoleBinding) | Neither service calls the Kubernetes API — adding RBAC before it is needed adds noise without security benefit |
| NetworkPolicies | Planned for a hardening pass once both services are stable |
| Ingress | Not needed until the agent exposes an HTTP API to end users |
| Redis / session-store StatefulSet | The current agent uses SQLite for sessions; Redis is the production target |

---

## Apply Order

```bash
# 1. Fill in real API key values
#    Edit deployments/task-agent/secret.yaml  OR  use kubectl:
kubectl create secret generic task-agent-secrets \
  --from-literal=GEMINI_API_KEY=<your_key> \
  --from-literal=OPENAI_API_KEY=<your_key> \
  --namespace=project-task-mcp \
  --dry-run=client -o yaml | kubectl apply -f -

# 2. Apply MCP server
kubectl apply -f deployments/task-mcp-server/

# 3. Apply agent
kubectl apply -f deployments/task-agent/deployment.yaml

# 4. Verify
kubectl rollout status deployment/task-mcp-server -n project-task-mcp
kubectl get pods -n project-task-mcp
kubectl logs -l app=task-mcp-server -n project-task-mcp
kubectl logs -l app=task-agent -n project-task-mcp
```
