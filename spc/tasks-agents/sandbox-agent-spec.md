# Sandbox Agent Architecture — Specification Draft

This spec redesigns the Task Management Agent to incorporate Sandboxed Agents alongside
Simple Agents. The primary motivation is **learning** — understanding when and how to use
the full v0.14 SDK capabilities in a real multi-agent system.

---

## 1. Why Sandbox Agents for a Task Management System?

The honest answer: our core workflows (create task, update status, get project view) do
not need a sandbox. Simple Agents + MCP cover them completely.

But three skill types genuinely benefit from a sandbox, and they make the system more
powerful and more interesting to build:

| Skill | Why Sandbox Fits |
|---|---|
| **Report Agent** | Generates Markdown/CSV project reports as real files, mounts them to Google Drive |
| **Code Review Agent** | Clones the GitHub repo linked to a task, runs tests, reads coverage, writes findings |
| **Digest Agent (enhanced)** | Produces a `digest.md` artifact + optionally a rendered HTML preview |

These three skills need a persistent workspace, file writing, or shell commands — the
exact cases where `SandboxAgent` is the right tool.

---

## 2. Revised Multi-Agent Layout

```
                        ┌─────────────────────────────────┐
                        │       Orchestrator Agent         │
                        │       (Simple Agent)             │
                        │  gpt-4o | MCP: task-mcp-server   │
                        │  Handoffs → all specialists      │
                        └──────────────┬──────────────────┘
                                       │
           ┌───────────────────────────┼──────────────────────────┐
           │                           │                          │
           ▼                           ▼                          ▼
  ┌─────────────────┐       ┌──────────────────┐      ┌──────────────────┐
  │  Triage Agent   │       │  Dependency Check │      │  Bulk Update     │
  │  (Simple Agent) │       │  (Simple Agent)   │      │  (Simple Agent)  │
  │  output_type=   │       │  MCP tools only   │      │  MCP tools only  │
  │  ExtractedTask  │       └──────────────────┘      └──────────────────┘
  └─────────────────┘

           ┌───────────────────────────┼──────────────────────────┐
           │                           │                          │
           ▼                           ▼                          ▼
  ┌─────────────────┐       ┌──────────────────┐      ┌──────────────────┐
  │  Digest Agent   │       │  Report Agent    │      │  Code Review     │
  │ (SandboxAgent)  │       │ (SandboxAgent)   │      │  Agent           │
  │  digest.md +    │       │  CSV / Markdown  │      │ (SandboxAgent)   │
  │  HTML artifact  │       │  → Drive mount   │      │  clone → test →  │
  └─────────────────┘       └──────────────────┘      │  findings.md     │
                                                       └──────────────────┘
```

**Rule:** The Orchestrator and all pure-API skills stay Simple Agents. Only skills that
produce file artifacts or need shell commands become Sandbox Agents.

---

## 3. Simple Agents (unchanged)

| Agent | Model | Tools |
|---|---|---|
| Orchestrator | `gpt-4o` | MCP task tools + handoffs to all specialists |
| Triage | `gpt-4o-mini` | No tools — structured output only (`ExtractedTask`) |
| Dependency Check | `gpt-4o-mini` | MCP: `task_get`, `task_transition` |
| Bulk Update | `gpt-4o-mini` | MCP: `task_update` (batch) |
| Escalation | `gpt-4o` | MCP: `task_get`, `project_view` + MCP Slack |

These agents call tools over HTTP and return text. No filesystem needed.

---

## 4. Sandbox Agents — Detailed Design

> **Gemini constraint (discovered Step 1, 2026-05-14):**
> `Filesystem()` capability injects `SandboxApplyPatchTool` (`CustomTool`) which is
> rejected by the Chat Completions API converter used for all non-OpenAI models.
> All sandbox agents in this project use `Shell()` only — files are written via shell
> commands (`echo`, redirects) instead of `apply_patch`. This works identically for
> our use case. If switching to an OpenAI model, `Filesystem()` can be re-added.

