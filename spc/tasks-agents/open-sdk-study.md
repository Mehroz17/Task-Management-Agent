# OpenAI Agents SDK — Study Notes

Study of the SDK before building the Task Management multi-agent system.

Sources:
- https://openai.github.io/openai-agents-python/
- https://openai.com/index/the-next-evolution-of-the-agents-sdk/ (April 15, 2026 — v0.14 release)
- https://developers.openai.com/api/docs/guides/agents/sandboxes
- https://explore.n1n.ai/blog/openai-agents-sdk-0-14-sandbox-harness-2026-05-11

> **Note:** The `llms.txt` file is outdated. The April 2026 (v0.14) release added
> three major new primitives: **Native Sandbox Agents**, **Subagents**, and the
> **Model-Native Harness**. These sections are marked `[NEW v0.14]`.

---

## 1. Core Primitive: `Agent`

An `Agent` is an LLM configured with instructions, tools, and optional runtime behavior.

```python
from agents import Agent

agent = Agent(
    name="My Agent",
    instructions="You are a helpful assistant.",  # static string or dynamic function
    model="gpt-4o",
    tools=[...],             # @function_tool decorated Python functions
    mcp_servers=[...],       # MCP server connections — tools auto-discovered
    handoffs=[...],          # other agents this agent can route to
    input_guardrails=[...],  # validate input before acting
    output_guardrails=[...], # validate output before returning
    output_type=None,        # Pydantic model for structured JSON output
    handoff_description="",  # shown to orchestrator when deciding to hand off
)
```

**What it gives us:** The single building block for every agent in our system —
orchestrator, triage, digest, etc. are all `Agent` instances with different
instructions and tools.

---

## 2. Running Agents — `Runner`

Three execution modes:

```python
from agents import Runner

# Async — standard for web/service contexts
result = await Runner.run(agent, "Create a task for the login bug")

# Sync — for scripts and CLI tools
result = Runner.run_sync(agent, "Create a task for the login bug")

# Streamed — real-time tokens for interactive CLI or web UI
async with Runner.run_streamed(agent, "Create a task") as result:
    async for event in result.stream_events():
        if event.type == "raw_response_event":
            # token-by-token output
            pass
        elif event.type == "run_item_stream_event":
            # semantic events: tool called, tool output, handoff, etc.
            pass
        elif event.type == "agent_updated_stream_event":
            # a handoff happened, new agent is now active
            pass
```

The **agent loop** the Runner runs:
1. Call LLM with current agent + input
2. If tool call → execute tool, append result, loop
3. If handoff → switch to new agent, loop
4. If final output → return `RunResult`
5. If `max_turns` exceeded → raise `MaxTurnsExceeded`

**What it gives us:** `Runner.run_streamed()` powers our interactive CLI. The loop
handles all tool calls and handoffs automatically — we don't manage it ourselves.

---

## 3. Multi-Agent Patterns

The SDK offers three distinct patterns. Understanding when to use each is critical.

### Pattern A — Handoffs (triage / routing)

The current agent transfers full conversation control to a specialist. The specialist
becomes the active agent and owns the rest of the conversation.

```python
from agents import Agent, handoff
from pydantic import BaseModel

class TriageInput(BaseModel):
    reason: str  # metadata the LLM provides when deciding to hand off

triage_agent = Agent(name="Triage Agent", instructions="Extract structured task details...")
digest_agent  = Agent(name="Digest Agent",  instructions="Summarize project health...")

orchestrator = Agent(
    name="Orchestrator",
    instructions="Route each request to the right specialist.",
    handoffs=[
        handoff(
            triage_agent,
            input_type=TriageInput,         # LLM fills this when handing off
            on_handoff=lambda ctx, d: ...,  # callback fired at handoff time
        ),
        digest_agent,  # plain Agent — uses handoff_description for routing hint
    ]
)
```

- `handoff()` exposes the target as a tool called `transfer_to_<agent_name>`
- `input_type` lets the LLM pass metadata (reason, priority, language) at handoff time
- `on_handoff` callback fires when the handoff is invoked (logging, side effects)
- `input_filter` controls what conversation history the receiving agent sees
- `RECOMMENDED_PROMPT_PREFIX` from `agents.extensions.handoff_prompt` adds standard
  handoff instructions to specialist prompts

**Use when:** The specialist takes full ownership — user continues talking to them.

---

### Pattern B — Agents as Tools (manager pattern)

