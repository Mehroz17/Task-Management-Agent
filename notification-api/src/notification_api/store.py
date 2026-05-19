from __future__ import annotations

import os
from collections import deque
from datetime import datetime, timezone

from notification_api.models import Notification, NotificationStatus

_MAX = int(os.environ.get("MAX_NOTIFICATIONS", "200"))
_inbox: deque[Notification] = deque()
_seen: dict[str, datetime] = {}  # task_id -> last fired_at


def add(n: Notification) -> None:
    _inbox.appendleft(n)
    _seen[n.task_id] = n.fired_at
    while len(_inbox) > _MAX:
        _inbox.pop()


def already_notified(task_id: str, within_hours: int) -> bool:
    if task_id not in _seen:
        return False
    elapsed = (datetime.now(timezone.utc) - _seen[task_id]).total_seconds() / 3600
    return elapsed < within_hours


def list_all(
    status: NotificationStatus | None = None,
    project: str | None = None,
) -> list[Notification]:
    result = list(_inbox)
    if status is not None:
        result = [n for n in result if n.status == status]
    if project is not None:
        result = [n for n in result if n.project == project]
    return result


def mark_read(notification_id: str) -> Notification | None:
    for n in _inbox:
        if n.id == notification_id:
            n.status = NotificationStatus.read
            return n
    return None


def clear() -> int:
    count = len(_inbox)
    _inbox.clear()
    _seen.clear()
    return count
