from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


class NotificationStatus(str, Enum):
    unread = "unread"
    read = "read"


class Notification(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    task_id: str
    task_title: str
    project: str
    due_date: str
    message: str
    fired_at: datetime = Field(default_factory=_now)
    status: NotificationStatus = NotificationStatus.unread