The orchestrator stays in control. It calls specialists like tools and synthesizes
their outputs. No transfer of conversation control.

```python
orchestrator = Agent(
    name="Manager",
    instructions="You coordinate specialists and synthesize their outputs.",
    tools=[
        triage_agent.as_tool(
            tool_name="triage_request",
            tool_description="Extract structure from a free-text task description",
        ),
        digest_agent.as_tool(
            tool_name="generate_digest",
            tool_description="Get project health summary for a given project",
        ),
    ]
)
```

Additional `.as_tool()` options:
- `parameters`: Pydantic model for structured input to the sub-agent
- `needs_approval=True`: Pause for human confirmation before running sub-agent
- `custom_output_extractor`: Transform sub-agent output before returning to manager
- `on_stream`: Callback to listen to sub-agent streaming events

**Use when:** You need one agent to synthesize multiple specialists' outputs, or the
orchestrator must stay in control throughout (e.g., confirmation gates, audit trail).

---

### Pattern C — Parallel Execution (code-based)

Run independent agents concurrently with `asyncio.gather`. No SDK coordination needed.

```python
import asyncio

results = await asyncio.gather(
    Runner.run(triage_agent, input_a),
    Runner.run(digest_agent, input_b),
)
```

**Use when:** Tasks are fully independent and their results don't depend on each other.

---

## 4. MCP Integration

The SDK supports five transports. We use **Streamable HTTP** since our `task-mcp-server`
already runs on that transport.

```python
from agents.mcp import MCPServerStreamableHttp

task_mcp = MCPServerStreamableHttp(
    url="http://localhost:8000/mcp",
    cache_tools_list=True,  # cache the tool list — reduces latency on repeated calls
)

agent = Agent(
    name="Task Agent",
    mcp_servers=[task_mcp],
    # All 6 tools auto-discovered: task_create, task_get, task_transition,
    # task_update, task_delete, project_view
)
```

Other transports available (not needed now):
- `MCPServerStdio` — launches a subprocess, communicates via stdin/stdout
- `MCPServerSse` — legacy SSE transport (deprecated)
- `HostedMCPTool` — OpenAI's servers call a public MCP server on your behalf
- `MCPServerManager` — manages multiple MCP servers simultaneously

MCP config options on `Agent`:
- `mcp_config.convert_schemas_to_strict=True` — strict JSON schema for tool calls
- `mcp_config.include_server_in_tool_names=True` — prefix tools with server name
  (useful when multiple MCP servers have overlapping tool names)

**What it gives us:** Connect once to `task-mcp-server` and all 6 workflow tools are
available to any agent that includes it in `mcp_servers`.

---

## 5. Sessions (Memory Across Turns)

Sessions maintain conversation history automatically across multiple `Runner.run()` calls.

```python
from agents import SQLiteSession  # built-in for development

session = SQLiteSession("user_123")

# Turn 1
result = await Runner.run(agent, "Create a task for Sara", session=session)

# Turn 2 — full conversation history automatically injected
result = await Runner.run(agent, "Now mark it urgent", session=session)
```

Available implementations:

| Session | Best For |
|---|---|
| `SQLiteSession` | Local dev — zero dependencies |
| `AsyncSQLiteSession` | Async SQLite with `aiosqlite` |
| `RedisSession` | Production — distributed, low latency |
| `SQLAlchemySession` | Any SQL database |
| `MongoDBSession` | Multi-process horizontal scaling |
| `DaprSession` | Cloud-native, 30+ backends |
| `OpenAIConversationsSession` | OpenAI manages storage server-side |

Custom implementation: implement `SessionABC` with `get_items()`, `add_items()`,
`pop_item()`, `clear_session()`.

**What it gives us:** Start with `SQLiteSession` for the interactive CLI. Swap to
`RedisSession` when we deploy to Kubernetes — zero code change in the agent.

---

## 6. Context Injection (`RunContextWrapper`)

Inject application state (user identity, preferences) into every tool call and
instruction callback without sending it to the LLM.

```python
from dataclasses import dataclass
from agents import RunContextWrapper

@dataclass
class UserContext:
    user_id: str
    default_project: str
    timezone: str

async def dynamic_instructions(ctx: RunContextWrapper[UserContext], agent) -> str:
    u = ctx.context
    return f"You manage tasks for {u.user_id}. Default project: {u.default_project}. Timezone: {u.timezone}."

agent = Agent(name="Task Agent", instructions=dynamic_instructions)

result = await Runner.run(
    agent,
    "What tasks are due this week?",
    context=UserContext(user_id="sara", default_project="backend", timezone="UTC"),
)
```

