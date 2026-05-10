from typing import Optional
from task_mcp import store
from task_mcp.models import Task, Priority


async def task_create(
    title: str,
    project_name: str,
    description: Optional[str] = None,
    assignee: Optional[str] = None,
    priority: Priority = Priority.medium,
    due_date: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> str:
    task = Task(
        title=title,
        project_name=project_name,
        description=description,
        assignee=assignee,
        priority=priority,
        due_date=due_date,
        tags=tags or [],
    )
    store.save_task(task)
    return task.model_dump_json()
