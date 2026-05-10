import pytest
from pydantic import ValidationError
from task_mcp.models import Task, Comment, TaskStatus, Priority


def test_task_defaults():
    task = Task(title="Fix login", project_name="auth")
    assert task.status == TaskStatus.todo
    assert task.priority == Priority.medium
    assert task.comments == []
    assert task.tags == []
    assert task.id is not None
    assert task.created_at is not None
    assert task.updated_at is not None


def test_task_invalid_status():
    with pytest.raises(ValidationError):
        Task(title="x", project_name="p", status="flying")


def test_task_invalid_priority():
    with pytest.raises(ValidationError):
        Task(title="x", project_name="p", priority="extreme")


def test_task_all_fields():
    task = Task(
        title="Deploy",
        project_name="infra",
        description="Deploy to prod",
        status=TaskStatus.in_progress,
        priority=Priority.urgent,
        assignee="john",
        due_date="2026-05-20",
        tags=["devops", "prod"],
    )
    assert task.assignee == "john"
    assert task.tags == ["devops", "prod"]


def test_comment_auto_timestamp():
    comment = Comment(author="maya", body="Looking into this")
    assert comment.id is not None
    assert comment.created_at is not None


def test_comment_requires_author_and_body():
    with pytest.raises(ValidationError):
        Comment(author="maya")
