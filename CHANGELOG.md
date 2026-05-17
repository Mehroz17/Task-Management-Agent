# Changelog

All significant milestones are recorded here in reverse chronological order.

---



**Next:** Add RBAC and NetworkPolicies

---

## [2026-05-17] — Fix Multi-Turn Session Memory

**Root cause**
`SQLiteSession` defaults to `db_path=":memory:"` — an in-memory database destroyed at the end of every HTTP request. Every call to `POST /agent/run` got a fresh empty session regardless of the `session_id` passed.

**Fix**
- Write each session to `/tmp/sessions/{session_id}.db` (absolute file path, always writable by the non-root `agent` user)
- `/app/sessions` was attempted first but raised `PermissionError` — `agent` user (UID 999) has no write access to `/app`

**Verified**
- Turn 1: `"my name is Alen and I want you to create a task to bring fruits"` → task created ✓
- Turn 2 (same `session_id`): `"whats my name and what have we done so far?"` → agent recalled name and prior task ✓

**Note:** Sessions survive across requests but are lost on pod restart (stored in `/tmp`). A PVC would be needed for true cross-restart persistence.

---

## [2026-05-17] — GHCR Packages Made Public + Deployments Switched to :latest

**What was done**
- Made both GHCR packages public — no credentials or imagePullSecrets required
  - `ghcr.io/mehroz17/task-management-agent/task-agent`
  - `ghcr.io/mehroz17/task-management-agent/task-mcp-server`
- Updated both deployment manifests to use `:latest` + `imagePullPolicy: Always`
- Removed `command:` override from task-agent deployment — Dockerfile CMD is now correct (`fastapi run src/api.py`)
- Added NodePort Service for task-agent on port `30090` — API reachable at `http://localhost:30090`
- Added `kubectl rollout restart` as the standard update flow after CI pushes a new image
- Updated `README.md` with public image note, image table, and Kubernetes deploy instructions

**Update flow going forward**
```
push code → CI builds + pushes :latest → kubectl rollout restart deployment/<name> -n project-task-mcp
```

**Verified**
- `GET http://localhost:30090/health` → `{"status": "ok", "mcp_url": "..."}` ✓
- `POST http://localhost:30090/agent/run` → task created via MCP, UUID returned ✓

---

## [2026-05-17] — task-agent: FastAPI Interface

**What was done**
- Added `fastapi[standard]` dependency to `task-agent/pyproject.toml` via `uv add`
- Created `task-agent/src/api.py` — single-file FastAPI wrapper around the existing `SandboxAgent`:
  - **Lifespan** opens one `MCPServerStreamableHttp` connection on startup; agent and `RunConfig` stored in `app.state`
  - `GET /health` — liveness check, returns MCP URL
  - `POST /agent/run` — accepts `{message, session_id?}`, runs `Runner.run`, returns `{session_id, output, new_session}`; `session_id` auto-generated (UUID) when omitted for multi-turn via `SQLiteSession`
- Added `[tool.fastapi] entrypoint = "api:app"` to `pyproject.toml`
- Updated `README.md`: task-agent marked complete, endpoints documented with request/response examples

**Design decisions**
- Two endpoints only — agent handles all task operations (create, list, get) via natural language; no need to expose raw MCP tools as REST
- Single file — the agent logic was already written; the API is a thin wrapper
- `async def` endpoints — `Runner.run` is fully async
- Agent instance shared across requests — `SandboxAgent` is stateless per run (each call gets its own ephemeral sandbox)

**Verified end-to-end**
- `GET /health` → `{"status": "ok", "mcp_url": "http://127.0.0.1:8000/mcp"}`
- `POST /agent/run` with `"Create a task titled 'Agent run test'..."` → agent called `task_create`, confirmed via `task_get`, wrote `summary.txt` in sandbox, returned task id and confirmation

**Run**
```bash
cd task-agent && fastapi dev src/api.py --port 8090
# → http://127.0.0.1:8090/docs
```

---

## [2026-05-17] — End-to-End Cluster Test: All Services Verified

**What was done**
- Populated Kubernetes Secret `task-agent-secrets` with real API keys sourced from `task-agent/.env`
  via `kubectl create secret --from-literal` with `--dry-run=client -o yaml | kubectl apply -f -`
