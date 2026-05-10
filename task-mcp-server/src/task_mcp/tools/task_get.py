import json
from task_mcp import store


async def task_get(task_id: str) -> str:
    task = store.get_task(task_id)
    if task is None:
        return json.dumps({"error": f"Task '{task_id}' not found"})
    return task.model_dump_json()
