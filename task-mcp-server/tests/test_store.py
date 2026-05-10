import pytest
from task_mcp.models import Task
from task_mcp import store


@pytest.fixture(autouse=True)
def clean_store():
    store.reset()


def _task(project_name: str = "proj", **kwargs) -> Task:
    return Task(title="Test task", project_name=project_name, **kwargs)


def test_save_and_get():
    t = _task()
    store.save_task(t)
    assert store.get_task(t.id) == t


def test_get_unknown_returns_none():
    assert store.get_task("nonexistent") is None


def test_all_tasks():
    t1, t2 = _task(), _task()
    store.save_task(t1)
    store.save_task(t2)
    result = store.all_tasks()
    assert len(result) == 2
    assert t1 in result and t2 in result


def test_tasks_for_project_filters():
    t1 = _task(project_name="alpha")
    t2 = _task(project_name="beta")
    store.save_task(t1)
    store.save_task(t2)
    assert store.tasks_for_project("alpha") == [t1]


def test_delete_existing():
    t = _task()
    store.save_task(t)
    assert store.delete_task(t.id) is True
    assert store.get_task(t.id) is None


def test_delete_unknown_returns_false():
    assert store.delete_task("ghost") is False


def test_reset_clears_all():
    store.save_task(_task())
    store.reset()
    assert store.all_tasks() == []