### 4.1 Digest Agent (SandboxAgent)

**What it does:** Summarizes project health — open tasks, blocked items, overdue,
upcoming deadlines — and writes a formatted `digest.md` and `digest.html` to the
workspace. The Slack MCP tool posts a link to the file.

**Manifest:**
```python
from agents.sandbox import Manifest
from agents.sandbox.entries import Dir  # NOT DirEntry

digest_manifest = Manifest(
    entries={
        "outputs": Dir(),   # where digest files are written
        "data":    Dir(),   # raw task JSON fetched via MCP tools
    },
    environment={"TZ": "UTC"},
)
```

**Capabilities:**
```python
from agents.sandbox.capabilities import Shell, Memory, Compaction
# NOT: FilesystemCapability, ShellCapability, MemoryCapability, CompactionCapability

digest_capabilities = [
    Shell(),       # write files via shell (echo/redirect), run pandoc
    Memory(),      # remember preferred digest format across runs
    Compaction(),  # handle long project histories without context overflow
    # Filesystem() excluded — incompatible with Gemini (Chat Completions API)
]
```

**Agent definition:**
```python
from agents import SandboxAgent

digest_agent = SandboxAgent(
    name="Digest Agent",
    model="gpt-4o",
    handoff_description="Generates a formatted project health digest with file artifacts.",
    instructions="""
    You produce a structured project digest.

    Steps:
    1. Call project_view MCP tool to get project health data.
    2. Call task_get for any blocked or overdue tasks to get full detail.
    3. Write outputs/digest.md — sections: Summary, Overdue, Blocked, Upcoming.
    4. Run: pandoc outputs/digest.md -o outputs/digest.html (if pandoc available).
    5. Report the file path and key highlights in your final response.

    Follow the format in your memory if one has been saved from a prior run.
    """,
    default_manifest=digest_manifest,
    capabilities=digest_capabilities,
    mcp_servers=[task_mcp],   # needs project_view and task_get
)
```

**Memory pattern:**
The `MemoryCapability` stores lessons like *"user prefers tables over bullet lists"* or
*"always include a 'Blocked Reasons' section"* — not task data. The digest content goes
in `outputs/digest.md`; the format preferences go in memory.

---

### 4.2 Report Agent (SandboxAgent)

**What it does:** Generates exportable project reports — CSV of all tasks, Markdown
summary, or filtered views. Optionally mounts Google Drive to write files directly.

**Manifest:**
```python
from agents.sandbox import Manifest
from agents.sandbox.entries import Dir

report_manifest = Manifest(
    entries={
        "outputs": Dir(),   # generated CSV, MD, JSON reports
    },
    environment={"REPORT_FORMAT": "csv"},
)
```

**Capabilities:**
```python
from agents.sandbox.capabilities import Shell, Compaction

report_capabilities = [
    Shell(),       # write files via shell, run transformations
    Compaction(),  # handle large task lists
    # Filesystem() excluded — incompatible with Gemini
]
```

**Agent definition:**
```python
report_agent = SandboxAgent(
    name="Report Agent",
    model="gpt-4o-mini",
    handoff_description="Generates exportable task reports as CSV or Markdown files.",
    instructions="""
    You generate project reports as downloadable files.

    Steps:
    1. Call project_view to get the project summary.
    2. Call task_get on relevant tasks to get full fields.
    3. Write outputs/report.csv — columns: id, title, status, priority, assignee, due_date.
    4. Write outputs/report.md — human-readable summary table.
    5. Report the file paths in your response.

    Never include task IDs or raw UUIDs in the human-readable report.
    """,
    default_manifest=report_manifest,
    capabilities=report_capabilities,
    mcp_servers=[task_mcp],
)
```

**Google Drive mount (future):**
When the Drive MCP server is connected, the agent writes files to the mounted path and
the Drive MCP tool handles the upload. The sandbox itself doesn't need Drive credentials
— the MCP server handles auth on the host side.

