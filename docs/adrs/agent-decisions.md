# Architecture Decision Record — Agent Architecture

**Date:** 2026-05-13
**Status:** Accepted
**Deciders:** Mehroz (project lead)

---

## Context: What We Were Deciding

We needed to choose the agent architecture for the Task Management multi-agent system.
The question was: should we use **Simple Agents** (Agent + MCP tools over HTTP) or
**Sandboxed Agents** (SandboxAgent with an isolated filesystem and shell), and for which
parts of the system?

This decision came after studying the OpenAI Agents SDK v0.14 in depth, which introduced
native sandbox execution as a first-class primitive (released April 15, 2026).

---

## How the Discussion Unfolded

### Step 1 — First proposal: Simple Agents only

The initial design proposal was a single-orchestrator with simple skill agents (Triage,
Digest) all using `Agent` + `MCPServerStreamableHttp`. The reasoning was straightforward:
every operation in a task management system is an HTTP call — create task, update status,
get project view. No filesystem needed.

The proposed structure was:
```
Orchestrator → Triage Agent (handoff)
             → Digest Agent (handoff)
```

### Step 2 — Realizing the llms.txt docs were outdated

When studying from `https://openai.github.io/openai-agents-python/llms.txt`, we suspected
the documentation was not current. The user pointed this out: *"i think that .txt file is
outdated you can use openai agents sandbox"*.

We ran a web search for `OpenAI Agents SDK sandboxed agents 2026` and discovered that
OpenAI had shipped a **major update** on April 15, 2026 (v0.14) — the largest overhaul
since the SDK launched. The `.txt` file had none of this.

### Step 3 — What v0.14 actually introduced

The research revealed five new primitives in v0.14:

1. **Native Sandbox Agents** (`SandboxAgent`) — isolated container environments with
   real filesystems, shell access, and resumable state across sessions
2. **Model-Native Harness** — control plane separated from compute plane; manages context
   scoping, memory isolation, and failure propagation for subagents
3. **Subagent Pattern** — a runtime primitive for spawning child agents; harness handles
   all lifecycle (previously you wired this manually)
4. **Standardized Primitives** — `AGENTS.md` (like `CLAUDE.md`), `ShellTool`,
   `ApplyPatchTool`, Skills for progressive tool disclosure
5. **100+ non-OpenAI LLMs** — model routing per agent via Chat Completions API

The key insight: *agents are no longer just LLMs with function tools — they can now own
a real compute environment.*

### Step 4 — Understanding Simple vs Sandboxed (the decision point)

We worked through a clear comparison:

**Simple Agent** (`Agent`):
- Calls Python functions or MCP tools
- Gets back text/JSON
- No filesystem, no shell
- Everything lives in conversation context
- Right for: API orchestration, text workflows, CRUD operations

**Sandboxed Agent** (`SandboxAgent`):
- Gets a real isolated computer (container/VM)
- Real filesystem, shell, installed packages
- Persistent workspace across turns (resumable)
- Separates control plane (harness, trusted) from compute plane (sandbox, untrusted)
- Right for: file manipulation, code execution, artifact generation, long-horizon work

The decision framework we derived:
```
Does the task need to touch a real filesystem,
run shell commands, or produce file artifacts?
         │
        NO → Simple Agent
         │
        YES
         │
Is it a one-off you can wrap as a @function_tool?
         │
        YES → Simple Agent
         │
        NO → Sandboxed Agent
```

### Step 5 — First conclusion: Simple Agents for our system

Applying the framework to our task management workflows:
- Create task → MCP call → Simple Agent ✓
- Update status → MCP call → Simple Agent ✓
- Get project summary → MCP call → Simple Agent ✓
- Triage free text → structured output → Simple Agent ✓
- Send Slack notification → MCP call → Simple Agent ✓

**Initial decision: Simple Agents. Sandbox deferred.**

### Step 6 — Pivoting to Sandbox for learning

The user then changed direction: *"sandbox architecture looks interesting as we are
building for learning purposes, so lets research more on this and write the draft of
spec for it."*

This reframed the decision. The goal is not just to ship the simplest working system —
it is also to learn the full SDK surface. Sandboxed agents cover the parts of v0.14 that
are genuinely new and interesting.

We researched further:
- Full sandbox documentation at `developers.openai.com/api/docs/guides/agents/sandboxes`
- Quickstart at `openai.github.io/openai-agents-python/sandbox_agents/`
- OpenAI Cookbook: *Migrate a Legacy Codebase with Sandbox Agents*
- OpenAI Cookbook: *Building Reliable Agents with Memory and Compaction*

