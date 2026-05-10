import json
from helpers import make_task
from task_mcp.tools.task_update import task_update


async def test_update_single_field():
    t = make_task(title="Old title")
    result = json.loads(await task_update(task_id=t.id, title="New title"))
    assert result["title"] == "New title"
    assert result["project_name"] == t.project_name


async def test_update_multiple_fields():
    t = make_task()
    result = json.loads(await task_update(task_id=t.id, assignee="sara", priority="high"))
    assert result["assignee"] == "sara"
    assert result["priority"] == "high"


async def test_update_comment_only():
    t = make_task()
    result = json.loads(await task_update(task_id=t.id, comment="Just a note"))
    assert len(result["comments"]) == 1
    assert result["comments"][0]["body"] == "Just a note"
    assert result["title"] == t.title


async def test_update_fields_and_comment():
    t = make_task()
    result = json.loads(await task_update(task_id=t.id, assignee="john", comment="Assigned to John"))
    assert result["assignee"] == "john"
    assert len(result["comments"]) == 1


async def test_update_unknown_task():
    result = json.loads(await task_update(task_id="ghost", title="x"))
    assert "error" in result
