import json
from helpers import make_task
from task_mcp.tools.task_transition import task_transition


async def test_valid_transition():
    t = make_task()
    result = json.loads(await task_transition(task_id=t.id, status="in_progress", note="Starting now"))
    assert result["status"] == "in_progress"
    assert len(result["comments"]) == 1
    assert "Starting now" in result["comments"][0]["body"]


async def test_transition_blocked_requires_note():
    t = make_task()
    result = json.loads(await task_transition(task_id=t.id, status="blocked", note="Waiting on design"))
    assert result["status"] == "blocked"
    assert "Waiting on design" in result["comments"][0]["body"]


async def test_transition_updates_updated_at():
    t = make_task()
    old_ts = t.updated_at
    result = json.loads(await task_transition(task_id=t.id, status="done", note="Shipped"))
    assert result["updated_at"] != old_ts


async def test_transition_invalid_status():
    t = make_task()
    result = json.loads(await task_transition(task_id=t.id, status="flying", note="x"))
    assert "error" in result


async def test_transition_unknown_task():
    result = json.loads(await task_transition(task_id="ghost", status="done", note="x"))
    assert "error" in result


async def test_transition_empty_note_rejected():
    t = make_task()
    result = json.loads(await task_transition(task_id=t.id, status="done", note="   "))
    assert "error" in result
