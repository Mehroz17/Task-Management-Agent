# Deployment Specification: notification-api

## Overview

The notification-api deploys as two Kubernetes resources:

1. **Deployment** — the long-running FastAPI service (rules store, inbox endpoints, `/notify/trigger`)
2. **CronJob** — fires every minute, calls `POST /notify/trigger` on the Deployment to run a deadline check

The polling logic stays inside the FastAPI app. The CronJob's only job is to wake it up on schedule.

```
K8s CronJob (every 1 min)
    │
    └── POST http://notification-api.project-task-mcp.svc.cluster.local:8090/notify/trigger
              │
              ▼
        notification-api Deployment
              │
              └── MCP ──► task-mcp-server:8000/mcp
                            (calls: project_view, task_get)
```

---

## Why CronJob, Not asyncio Background Loop

An asyncio background loop inside FastAPI would also work, but a Kubernetes CronJob is
the better fit here:

| | asyncio loop | K8s CronJob |
|---|---|---|
| Visibility | hidden inside pod logs | separate pod per run, own logs |
| Control | restart pod to change interval | edit CronJob schedule, no redeploy |
| Failure isolation | loop crash can hang the API | CronJob failure doesn't affect the API |
| Kubernetes-native | no | yes |

---

## Resources

### 1. Deployment

- **Name:** `notification-api`
- **Namespace:** `project-task-mcp`
- **Replicas:** 1
- **Port:** 8090 (FastAPI runs on 8090 to avoid colliding with task-mcp-server on 8000)
- **Image:** `ghcr.io/mehroz17/task-management-agent/notification-api:latest`
- **imagePullPolicy:** `Always`
- **Probes:**
  - Liveness: `GET /health`, initialDelay 15s, period 20s
  - Readiness: `GET /health`, initialDelay 5s, period 10s
- **Resources:**
  - requests: `100m CPU / 128Mi`
  - limits: `500m CPU / 256Mi`
- **Security context:** `runAsNonRoot: true`, `runAsUser: 999`, `readOnlyRootFilesystem: true`,
  `allowPrivilegeEscalation: false`, `capabilities: drop: [ALL]`
- **Env vars:**

| Variable | Source |
|---|---|
| `TASK_MCP_URL` | plain env: `http://task-mcp-server.project-task-mcp.svc.cluster.local:8000/mcp` |
| `POLL_INTERVAL_SECONDS` | plain env: `60` (informational — actual trigger is the CronJob) |
| `DEFAULT_THRESHOLD_HOURS` | plain env: `24` |
| `MAX_NOTIFICATIONS` | plain env: `200` |

No secrets needed — notification-api makes no external API calls.

---

### 2. Service

- **Name:** `notification-api`
- **Namespace:** `project-task-mcp`
- **Type:** `ClusterIP`
- **Port:** 8090 → targetPort 8090
- **Why ClusterIP:** notification-api only needs to be reachable by the CronJob (in-cluster)
  and optionally by future services. No external access required.

In-cluster DNS: `http://notification-api.project-task-mcp.svc.cluster.local:8090`

For local development / testing:
```bash
kubectl port-forward svc/notification-api 8090:8090 -n project-task-mcp
```

---

### 3. CronJob

- **Name:** `notification-checker`
- **Namespace:** `project-task-mcp`
- **Schedule:** `*/1 * * * *` (every minute)
- **concurrencyPolicy:** `Forbid` — if a previous job is still running, skip this run
  (prevents overlapping checks if task-mcp-server is slow)
- **successfulJobsHistoryLimit:** `3`
- **failedJobsHistoryLimit:** `3`
- **restartPolicy:** `Never`
- **What it runs:** a minimal container (`curlimages/curl:latest`) that calls:
  ```
  curl -s -X POST http://notification-api.project-task-mcp.svc.cluster.local:8090/notify/trigger
  ```
- **Resources:** requests `50m CPU / 32Mi`, limits `100m CPU / 64Mi`

Using `curlimages/curl` keeps the CronJob image tiny — no Python, no app code. All logic
stays in the Deployment.

---

## Connections Summary

| From | To | Protocol | Port |
|---|---|---|---|
| `notification-checker` CronJob | `notification-api` Deployment | HTTP | 8090 |
| `notification-api` Deployment | `task-mcp-server` Deployment | MCP (HTTP) | 8000 |

`notification-api` has **no connection** to `task-agent`.

---

## Apply Order

```bash
kubectl apply -f deployments/notification-api/deployment.yaml
kubectl apply -f deployments/notification-api/service.yaml
kubectl apply -f deployments/notification-api/cronjob.yaml
```

---

## Deliberate Omissions (this phase)

| Resource | Reason deferred |
|---|---|
| RBAC | notification-api makes no Kubernetes API calls |
| NetworkPolicy | deferred to hardening phase |
| Ingress | ClusterIP is sufficient; no public access needed |
| PersistentVolumeClaim | state is in-memory; rules and inbox lost on restart |
| Secrets | no external API keys required |
