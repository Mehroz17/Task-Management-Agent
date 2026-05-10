import json
from helpers import make_task
from task_mcp.tools.task_get import task_get


async def test_get_existing_task():
    t = make_task(title="Fix auth", assignee="maya")
    result = json.loads(await task_get(task_id=t.id))
    assert result["id"] == t.id
    assert result["title"] == "Fix auth"
    assert result["assignee"] == "maya"
    assert result["comments"] == []


async def test_get_unknown_task():
    result = json.loads(await task_get(task_id="ghost"))
    assert "error" in result
