import json
from datetime import datetime, timezone, timedelta
from helpers import make_task
from task_mcp.models import TaskStatus
from task_mcp.tools.project_view import project_view


def _yesterday() -> str:
    return (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")


async def test_total_count():
    make_task(project_name="alpha")
    make_task(project_name="alpha")
    make_task(project_name="beta")
    result = json.loads(await project_view(project_name="alpha"))
    assert result["total"] == 2


async def test_status_breakdown():
    make_task(project_name="p", status=TaskStatus.todo)
    make_task(project_name="p", status=TaskStatus.done)
    make_task(project_name="p", status=TaskStatus.blocked)
    result = json.loads(await project_view(project_name="p"))
    assert result["by_status"]["todo"] == 1
    assert result["by_status"]["done"] == 1
    assert result["by_status"]["blocked"] == 1


async def test_overdue_detection():
    make_task(project_name="p", due_date=_yesterday(), status=TaskStatus.todo)
    make_task(project_name="p", due_date=_yesterday(), status=TaskStatus.done)
    result = json.loads(await project_view(project_name="p"))
    assert result["overdue_count"] == 1


async def test_by_assignee():
    make_task(project_name="p", assignee="maya")
    make_task(project_name="p", assignee="maya")
    make_task(project_name="p", assignee="john")
    result = json.loads(await project_view(project_name="p"))
    assert result["by_assignee"]["maya"] == 2
    assert result["by_assignee"]["john"] == 1


async def test_empty_project():
    result = json.loads(await project_view(project_name="empty"))
    assert result["total"] == 0
    assert result["overdue_count"] == 0
