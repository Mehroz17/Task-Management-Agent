import pytest
from task_mcp import store


@pytest.fixture(autouse=True)
def clean_store():
    store.reset()
