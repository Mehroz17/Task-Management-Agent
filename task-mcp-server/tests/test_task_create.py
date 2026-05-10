import json
from task_mcp.tools.task_create import task_create
from task_mcp.models import TaskStatus, Priority


async def test_create_required_fields_only():
    result = json.loads(await task_create(title="Setup CI", project_name="infra"))
    assert result["title"] == "Setup CI"
    assert result["project_name"] == "infra"
    assert result["status"] == TaskStatus.todo
    assert result["priority"] == Priority.medium
    assert result["id"] is not None


async def test_create_all_fields():
    result = json.loads(await task_create(
        title="Deploy",
        project_name="infra",
        description="Deploy to prod",
        assignee="john",
        priority="urgent",
        due_date="2026-06-01",
        tags=["devops"],
    ))
    assert result["assignee"] == "john"
    assert result["priority"] == "urgent"
    assert result["tags"] == ["devops"]


async def test_create_persists_to_store():
    from task_mcp import store
    result = json.loads(await task_create(title="Persisted", project_name="p"))
    assert store.get_task(result["id"]) is not None
