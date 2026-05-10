from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    todo = "todo"
    in_progress = "in_progress"
    blocked = "blocked"
    done = "done"


class Priority(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    urgent = "urgent"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Comment(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    author: str
    body: str
    created_at: str = Field(default_factory=_now)


class Task(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    project_name: str
    description: Optional[str] = None
    status: TaskStatus = TaskStatus.todo
    priority: Priority = Priority.medium
    assignee: Optional[str] = None
    due_date: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    comments: list[Comment] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