---

### 4.3 Code Review Agent (SandboxAgent)

**What it does:** When a task is linked to a GitHub PR or branch, clones the repo,
installs dependencies, runs tests, reads coverage, and writes `findings.md` back to the
workspace. Updates the task with the findings via MCP.

**Manifest:**
```python
from agents.sandbox import Manifest, DirEntry, GitEntry

def make_code_review_manifest(repo_url: str, branch: str) -> Manifest:
    return Manifest(
        entries={
            "repo/":     GitEntry(repo=repo_url, ref=branch),  # cloned at run time
            "outputs/":  DirEntry(),                            # findings.md written here
        },
        environment={
            "PYTHONDONTWRITEBYTECODE": "1",
            "CI": "true",
        },
    )
```

**Capabilities:**
```python
from agents.sandbox.capabilities import Shell, Memory, Compaction

code_review_capabilities = [
    Shell(),       # run pytest, pip install, git diff, write findings.md via shell
    Memory(),      # remember project-specific test commands across runs
    Compaction(),  # large repos produce a lot of output
    # Filesystem() excluded — incompatible with Gemini
]
```

**Agent definition:**
```python
code_review_agent = SandboxAgent(
    name="Code Review Agent",
    model="gpt-4o",
    handoff_description="Reviews code linked to a task — runs tests, checks coverage, writes findings.",
    instructions="""
    You review code in the repo/ directory and produce a findings report.

    Steps:
    1. Read repo/README.md to understand the project.
    2. Run: cd repo && pip install -e ".[dev]" -q (or equivalent).
    3. Run: cd repo && pytest --tb=short --cov 2>&1 | tee outputs/test_output.txt
    4. Read outputs/test_output.txt and identify failures, warnings, coverage gaps.
    5. Write outputs/findings.md — sections: Test Results, Coverage, Issues Found, Recommendation.
    6. Call task_update MCP tool to add a comment with the findings summary.

    Be concise. findings.md should be readable in under 2 minutes.
    If tests fail to install or run, document the error and stop — do not guess at fixes.
    """,
    default_manifest=None,     # manifest built per run (repo URL varies)
    capabilities=code_review_capabilities,
    mcp_servers=[task_mcp, github_mcp],
)
```

**How the manifest is injected per run:**
```python
from agents import RunConfig
from agents.sandbox import SandboxRunConfig

task = await get_task(task_id)
repo_url = task.github_repo_url
branch = task.github_branch

# SandboxRunConfig is a field inside RunConfig — not a top-level run_config
result = await Runner.run(
    code_review_agent,
    f"Review the code for task {task_id}",
    run_config=RunConfig(
        sandbox=SandboxRunConfig(
            client=sandbox_client,
            manifest=make_code_review_manifest(repo_url, branch),
        )
    ),
)
```

---

## 5. Sandbox Client Strategy

The provider is **never** part of the agent definition — it is injected at run time.
This means the same agent runs locally during development and in production without
any code changes.

```python
import os

def get_sandbox_client():
    env = os.getenv("ENVIRONMENT", "local")

    if env == "local":
        from agents.sandbox.sandboxes.unix_local import UnixLocalSandboxClient
        return UnixLocalSandboxClient()

    elif env == "development":
        from agents.sandbox.sandboxes.docker import DockerSandboxClient
        return DockerSandboxClient(image="python:3.13-slim")

    elif env in ("staging", "production"):
        from agents.sandbox.sandboxes.e2b import E2BSandboxClient
        return E2BSandboxClient(api_key=os.environ["E2B_API_KEY"])
```

| Environment | Client | Why |
|---|---|---|
| Local dev | `UnixLocalSandboxClient` | No Docker needed, fastest iteration |
| CI / staging | `DockerSandboxClient` | Consistent, isolated, reproducible |
| Production | `E2BSandboxClient` | Managed, scalable, no infra to maintain |

---

## 6. State Management

Sandbox agents produce two kinds of state that must be persisted between turns:

