"""事件优先级管理。

群事件反应与正常对话消息协调，用户消息优先级高于群事件反应。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

from .sensor import GroupEvent

logger = logging.getLogger(__name__)


class EventPriority(IntEnum):
    """事件优先级。"""

    USER_MESSAGE = 100
    PROACTIVE_CHAT = 50
    GROUP_EVENT_REACTION = 30
    SYSTEM_EVENT = 10


@dataclass
class PrioritizedEvent:
    """带优先级的事件。"""

    event_type: str
    priority: EventPriority
    data: Any = None
    timestamp: float = 0.0


class EventPriorityManager:
    """事件优先级管理器。"""

    def __init__(self) -> None:
        self._queue: list[PrioritizedEvent] = []

    def enqueue_user_message(self, data: Any, timestamp: float = 0.0) -> None:
        """入队用户消息。"""
        self._queue.append(PrioritizedEvent(
            event_type="user_message",
            priority=EventPriority.USER_MESSAGE,
            data=data,
            timestamp=timestamp,
        ))

    def enqueue_group_event(self, event: GroupEvent) -> None:
        """入队群事件反应。"""
        self._queue.append(PrioritizedEvent(
            event_type="group_event",
            priority=EventPriority.GROUP_EVENT_REACTION,
            data=event,
            timestamp=event.timestamp,
        ))

    def enqueue_proactive(self, data: Any, timestamp: float = 0.0) -> None:
        """入队主动对话。"""
        self._queue.append(PrioritizedEvent(
            event_type="proactive",
            priority=EventPriority.PROACTIVE_CHAT,
            data=data,
            timestamp=timestamp,
        ))

    def dequeue_next(self) -> PrioritizedEvent | None:
        """按优先级出队下一个事件。"""
        if not self._queue:
            return None

        self._queue.sort(key=lambda e: (-e.priority, e.timestamp))
        return self._queue.pop(0)

    def has_pending(self) -> bool:
        """是否有待处理事件。"""
        return len(self._queue) > 0

    def clear(self) -> None:
        """清空队列。"""
        self._queue.clear()