`RunContextWrapper` also exposes:
- `ctx.usage` — aggregated token counts for the run
- `ctx.tool_input` — structured input when the agent is used via `.as_tool()`
- `ctx.approve_tool()` / `ctx.reject_tool()` — programmatic approval control

**What it gives us:** User profile (default project, timezone, preferences) injected at
run time. The LLM sees it in the system prompt via dynamic instructions; our code sees
it in `ctx.context` inside every tool function.

---

## 7. Guardrails

Validate user input before the agent acts and agent output before it's returned.

```python
from agents import input_guardrail, GuardrailFunctionOutput, RunContextWrapper, Agent

@input_guardrail(blocking=True)  # blocking = runs before agent, saves tokens on rejection
async def scope_guard(
    ctx: RunContextWrapper, agent: Agent, input: str
) -> GuardrailFunctionOutput:
    out_of_scope = any(phrase in input.lower() for phrase in ["delete all", "drop project"])
    return GuardrailFunctionOutput(
        output_info="scope check result",
        tripwire_triggered=out_of_scope,
    )

agent = Agent(name="Task Agent", input_guardrails=[scope_guard])
```

When `tripwire_triggered=True`, the SDK raises `InputGuardrailTripwireTriggered` —
catch it and return a refusal to the user.

Two modes:
- **Parallel** (default): guardrail runs alongside the agent — lower latency but agent
  may consume tokens before cancellation
- **Blocking** (`blocking=True`): guardrail runs first — no tokens consumed on rejection

Scope rules:
- Input guardrails run only for the **first agent** in a handoff chain
- Output guardrails run only for the agent that produces the **final output**
- Tool guardrails (`@function_tool` wrapping) run on every tool invocation

**What it gives us:** The "hard refusals" from `agent.md` — blocking requests to delete
entire projects, access unauthorized data, or act outside the session.

---

## 8. Structured Output

Force the LLM to return a valid Pydantic model instead of free text.

```python
from pydantic import BaseModel
from agents import Agent

class ExtractedTask(BaseModel):
    title: str
    priority: str       # "low" | "medium" | "high" | "urgent"
    assignee: str | None
    project: str

triage_agent = Agent(
    name="Triage Agent",
    instructions="Extract task structure from the user's free-text description.",
    output_type=ExtractedTask,  # LLM must return valid JSON matching this schema
)

result = await Runner.run(triage_agent, "Login button broken on mobile, urgent, assign Sara")
task: ExtractedTask = result.final_output  # fully typed
```

**What it gives us:** Triage agent extracts structured fields from messy user input
reliably. No prompt engineering needed to parse JSON — the SDK enforces it.

---

## 9. Key Behaviors and Defaults

| Behavior | Default | How to Override |
|---|---|---|
| Max turns per run | 10 | `Runner.run(..., max_turns=20)` |
| Tool choice | `"auto"` | `model_settings=ModelSettings(tool_choice="required")` |
| Tool result loops to LLM | Yes | `tool_use_behavior="stop_on_first_tool"` |
| Guardrail execution | Parallel | `@input_guardrail(blocking=True)` |
| Handoff history | Flat (full) | `RunConfig(nest_handoff_history=True)` — collapses prior turns |
| Tool reset after call | Yes | `reset_tool_choice=False` |

---

## 10. How the SDK Maps to Our Agent Constitution (`agent.md`)

| `agent.md` concept | SDK primitive | Notes |
|---|---|---|
| Orchestrator agent | `Agent` with `handoffs=[...]` | Routes to skill agents |
| Skill agents (Triage, Digest…) | `Agent` with `output_type` | Handoff targets with focused instructions |
| 6 MCP task tools | `MCPServerStreamableHttp("http://localhost:8000/mcp")` | Auto-discovered on connect |
| Session memory — per conversation | `SQLiteSession` (dev) → `RedisSession` (prod) | Session ID = user or conversation key |
| User profile — across sessions | `RunContextWrapper[UserContext]` + dynamic instructions | Injected at run time, not stored in session |
| Confirmation gates for destructive ops | `needs_approval=True` on `.as_tool()` or pending-state pattern | Pauses run; user approves/rejects |
| Hard refusals (delete all, out of scope) | `@input_guardrail(blocking=True)` | Raises `InputGuardrailTripwireTriggered` |
| Streaming interactive CLI | `Runner.run_streamed()` + `stream_events()` | `ResponseTextDeltaEvent` for tokens |
| Orchestrator → skill handoff | `handoff(agent, input_type=..., on_handoff=...)` | `input_type` passes routing metadata |
| Agent introspection / tracing | SDK built-in tracing → OpenAI Traces | Extend with Datadog trace processor |
| `agent-runner` stateless pods | `Runner` is stateless by design | State lives in session (Redis), not runner |