```
┌──────────────────────────────────────────────────────┐
│                  State After a Run                   │
│                                                      │
│  RunState          → Redis (existing session store)  │
│  (harness state:     Key: session_id + ":run_state"  │
│   model history,                                     │
│   agent position)                                    │
│                                                      │
│  SandboxSession    → Object Storage (new)            │
│  (workspace:         Bucket: task-agent-sandboxes/   │
│   files, packages,   Key: session_id + "/workspace"  │
│   installed state)                                   │
└──────────────────────────────────────────────────────┘
```

**Resume pattern (long-horizon work):**
```python
# After a run that pauses for human review
run_state     = result.to_state()
sandbox_state = result.sandbox_session.serialize()

# Store both
await redis.set(f"{session_id}:run_state",     run_state.serialize())
await s3.put_object(Key=f"{session_id}/workspace", Body=sandbox_state)

# Resume later — exact same workspace, exact same conversation position
stored_run   = RunState.deserialize(await redis.get(f"{session_id}:run_state"))
stored_ws    = await s3.get_object(Key=f"{session_id}/workspace")

result = await Runner.run(
    agent,
    "Continue the review",
    run_state=stored_run,
    run_config=SandboxRunConfig(
        client=get_sandbox_client(),
        session_state=stored_ws,
    ),
)
```

---

## 7. Memory vs. Compaction — When to Use Each

These are two separate mechanisms, both available as capabilities:

| | `MemoryCapability` | `CompactionCapability` |
|---|---|---|
| **Purpose** | Carry lessons to **future runs** | Handle long context in the **current run** |
| **Scope** | Across sessions | Within a session |
| **What to store** | Workflow preferences, format choices | Nothing — it's automatic |
| **What NOT to store** | Task data, compliance findings, facts | N/A |
| **Stored where** | `memories/` directory in workspace | Inline — collapses prior turns |

**Memory prompt we use for Digest Agent:**
```python
MemoryCapability(
    generate_config=MemoryGenerateConfig(
        prompt="""
        Store only reusable workflow lessons.

        Good to store: preferred report sections, formatting choices, 
        which MCP tools to call first, user timezone preferences.

        Do NOT store: task titles, assignees, dates, project names,
        any data that belongs in outputs/digest.md.
        """
    )
)
```

---

## 8. Security Model

The core principle: **the sandbox is untrusted compute; the host harness is trusted**.

```
┌────────────────────────────────────────────────────────┐
│  HOST HARNESS (trusted)                                │
│  - Orchestrator agent                                  │
│  - MCP server connections (task-mcp-server, Slack)     │
│  - API keys and credentials                            │
│  - Audit logging                                       │
│  - Approval gates                                      │
└─────────────────────┬──────────────────────────────────┘
                      │  scoped workspace only
                      ▼
┌────────────────────────────────────────────────────────┐
│  SANDBOX (untrusted compute)                           │
│  - File system access (workspace only)                 │
│  - Shell commands                                      │
│  - No credentials (never injected into sandbox)        │
│  - No direct external network unless explicitly needed │
│  - Output reviewed before leaving sandbox              │
└────────────────────────────────────────────────────────┘
```

**Rules:**
1. API keys and secrets are **never** passed into the sandbox manifest or environment
2. The sandbox can call MCP tools (the host harness makes those calls on behalf of the
   sandbox agent — the sandbox never holds the credentials)
3. Artifacts written by the sandbox are reviewed before posting to Slack or Drive
4. Each sandbox run is ephemeral unless explicitly resumed — no leftover state

---

## 9. Infrastructure Additions (on top of existing K8s layout)

Existing services: `agent-api`, `agent-runner`, `mcp-gateway`, `session-store`, `trace-exporter`

New additions for sandbox agents:

