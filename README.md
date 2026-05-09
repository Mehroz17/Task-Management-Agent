# Task Management Agent

An AI-powered task management system built on the OpenAI Agents SDK, deployed on Kubernetes.

## Overview

This project implements an intelligent task management assistant using a multi-agent architecture. An orchestrator agent handles user requests and delegates to specialized skill agents for complex workflows. External integrations (Slack, GitHub, Google Calendar, Google Drive) are connected via MCP servers.

## Architecture

The system follows a two-layer design:

**Commodity Layer** — the building blocks:
- **LLM** — OpenAI `gpt-4o` via the OpenAI Agents SDK
- **Tools** — task CRUD, project summaries, notifications
- **MCP** — Slack, GitHub, Google Calendar, Google Drive
- **Skills** — Triage, Daily Digest, Dependency Check, Bulk Update, Escalation
- **agent.md** — the agent constitution (this repo)

**Engineering Layer** — what makes it shippable:
- **Harness** — SDK `Runner` with loop, dispatch, and recovery
- **Context engineering** — session-based history, orchestrator → skill handoffs
- **Memory and state** — Redis-backed session, user profile, and project state
- **Evals** — scenario-based evaluation of routing, triage, safety, and recovery
- **Observability** — OpenAI Traces + Datadog via SDK trace processors
- **Permissions and safety** — input guardrails (blocking mode) + confirmation gates

## Kubernetes Deployment

| Service | Role |
|---|---|
| `agent-api` | HTTP entrypoint |
| `agent-runner` | Orchestrator + skill agents (horizontally scalable) |
| `mcp-gateway` | MCP server proxy |
| `session-store` | Redis (StatefulSet) |
| `trace-exporter` | Forwards traces to Datadog |

Secrets are stored in Kubernetes Secrets. Agent instructions are hot-reloadable via ConfigMaps. Environments (dev, staging, prod) are managed through Helm values files.

## Docs

See [`agent.md`](./agent.md) for the full agent constitution — tools, skills, MCP servers, memory design, observability setup, safety rules, and the complete Kubernetes deployment spec.