---

## 11. What We Will Use (and What We Won't, Yet)

### Will use from day one
- `Agent`, `Runner.run_streamed()`, `handoff()` — core multi-agent loop
- `MCPServerStreamableHttp` — connect to `task-mcp-server`
- `SQLiteSession` — conversation memory for the CLI
- `RunContextWrapper[UserContext]` — inject user identity and default project
- `@input_guardrail(blocking=True)` — scope enforcement
- `output_type` on Triage agent — structured task extraction

### Will add later (Kubernetes / production milestone)
- `RedisSession` — swap in when deploying to K8s
- Datadog trace processor — observability in production
- `AgentHooks` / `RunHooks` — lifecycle callbacks for audit logging
- `asyncio.gather` parallel pattern — for running Digest + Escalation concurrently
- `needs_approval=True` — human-in-the-loop confirmation gates

---

## 17. [VERIFIED] Step 1 — Real Import Paths vs. Docs (2026-05-14)

Docs and `llms.txt` describe class names that differ from the actual installed package
(`openai-agents==0.17.2`). Always verify against the installed package, not the docs.

### Correct import paths

```python
# Sandbox capabilities — NOT FilesystemCapability / ShellCapability
from agents.sandbox.capabilities import Filesystem, Shell, Memory, Compaction

# Sandbox entries — NOT DirEntry
from agents.sandbox.entries import Dir

# Sandbox client — lives in a submodule, not agents.sandbox directly
from agents.sandbox.sandboxes.unix_local import UnixLocalSandboxClient
from agents.sandbox.sandboxes.docker import DockerSandboxClient

# SandboxRunConfig and Manifest — these ARE in agents.sandbox directly
from agents.sandbox import Manifest, SandboxAgent, SandboxRunConfig

# RunConfig — SandboxRunConfig is a FIELD inside RunConfig, not a replacement
from agents import RunConfig
```

### Critical: `SandboxRunConfig` is nested inside `RunConfig`

Wrong (causes `AttributeError: 'SandboxRunConfig' object has no attribute 'session_input_callback'`):
```python
# WRONG
result = await Runner.run(agent, input, run_config=SandboxRunConfig(client=...))
```

Correct:
```python
# CORRECT — SandboxRunConfig is the sandbox field of RunConfig
result = await Runner.run(
    agent, input,
    run_config=RunConfig(sandbox=SandboxRunConfig(client=UnixLocalSandboxClient())),
)
```

### Critical: `Filesystem()` capability is incompatible with non-OpenAI models

`Filesystem()` injects `SandboxApplyPatchTool` which extends `CustomTool`. The Chat
Completions API converter (used for all non-OpenAI models including Gemini) only
handles `FunctionTool` subclasses and hard-rejects everything else:

```
UserError: Hosted tools are not supported with the ChatCompletions API.
Got tool type: <class '...SandboxApplyPatchTool'>
```

`Shell()` only injects `ExecCommandTool` and `WriteStdinTool`, both `FunctionTool`
subclasses — fully compatible with Gemini via Chat Completions.

**Workaround for Gemini + SandboxAgent:** Use `Shell()` only. The agent writes files
via shell commands (`echo "content" > outputs/file.txt`) instead of `apply_patch`.

```python
# Works with Gemini (Shell only — all FunctionTool)
agent = SandboxAgent(
    capabilities=[Shell()],   # NOT Filesystem()
)

# Does NOT work with Gemini (Filesystem injects CustomTool)
agent = SandboxAgent(
    capabilities=[Filesystem(), Shell()],  # breaks on Gemini
)
```

### Verified working: Hello World with Gemini + SandboxAgent