- Restarted `task-agent` deployment to pick up the new secret: `kubectl rollout restart deployment/task-agent`
- Streamed full pod logs for both services to verify correct behaviour

**Infrastructure results**

| Resource | Result |
|---|---|
| `task-mcp-server` pod | `1/1 Running` — healthy throughout |
| `task-mcp-server` ClusterIP service | Reachable inside cluster via DNS |
| `task-agent` pod | `1/1 Running` → exited cleanly after 2-turn script |
| Secret injection (`GEMINI_API_KEY`, `OPENAI_API_KEY`) | Correctly mounted and consumed |

**Agent execution results**

*Turn 1 — Task creation via MCP:*
- Agent resolved `http://task-mcp-server.project-task-mcp.svc.cluster.local:8000/mcp` — in-cluster DNS working
- Called `task_create` → task created: title `"Write Step 3 integration"`, project `task-agent`, priority `high`
- Task ID returned: `19244de1-da4a-4035-b799-95f4b80e4039`
- Agent called `task_get` with the returned ID to confirm persistence — task confirmed in store
- Wrote `"Created task: Write Step 3 integration (id: 19244de1-...)"` to `outputs/summary.txt` inside the sandbox
- Confirmed the write with `cat outputs/summary.txt`
- **Result: PASS**

*Turn 2 — Project view via MCP:*
- Agent called `project_view` with project name `task-agent`
- Returned 1 task in `todo` status — consistent with Turn 1 creation
- Session memory (SQLiteSession) carried context across turns — agent recalled what it created
- **Result: PASS**

**What the test confirmed**
- In-cluster DNS resolution works — agent reached the MCP server by Kubernetes service name
- FastMCP Streamable HTTP transport (`/mcp` endpoint) functions correctly inside the cluster
- `task-mcp-server` in-memory store persisted the task across two separate MCP calls in the same session
- Gemini model (`gemini-3.1-flash-lite`) is reachable from inside the pod (external HTTPS egress works)
- OpenAI tracing active — traces sent to OpenAI dashboard using `OPENAI_API_KEY`
- Kubernetes Secret injection works — both keys consumed without errors

**Bug found and fixed during apply**
- Both pods started with `CreateContainerConfigError`: `container has runAsNonRoot and image has non-numeric user (mcp/agent), cannot verify user is non-root`
- Root cause: Dockerfiles use named users (`USER mcp`, `USER agent`) but Kubernetes requires a numeric UID to enforce `runAsNonRoot: true`
- Fix: added `runAsUser: 999` and `runAsGroup: 999` to both deployment securityContexts (confirmed via `docker run ... id`)
- Manifests updated and re-applied — both pods came up clean on second apply

**Note on secret management**
- The Kubernetes Secret is not automatically linked to `task-agent/.env` — it was populated manually
- To re-sync after key rotation: `export $(grep -v '^#' task-agent/.env | xargs) && kubectl create secret generic task-agent-secrets --from-literal=GEMINI_API_KEY="$GEMINI_API_KEY" --from-literal=OPENAI_API_KEY="$OPENAI_API_KEY" --namespace=project-task-mcp --dry-run=client -o yaml | kubectl apply -f -`

---

## [2026-05-17] — Kubernetes Deployment Plan: project-mcp namespace

**What was done**
- Planned full Kubernetes deployment for the two production images:
  - `ghcr.io/mehroz17/task-management-agent/task-mcp-server:sha-9e143707c001d6d789fe4d643652debd8ad4f239`
  - `ghcr.io/mehroz17/task-management-agent/task-agent:sha-6fe471a4054a357f9eee850c2fd5a373ac58fdb7`
- Target environment: local cluster (kind / minikube)
- Namespace: `project-task-mcp` (manually created via `kubectl create namespace project-task-mcp`)
- Manifest layout (per `agent.md` convention — all manifests under `deployments/`):
  - `deployments/task-mcp-server/deployment.yaml` — Deployment, port 8000
  - `deployments/task-mcp-server/service.yaml` — ClusterIP
  - `deployments/task-agent/secret.yaml` — template for `GEMINI_API_KEY` + `OPENAI_API_KEY`
  - `deployments/task-agent/deployment.yaml` — Deployment, env wired to MCP server in-cluster DNS
  - `namespace.yaml` skipped — namespace `project-task-mcp` was created manually
