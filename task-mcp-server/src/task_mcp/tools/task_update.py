import json
from datetime import datetime, timezone
from typing import Optional
from task_mcp import store
from task_mcp.models import Comment, Priority


async def task_update(
    task_id: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    assignee: Optional[str] = None,
    priority: Optional[Priority] = None,
    due_date: Optional[str] = None,
    tags: Optional[list[str]] = None,
    comment: Optional[str] = None,
) -> str:
    task = store.get_task(task_id)
    if task is None:
        return json.dumps({"error": f"Task '{task_id}' not found"})

    if title is not None:
        task.title = title
    if description is not None:
        task.description = description
    if assignee is not None:
        task.assignee = assignee
    if priority is not None:
        task.priority = Priority(priority)
    if due_date is not None:
        task.due_date = due_date
    if tags is not None:
        task.tags = tags
    if comment:
        task.comments.append(Comment(author="user", body=comment))

    task.updated_at = datetime.now(timezone.utc).isoformat()
    store.save_task(task)
    return task.model_dump_json()
