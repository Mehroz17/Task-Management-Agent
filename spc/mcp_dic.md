# MCP Server — Transport Decision

## Transport — Streamable HTTP

### What the two options are

**stdio** — the client launches the MCP server as a child process on the same machine.
Messages travel through the process's standard input and output streams. The server lives
and dies with that one process. One client, one machine, one session.

**Streamable HTTP** — the server runs as an independent network service. Clients reach it
over HTTP. Any number of clients can connect simultaneously. The server is just a process
listening on a port; it has no idea how many agents are talking to it.

### Why stdio is the wrong choice here

Our server will run as a Kubernetes Deployment and will be called by multiple agent pods
(orchestrator, skill agents) potentially at the same time. stdio cannot do this. A stdio
server cannot be shared — it is owned by exactly one client process. There is no version
of stdio that works for a deployed, multi-client scenario.

### How Streamable HTTP actually works

The MCP spec defines one single HTTP endpoint (e.g. `http://tasks-mcp-service/mcp`) that
handles both POST and GET. That is the entire surface area of the server from the network
perspective.

**Client → Server (tool calls):**
Every JSON-RPC message the client sends is a new HTTP POST to that endpoint. The client
includes two required headers:

```
Accept: application/json, text/event-stream
MCP-Protocol-Version: 2025-06-18
```

The server reads the JSON-RPC request from the POST body and responds in one of two ways:

- **Plain JSON response** (`Content-Type: application/json`) — the simple case. The
  server returns one JSON object and closes the response. This is what we will use for
  every tool call in this system. Simple, stateless, easy to reason about.

- **SSE stream response** (`Content-Type: text/event-stream`) — the server opens a
  streaming connection and sends multiple messages back before closing it. Useful for
  long-running operations that push progress updates. We do not need this for our tools.

**Server → Client (server-initiated messages):**
The client can also send an HTTP GET to the same endpoint to open an SSE stream and
receive server-initiated messages. We do not use this either — our tools are all
request-response.

**What a single tool call looks like:**

```
Agent pod                              tasks-mcp-service (K8s)
   │                                          │
   │  POST /mcp                               │
   │  Accept: application/json, text/event-stream
   │  MCP-Protocol-Version: 2025-06-18        │
   │  Body: { "jsonrpc": "2.0",               │
   │          "method": "tools/call",         │
   │          "params": { "name": "task_create", ... } }
   │ ─────────────────────────────────────────>
   │                                          │
   │                                          │  executes tool
   │                                          │
   │  200 OK                                  │
   │  Content-Type: application/json          │
   │  Body: { "jsonrpc": "2.0",               │
   │          "result": { ... } }             │
   │ <─────────────────────────────────────────
```

Each call is a fresh HTTP request. No persistent connection. No session state on the server.

**Session management — opting out:**
The spec allows servers to issue a session ID at initialization and require clients to
echo it on every subsequent request via `Mcp-Session-Id`. We are not using this. Every
request is treated independently.

**Initialization handshake:**
The OpenAI Agents SDK and FastMCP handle this automatically on both sides. When an agent
first connects, the SDK sends an `InitializeRequest`, receives an `InitializeResult`, then
sends `InitializedNotification`. Tool calls follow. We write none of this.

### Why this fits Kubernetes perfectly

The server becomes a standard K8s Deployment behind a ClusterIP Service. Agent pods call
`http://tasks-mcp-service/mcp` and K8s routes each POST to any healthy replica. No
session state on the server means any replica can handle any request. Scaling is just
increasing the replica count.
