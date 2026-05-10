import json
from datetime import datetime, timezone
from task_mcp import store
from task_mcp.models import Comment, TaskStatus


async def task_transition(task_id: str, status: str, note: str) -> str:
    if not note.strip():
        return json.dumps({"error": "note is required and cannot be blank"})

    try:
        new_status = TaskStatus(status)
    except ValueError:
        valid = [s.value for s in TaskStatus]
        return json.dumps({"error": f"Invalid status '{status}'. Valid values: {valid}"})

    task = store.get_task(task_id)
    if task is None:
        return json.dumps({"error": f"Task '{task_id}' not found"})

    task.status = new_status
    task.updated_at = datetime.now(timezone.utc).isoformat()
    task.comments.append(Comment(author="system", body=f"[{new_status.value}] {note}"))
    store.save_task(task)
    return task.model_dump_json()