- Deliberate omissions for this phase: no RBAC (ServiceAccount / Role / RoleBinding), no NetworkPolicies
- Security context decisions:
  - `task-mcp-server`: `readOnlyRootFilesystem: true`, `runAsNonRoot: true` — stateless, no disk writes
  - `task-agent`: `readOnlyRootFilesystem: false` — SQLiteSession writes `.db` file to `/app`; `runAsNonRoot: true`
- task-agent deployed as a Deployment (future-proof for long-running agent); current image runs a 2-turn script and exits, so pod will CrashLoopBackOff — expected in dev, check logs per-run
- In-cluster MCP URL for task-agent: `http://task-mcp-server.project-task-mcp.svc.cluster.local:8000/mcp`

**Next:** Write manifest files and apply to local cluster

---

## [2026-05-15] — New Skill: workflow_creator

**What was done**
- Created `.claude/skills/workflow_creator/` skill to codify the Python + UV + GHCR CI/CD pipeline process
- Captures every lesson learned from setting up task-mcp-server and task-agent pipelines
- Two files:
  - `SKILL.md` — 7-step workflow: read service → Dockerfile (delegates to `multi-stage-dockerfile`) → `.dockerignore` → workflow authoring → local build + smoke test → manual first push → one-time GHCR permissions
  - `references/workflow-template.yml` — ready-to-fill GitHub Actions template with correct `permissions` blocks, dual-tag strategy, and env dummy comment built in
- Bakes in all failure patterns as a common failures table: `KeyError` at pytest collection, `permission_denied: write_package`, path trigger not firing, `testpaths` misconfiguration
- Security checklist included: pin `uv` version, explicit `permissions` on both jobs, no real secrets in YAML, `.env` in `.dockerignore`, non-root user
- Originally named `python-ghcr-cicd`, renamed to `workflow_creator`

---

## [2026-05-15] — task-agent: Dockerfile, CI/CD Pipeline, and Security Review

**What was done**
- Authored multi-stage `Dockerfile` for `task-agent/` (identical pattern to task-mcp-server):
  - Builder stage: UV installs prod deps into `.venv`
  - Runtime stage: `python:3.13-slim`, non-root `agent` system user, only `.venv` + `src/`
  - No EXPOSE or HEALTHCHECK — agent is a one-shot script, not a server
  - CMD: `python src/task_mcp_sandbox.py` (requires `GEMINI_API_KEY`, `OPENAI_API_KEY`, `TASK_MCP_URL` at runtime)
- Added `.dockerignore` excluding `.venv`, `.env`, `__pycache__`, `dist`
- Fixed `pyproject.toml` bug: `testpaths` was `["tests"]` but all tests live in `src/`— corrected to `["src"]`
- Built and smoke-tested image locally (`all imports OK`)
- Pushed manually to `ghcr.io/mehroz17/task-management-agent/task-agent` with `:latest` and `:sha-<commit>` tags
- Granted repository write access to new GHCR package (same one-time manual step as task-mcp-server)
- Created `.github/workflows/task-agent.yml`:
  - Triggers: push to `task-agent/**` or `.github/workflows/task-agent.yml`, plus `workflow_dispatch`
  - `test` job: runs `test_gemini_model_is_used` (config-only, no live API calls) with dummy env keys so module imports without crashing
  - `publish` job: builds and pushes to GHCR with `:latest` and `:sha-<commit>` tags
  - Pipeline fully green end-to-end

**Bugs found and fixed during CI**
- `OPENAI_API_KEY` read at module import time → added `OPENAI_API_KEY: dummy` to test env
- `GEMINI_API_KEY` read inside `build_agent()` even for config-only test → added `GEMINI_API_KEY: dummy`
- Fix commit touched only `.github/workflows/` (outside `task-agent/**`) → added workflow file to path trigger and `workflow_dispatch`

