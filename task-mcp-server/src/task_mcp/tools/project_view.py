import json
from datetime import datetime, timezone
from task_mcp import store
from task_mcp.models import TaskStatus


async def project_view(project_name: str) -> str:
    tasks = store.tasks_for_project(project_name)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    by_status = {s.value: 0 for s in TaskStatus}
    by_assignee: dict[str, int] = {}
    overdue = []
    blocked = []

    for t in tasks:
        by_status[t.status.value] += 1

        if t.assignee:
            by_assignee[t.assignee] = by_assignee.get(t.assignee, 0) + 1

        if t.due_date and t.due_date < today and t.status != TaskStatus.done:
            overdue.append({"id": t.id, "title": t.title, "due_date": t.due_date})

        if t.status == TaskStatus.blocked:
            last_note = t.comments[-1].body if t.comments else "No note"
            blocked.append({"id": t.id, "title": t.title, "note": last_note})

    return json.dumps({
        "project": project_name,
        "total": len(tasks),
        "by_status": by_status,
        "overdue_count": len(overdue),
        "overdue": overdue,
        "blocked": blocked,
        "by_assignee": by_assignee,
    })
