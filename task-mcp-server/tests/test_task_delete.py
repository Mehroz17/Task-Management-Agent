import json
from helpers import make_task
from task_mcp import store
from task_mcp.tools.task_delete import task_delete


async def test_delete_existing():
    t = make_task()
    result = json.loads(await task_delete(task_id=t.id))
    assert result["deleted"] is True
    assert store.get_task(t.id) is None


async def test_delete_unknown():
    result = json.loads(await task_delete(task_id="ghost"))
    assert "error" in result
