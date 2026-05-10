import json
from task_mcp import store


async def task_delete(task_id: str) -> str:
    if not store.delete_task(task_id):
        return json.dumps({"error": f"Task '{task_id}' not found"})
    return json.dumps({"deleted": True, "task_id": task_id})
