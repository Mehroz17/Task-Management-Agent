from task_mcp import store
from task_mcp.models import Task


def make_task(**kwargs) -> Task:
    defaults = dict(title="Sample task", project_name="default")
    defaults.update(kwargs)
    t = Task(**defaults)
    store.save_task(t)
    return t