```python
from agents import OpenAIChatCompletionsModel, RunConfig, Runner, set_tracing_disabled
from agents.sandbox import Manifest, SandboxAgent, SandboxRunConfig
from agents.sandbox.capabilities import Shell
from agents.sandbox.entries import Dir
from agents.sandbox.sandboxes.unix_local import UnixLocalSandboxClient
from openai import AsyncOpenAI

set_tracing_disabled(True)  # tracing targets OpenAI — disable for non-OpenAI models

model = OpenAIChatCompletionsModel(
    model="gemini-3-flash-preview",
    openai_client=AsyncOpenAI(
        api_key=os.environ["GEMINI_API_KEY"],
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    ),
)

agent = SandboxAgent(
    name="Hello Sandbox",
    model=model,
    instructions="Write 'Hello from Gemini inside a sandbox!' to outputs/hello.txt, then cat it.",
    default_manifest=Manifest(entries={"outputs": Dir()}),
    capabilities=[Shell()],   # Shell only — compatible with Chat Completions
)

result = await Runner.run(
    agent,
    "Say hello and write it to a file.",
    run_config=RunConfig(sandbox=SandboxRunConfig(client=UnixLocalSandboxClient())),
)
```

**Output:** Agent ran shell commands to write and verify `outputs/hello.txt` inside the
isolated sandbox. File confirmed written. Step 1 passed.

---

## 12. [NEW v0.14] Model-Native Harness (April 2026)

Released April 15, 2026 in SDK v0.14. The harness is the control plane that manages the
agent loop, model calls, memory, and orchestration — physically separated from the
compute plane (the sandbox where code actually runs).

**What changed from v0.13:**
- v0.13: You managed container lifecycle externally and wired it to the agent yourself
- v0.14: The harness is a first-class SDK primitive — it handles context scoping,
  memory isolation between agents, credential management, and failure propagation

**Key capabilities:**
- Configurable memory per agent run
- Checkpoint-based persistence for long-horizon tasks (resume across sessions)
- Sandbox-aware orchestration — harness knows whether work runs locally or in a container
- Codex-style filesystem tools built in (`ShellTool`, `ApplyPatchTool`)

**What it gives us:** For the task agent, we don't need sandbox execution (our tools live
in the MCP server, not in a local shell). But the harness checkpoint model is useful for
long-running Digest or Escalation workflows that span multiple turns.

---

## 13. [NEW v0.14] Native Sandbox Agents (April 2026)

Sandbox agents run in isolated, Unix-like execution environments. The model can work with
filesystems, run commands, install packages, mount data, expose ports, and resume state
across sessions — all without touching the host machine.

### When to use sandboxes

Use when the agent needs to:
- Process files from a directory (not from prompt context)
- Generate files or artifacts for later inspection
- Run shell commands, install packages, or execute scripts
- Expose a service on a port (e.g., a preview web server)
- Resume stateful work across multiple sessions

**Skip sandboxes** for simple model responses and tool calls without a persistent workspace
(this is our current case — MCP tools are the compute layer, not a sandbox).

### Core components

**Manifest** — defines the workspace for each fresh session:
- File entries and directories
- Git repository mounts
- Cloud storage mounts
- Environment variables and OS accounts

**Capabilities** — attach sandbox-native behavior to the agent:
- `Shell` — execute commands
- `Filesystem` — read/write files and inspect images
- `Skills` — discover and materialize skill bundles
- `Memory` — cross-run learning from prior workspace sessions
- `Compaction` — trim context for long-running workflows

**Sandbox Client** — selects the execution environment:
- `UnixLocalSandboxClient` — Docker-free local dev
- `DockerSandboxClient` — local Docker container
- Hosted providers: **Blaxel, Cloudflare, Daytona, E2B, Modal, Runloop, Vercel**

### Session management

The runner resolves sandbox sessions in priority order:
1. Live injected session (reused directly)
2. Resume from stored `RunState` session state
3. Resume from explicit serialized state
4. Create fresh session from manifest

### Security model

The control plane (harness) and compute plane (sandbox) are physically separated.
This blocks lateral movement from prompt injection — even if the model generates
malicious commands, they can't escape the sandbox to the host.

**What it gives us:** Not needed for our first milestone (MCP handles our compute).
Relevant later if we add a "Code Review" skill that needs to clone a repo and run tests.

---

## 14. [NEW v0.14] Subagent Pattern (April 2026)

Subagents are a runtime primitive in v0.14 — parent agents spawn child agents, and the
harness manages context scoping, memory isolation, and failure propagation automatically.

### How it differs from handoffs and `.as_tool()`