### Step 7 — Identifying which skills genuinely need a sandbox

We asked: which of our skill agents have a real reason to be sandboxed — not just because
it's interesting, but because the workflow actually needs a workspace?

Three skills passed the test:

| Skill | Why Sandbox Is Genuinely Right |
|---|---|
| **Digest Agent** | Produces `digest.md` + `digest.html` artifacts; uses `MemoryCapability` to remember preferred format across runs |
| **Report Agent** | Generates CSV/Markdown project reports as downloadable files; future Google Drive mount |
| **Code Review Agent** | Clones a GitHub repo linked to a task, runs `pytest`, writes `findings.md` — needs real shell + filesystem |

The remaining five skills stay as Simple Agents because they only make MCP HTTP calls:
Orchestrator, Triage, Dependency Check, Bulk Update, Escalation.

### Step 8 — Infrastructure requirements for sandboxes

We worked through what sandbox agents add to the system. Key findings:

- **No new K8s Deployment** — E2B/Modal manage their own containers in production
- **New storage layer** — `RunState` stays in Redis (existing); workspace snapshots go to
  S3-compatible blob storage (new addition)
- **Provider is a runtime choice** — same agent definition, different `sandbox_client`
  per environment (UnixLocal → Docker → E2B)
- **Credentials never enter the sandbox** — host harness holds all secrets; sandbox only
  gets a scoped workspace
- **Network policy** — sandbox pods allowed to reach `task-mcp-server`; all other
  outbound denied by default

---

## The Decision

### Architecture: Hybrid — Simple Agents + Sandbox Agents

| Agent | Type | Reason |
|---|---|---|
| Orchestrator | `Agent` (Simple) | Routing only — pure MCP calls |
| Triage | `Agent` (Simple) | Structured text extraction via `output_type` |
| Dependency Check | `Agent` (Simple) | MCP `task_get` + `task_transition` only |
| Bulk Update | `Agent` (Simple) | MCP `task_update` batch calls |
| Escalation | `Agent` (Simple) | MCP + Slack MCP notification calls |
| **Digest** | `SandboxAgent` | File artifacts + MemoryCapability for format prefs |
| **Report** | `SandboxAgent` | CSV/MD generation + future Drive mount |
| **Code Review** | `SandboxAgent` | git clone + pytest + findings.md |

### Sandbox client strategy

| Environment | Client | Reason |
|---|---|---|
| Local dev | `UnixLocalSandboxClient` | Zero setup, fastest iteration |
| CI / staging | `DockerSandboxClient` | Consistent, isolated builds |
| Production | `E2BSandboxClient` | Managed, scalable, no infra overhead |

Provider is injected at runtime — agent definitions never change across environments.

### State storage split

| State Type | Store | Key pattern |
|---|---|---|
| Conversation history | `SQLiteSession` → `RedisSession` | `{session_id}` |
| Harness `RunState` | Redis | `{session_id}:run_state` |
| Workspace snapshot | S3 bucket | `{session_id}/workspace` |

---

## What We Rejected and Why

| Option | Why Rejected |
|---|---|
| All Simple Agents | Correct for production-fastest, but misses the learning goal of v0.14 sandbox primitives |
| All Sandbox Agents | Over-engineering — orchestrator and pure-API skills gain nothing from a sandbox |
| Skip the ADR | Discussion happened across a long session; capturing reasoning prevents future confusion |

---

## Consequences

**Positive:**
- We learn the full v0.14 SDK surface: `SandboxAgent`, `Manifest`, `Capabilities`,
  `MemoryCapability`, `CompactionCapability`, `RunState` resumption, sandbox clients
- The system becomes genuinely more powerful — reports and code reviews are real
  file artifacts, not just text in a chat response
- Provider swappability means zero code changes going from local dev to production

**Negative / Tradeoffs:**
- More moving parts — S3 bucket needed for workspace snapshots
- Sandbox skills are slower and more expensive than simple MCP calls
- `E2B_API_KEY` or equivalent needed in production secrets

**Deferred:**
- Google Drive mount for Report Agent (needs Drive MCP server first)
- Actual Code Review Agent (needs GitHub MCP server + tasks with linked repos)
- Full `MemoryCapability` tuning (format preferences learned over real usage)

---

## Reference

- Full sandbox spec: `spc/tasks-agents/sandbox-agent-spec.md`
- SDK study notes: `spc/tasks-agents/open-sdk-study.md`
- Agent constitution: `agent.md`
- SDK docs: https://openai.github.io/openai-agents-python/sandbox_agents/
- Sandbox API: https://developers.openai.com/api/docs/guides/agents/sandboxes
