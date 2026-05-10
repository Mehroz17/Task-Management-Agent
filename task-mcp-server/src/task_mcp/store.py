from task_mcp.models import Task

_tasks: dict[str, Task] = {}


def save_task(task: Task) -> None:
    _tasks[task.id] = task


def get_task(task_id: str) -> Task | None:
    return _tasks.get(task_id)


def all_tasks() -> list[Task]:
    return list(_tasks.values())


def tasks_for_project(project_name: str) -> list[Task]:
    return [t for t in _tasks.values() if t.project_name == project_name]


def delete_task(task_id: str) -> bool:
    if task_id not in _tasks:
        return False
    del _tasks[task_id]
    return True


def reset() -> None:
    _tasks.clear()