| Pattern | Who stays in control | History passed | v0.14 harness managed |
|---|---|---|---|
| `handoff()` | Specialist takes over | Full conversation | No |
| `.as_tool()` | Orchestrator stays | Only tool I/O | No |
| **Subagent** | Orchestrator stays | Isolated scope per subagent | **Yes** |

### What the harness handles for subagents

- **Context scoping**: Each subagent gets its own isolated context — no bleed between
  parallel subagents
- **Memory isolation**: Subagent memory is separate from parent memory unless explicitly
  shared
- **Failure propagation**: If a subagent fails, the harness surfaces the failure to the
  parent cleanly (no raw exceptions)
- **Parallel routing**: Parent can spawn multiple subagents in parallel, routed to
  isolated sandbox environments

### Subagent vs. skills (our terminology)

In `agent.md` we called these "skill agents". In v0.14 terms they are **subagents**:
- Triage → subagent spawned by orchestrator to extract task structure
- Daily Digest → subagent spawned to summarize project health
- Dependency Check → subagent spawned before task completion
- Bulk Update → subagent spawned with isolated write scope
- Escalation → subagent spawned to find and surface overdue tasks

The orchestrator spawns the right subagent based on user intent. The harness handles
everything else.

**What it gives us:** This is the right primitive for our multi-agent design. Replace
manual handoff wiring with the subagent pattern where the harness manages isolation —
cleaner, safer, and handles failures automatically.

---

## 15. [NEW v0.14] New Standardized Primitives (April 2026)

The v0.14 release standardized several primitives that were previously conventions or
optional add-ons:

### `AGENTS.md`

A markdown file (similar to `CLAUDE.md` for Claude Code) that provides custom
instructions to the agent at runtime. The SDK loads it from the working directory
automatically.

- Grew out of community convention
- OpenAI adopting it signals cross-industry convergence on agent instruction files
- Our `agent.md` is the equivalent — we may expose it as `AGENTS.md` for the SDK

### Skills (progressive tool disclosure)

Skills are bundles of tools that agents can discover and load on demand, rather than
having every tool available from the start. The SDK now has first-class `Skills` support
as a sandbox capability.

- Reduces context bloat from large tool lists
- Agents load the skill bundle they need for the current task
- Pairs with `ToolSearchTool` for deferred loading

### `ShellTool` and `ApplyPatchTool`

- `ShellTool` — execute shell commands (local or hosted sandbox)
- `ApplyPatchTool` — edit files via unified diffs (Codex-style, efficient for large files)

### 100+ non-OpenAI LLMs

The SDK now supports over 100 models via the Chat Completions API compatibility layer.
You can route different agents to different models:
- Orchestrator → `gpt-4o` (high reasoning)
- Triage → `gpt-4o-mini` (fast, cheap extraction)
- Digest → `gpt-4o` (quality summaries)

**What it gives us:** `AGENTS.md` as the runtime config for our agent instructions.
Model routing per agent to balance cost vs. quality.

---

## 16. Updated Mapping: `agent.md` → SDK v0.14 Primitives

| `agent.md` concept | SDK v0.14 primitive | Notes |
|---|---|---|
| Orchestrator agent | `Agent` with subagent routing | Harness manages subagent lifecycle |
| Skill agents (Triage, Digest…) | Subagents | Harness scopes context + isolates memory |
| 6 MCP task tools | `MCPServerStreamableHttp("http://localhost:8000/mcp")` | First-class MCP, auto-discovered |
| Agent constitution (`agent.md`) | `AGENTS.md` | SDK loads automatically from working dir |
| Session memory — per conversation | `SQLiteSession` (dev) → `RedisSession` (prod) | Unchanged |
| User profile | `RunContextWrapper[UserContext]` + dynamic instructions | Unchanged |
| Confirmation gates | `needs_approval=True` | Pauses run; user approves/rejects |
| Hard refusals | `@input_guardrail(blocking=True)` | Unchanged |
| Streaming CLI | `Runner.run_streamed()` | Unchanged |
| Long-horizon tasks | Harness checkpoints + `Compaction` capability | New in v0.14 |
| Skill routing | Subagent pattern (harness-managed) | Replaces manual handoff wiring |
| Cost optimization | Model routing per agent | `gpt-4o` for orchestrator, `gpt-4o-mini` for extraction |
| Future: sandbox workloads | `E2B` / `Modal` sandbox provider | Code review, test-running skills |
