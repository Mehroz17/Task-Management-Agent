from __future__ import annotations

import logging
import os

from fastapi import FastAPI, HTTPException

from notification_api import store
from notification_api.mcp_client import get_overdue_tasks
from notification_api.models import Notification, NotificationStatus

logger = logging.getLogger(__name__)

MCP_URL = os.environ.get("TASK_MCP_URL", "http://localhost:8000/mcp")
WATCHED_PROJECTS: list[str] = [
    p.strip()
    for p in os.environ.get("WATCHED_PROJECTS", "").split(",")
    if p.strip()
]
THRESHOLD_HOURS = int(os.environ.get("DEFAULT_THRESHOLD_HOURS", "24"))

app = FastAPI(title="Notification API", version="0.1.0")


async def _run_check() -> dict:
    new_count = 0
    skipped = 0
    for project in WATCHED_PROJECTS:
        tasks = await get_overdue_tasks(MCP_URL, project)
        for task in tasks:
            task_id = task.get("id", "")
            if store.already_notified(task_id, THRESHOLD_HOURS):
                skipped += 1
                continue
            due_date = task.get("due_date", "")
            title = task.get("title", "unknown")
            n = Notification(
                task_id=task_id,
                task_title=title,
                project=project,
                due_date=due_date,
                message=f"Task '{title}' is overdue (was due on {due_date})",
            )
            store.add(n)
            new_count += 1
    return {
        "checked_projects": WATCHED_PROJECTS,
        "new_notifications": new_count,
        "skipped_duplicates": skipped,
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "mcp_url": MCP_URL,
        "watched_projects": WATCHED_PROJECTS,
        "threshold_hours": THRESHOLD_HOURS,
    }


@app.post("/notify/trigger")
async def trigger():
    return await _run_check()


@app.get("/notifications", response_model=list[Notification])
async def list_notifications(
    status: NotificationStatus | None = None,
    project: str | None = None,
):
    return store.list_all(status=status, project=project)


@app.post("/notifications/{notification_id}/read", response_model=Notification)
async def mark_read(notification_id: str):
    n = store.mark_read(notification_id)
    if n is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    return n


@app.delete("/notifications")
async def clear_inbox():
    count = store.clear()
    return {"cleared": count}