| New Component | Type | Purpose |
|---|---|---|
| Sandbox session store | S3-compatible bucket | Persist serialized workspace snapshots |
| Sandbox provider secret | Kubernetes Secret | `E2B_API_KEY` / `MODAL_API_KEY` mounted as env var |
| `ENVIRONMENT` config | ConfigMap | Controls which sandbox client is used per environment |
| Resource quota | LimitRange | CPU/memory caps per sandbox pod |
| Network policy | NetworkPolicy | Sandbox pods → `task-mcp-server` allowed; all else denied by default |

**No new Kubernetes Deployment needed** — sandbox execution happens inside the provider
(E2B/Modal manages the containers). The `agent-runner` pod stays the same.

---

## 10. Project Structure

```
task-agent/
├── pyproject.toml
└── src/task_agent/
    ├── __main__.py              # CLI entry point
    ├── config.py                # env vars: MCP URL, model, sandbox client
    ├── agent.py                 # orchestrator (Simple Agent)
    ├── mcp.py                   # MCPServerStreamableHttp setup
    ├── session.py               # SQLiteSession (dev) / RedisSession (prod)
    ├── context.py               # UserContext dataclass + dynamic instructions
    ├── guardrails.py            # @input_guardrail scope enforcement
    ├── runner.py                # streamed CLI loop
    │
    ├── skills/                  # Simple Agent skills
    │   ├── triage.py            # Triage — output_type=ExtractedTask
    │   ├── dependency_check.py  # Dependency Check
    │   ├── bulk_update.py       # Bulk Update
    │   └── escalation.py       # Escalation
    │
    └── sandbox_skills/          # Sandbox Agent skills
        ├── sandbox_client.py    # get_sandbox_client() — env-aware factory
        ├── digest.py            # Digest Agent — SandboxAgent + digest.md
        ├── report.py            # Report Agent — SandboxAgent + CSV/MD
        └── code_review.py       # Code Review Agent — SandboxAgent + pytest
```

---

## 11. Decision Log

| Decision | Choice | Reason |
|---|---|---|
| Orchestrator type | Simple Agent | Routing only — no filesystem needed |
| Triage / Dep Check / Bulk / Escalation | Simple Agent | Pure MCP tool calls |
| Digest | SandboxAgent | Produces file artifacts; memory for format preferences |
| Report | SandboxAgent | Writes CSV/MD; future Drive mount |
| Code Review | SandboxAgent | Needs git clone, pip install, pytest |
| Dev sandbox client | `UnixLocalSandboxClient` | Zero setup, fastest iteration |
| Prod sandbox client | `E2BSandboxClient` | Managed infra, no K8s sandbox pods to maintain |
| Workspace state storage | S3 bucket | Blob storage is the right fit for serialized workspaces |
| Memory contents | Format/workflow lessons only | Task data belongs in outputs, not memory |
| Credentials in sandbox | Never | Host harness holds all secrets |

---

## 12. What We Learn from This Architecture

Building this system teaches the full v0.14 SDK surface:

| SDK Primitive | Where We Use It |
|---|---|
| `Agent` + `Runner` | Orchestrator + Simple skills |
| `SandboxAgent` | Digest, Report, Code Review |
| `Manifest` + `GitEntry` | Code Review (per-run manifest) |
| `Shell()` (not `Filesystem()` — Gemini incompatible) | All sandbox skills |
| `Memory()` + `MemoryGenerateConfig` | Digest Agent |
| `Compaction()` | Digest + Code Review (long runs) |
| `RunConfig(sandbox=SandboxRunConfig(...))` + `UnixLocalSandboxClient` | Dev runner |
| `E2BSandboxClient` | Prod runner |
| `RunState` serialization + resume | Long-horizon Code Review |
| `MCPServerStreamableHttp` | All agents (task-mcp-server) |
| `SQLiteSession` → `RedisSession` | Conversation memory |
| `RunContextWrapper[UserContext]` | User identity injection |
| `@input_guardrail(blocking=True)` | Scope enforcement |
| `handoff()` + `input_type` | Orchestrator → skill routing |
| `output_type=ExtractedTask` | Triage structured extraction |