**Security review findings**
- `uv:latest` in both Dockerfiles — unpinned builder image, supply chain risk (not yet fixed)
- `test` job in both workflows missing `permissions` block — inherits broad default token permissions (not yet fixed)
- No NetworkPolicy in K8s — intentional for course project

**Next:** Fix the two security lapses (pin `uv` version, add `permissions: contents: read` to test jobs)

---

## [2026-05-14] — Kubernetes Manifests: task-mcp-server

**What was done**
- Analyzed `task-mcp-server` characteristics for K8s deployment:
  - FastMCP Streamable HTTP on port 8000, `stateless_http=True`
  - In-memory store — single replica required (no shared state across pods)
  - Non-root `mcp` user already set in Dockerfile — clean security baseline
  - No external dependencies, no secrets needed
- Decided dev path: 1 replica, ephemeral in-memory state, no HPA, no PVC
- Created `deployments/task-mcp-deploy/` at repo root with 2 manifest files:
  - `namespace.yaml` — `task-mcp` namespace with `app.kubernetes.io` labels
  - `deployment.yaml` — 4 resources in one file (ConfigMap + ServiceAccount + Deployment + Service):
    - **ConfigMap** (`task-mcp-config`): externalises `MCP_HOST` and `MCP_PORT`
    - **ServiceAccount** (`task-mcp-sa`): dedicated SA, `automountServiceAccountToken: false`
    - **Deployment**: pinned image `ghcr.io/mehroz17/task-management-agent/task-mcp-server:sha-9e143707c001d6d789fe4d643652debd8ad4f239`, `tcpSocket` liveness + readiness probes (no HTTP health endpoint), resource limits (50m/64Mi req, 250m/256Mi lim), `readOnlyRootFilesystem: true` with `/tmp` emptyDir volume, `seccompProfile: RuntimeDefault`, drop ALL capabilities
    - **Service**: ClusterIP on port 8000
- Deliberate omissions: no RBAC Role/RoleBinding (server makes no K8s API calls), no NetworkPolicy (course project), no Ingress (ClusterIP sufficient), no HPA (in-memory store)
- Local access pattern: `kubectl port-forward svc/task-mcp 8000:8000 -n task-mcp`
- In-cluster access pattern for task-agent: `TASK_MCP_URL=http://task-mcp.task-mcp.svc.cluster.local:8000/mcp`

**Next:** Apply manifests to local cluster and verify rollout

---

## [2026-05-14] — task-agent: Step 2 Tests Passing + Tracing + Session Memory

**What was done**
- Added OpenAI tracing to `hello_sandbox.py`: `set_tracing_export_api_key(OPENAI_API_KEY)` — traces visible at platform.openai.com/traces even when using Gemini as inference model
- Added `SQLiteSession("hello_sandbox_session")` for multi-turn memory — agent recalls Turn 1 when asked in Turn 2
- Verified Step 1 script runs two turns successfully:
  - Turn 1: agent writes `outputs/hello.txt` with "Hello from Gemini inside a sandbox!"
  - Turn 2: agent recalls file name and content from session history
- Wrote `src/test_hello_sandbox.py` with 5 tests covering: model wiring, no errors, file confirmed, sandbox isolation, session memory
- Restructured tests to use `module-scoped` pytest fixtures (`turn1_result`, `session_results`) to share API calls — reduces 5 separate API calls to 3, staying under Gemini free tier limit (5 req/min)
- **All 5 tests passed** in 10.6s: `5 passed in 10.63s`

**Next:** Step 3 — connect SandboxAgent to `task-mcp-server` via `MCPServerStreamableHttp`

---

## [2026-05-13] — task-agent: Step 1 Hello World Sandbox Setup

**What was done**
- Created `task-agent/` package at repo root (separate from `task-mcp-server/`)
- Package structure: `pyproject.toml`, `.env.example`, `.gitignore`, `src/hello_sandbox.py`
- Dependencies: `openai-agents==0.17.2`, `python-dotenv` — installed via `uv sync`
- Discovered that SDK docs (llms.txt) had outdated class names; verified correct imports
  from the installed package directly:
  - `Filesystem` / `Shell` (not `FilesystemCapability` / `ShellCapability`)
  - `Dir` from `agents.sandbox.entries` (not `DirEntry`)
  - `UnixLocalSandboxClient` from `agents.sandbox.sandboxes.unix_local`
- Model chosen: `gemini-3-flash-preview` via Gemini OpenAI-compatible endpoint
  (`https://generativelanguage.googleapis.com/v1beta/openai/`)
- Secrets in `.env` (local dev) — `GEMINI_API_KEY`, `TASK_MCP_URL`
- SDK tracing disabled (`set_tracing_disabled(True)`) — tracing targets OpenAI by default

**Next:** Run `uv run python src/hello_sandbox.py`, verify agent writes `outputs/hello.txt`
inside the sandbox, then move to Step 2 (testing).

---

## [2026-05-13] — OpenAI Agents SDK Study: Simple Agents vs Sandboxed Agents

**What was done**
- Studied the OpenAI Agents SDK in full, including the April 2026 v0.14 release
- Created `spc/tasks-agents/open-sdk-study.md` — 16-section study note covering:
  - Core primitives: `Agent`, `Runner`, handoffs, `.as_tool()`, parallel execution
  - MCP integration via `MCPServerStreamableHttp`
  - Sessions (`SQLiteSession` → `RedisSession`), context injection, guardrails, structured output
  - v0.14 additions: Model-Native Harness, Native Sandbox Agents, Subagent pattern,
    `AGENTS.md`, Skills, `ShellTool`, `ApplyPatchTool`, 100+ non-OpenAI LLMs
  - Full mapping from `agent.md` concepts to SDK v0.14 primitives
- Clarified the distinction between Simple Agents and Sandboxed Agents:
  - Simple Agent (`Agent` + function tools / MCP) — for API orchestration, text workflows
  - Sandboxed Agent (`SandboxAgent`) — for real filesystem, shell, long-horizon compute work

**Note: OpenAI SDK Architecture Shift (April 15, 2026)**
OpenAI significantly updated its Agents SDK, transitioning from a simpler chatbot-focused
architecture to one that natively supports sandboxed agents. The new SDK ships a
model-native harness, first-class sandbox execution across 7 providers, the subagent
pattern as a runtime primitive, and standardized agent primitives (AGENTS.md, Skills,
ShellTool, ApplyPatchTool). This is a foundational shift — agents are no longer just
LLMs with function tools; they are now capable of owning a real compute environment.

**Decision**
The task management system uses **Simple Agents** with `MCPServerStreamableHttp` — no
sandbox needed because the `task-mcp-server` is the compute layer. Sandboxed agents are
deferred to future skills (e.g., code review, file report generation).

---

## [2026-05-12] — CI/CD Pipeline: Verified End-to-End

**What was done**
- Granted `Mehroz17/Task-Management-Agent` repository Write access to the GHCR package
  under package Settings → "Manage Actions access"
- Re-triggered pipeline with a version bump (0.1.1); both jobs passed:
  - `Run tests` ✓ — 36 tests in 10s
  - `Build and push image` ✓ — image pushed to GHCR in 21s
- CI/CD pipeline is now fully operational

**Why the manual permissions step was needed**
GHCR treats each container image as an independent package with its own access control.
When the image was first pushed manually via `docker push`, it was created under your
personal account credentials — not under the repository. GitHub Actions uses a temporary
token (`GITHUB_TOKEN`) scoped to the repository, and that token has no write access to
packages created outside of Actions until you explicitly grant it.

The one-time fix: go to the package settings and add the repository as a collaborator
with Write role. After that, every future push from Actions works automatically — you
never need to do this again for this package.

---

## [2026-05-12] — CI/CD Pipeline for task-mcp-server

**What was done**
- Added `.github/workflows/task-mcp-server.yml` — GitHub Actions workflow that automatically
  builds and publishes the Docker image whenever `task-mcp-server/` code changes
- Two jobs: `test` (runs pytest) → `publish` (builds and pushes image to GHCR)
- Triggered only on pushes to `main` that touch `task-mcp-server/**` — repo-level changes
  (agent.md, CHANGELOG.md, etc.) do not trigger it
- Image tagged with both `:latest` and `:sha-<commit>` on every successful run

**Verified**
- Workflow file pushed to GitHub, visible under repo Actions tab

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
