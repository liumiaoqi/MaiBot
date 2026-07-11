"""WebSocket 域注册表 — 解耦 unified.py 中的 if-elif 链。"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine


class LogsEventType(str, Enum):
    ENTRY = "entry"
    SNAPSHOT = "snapshot"


class PluginProgressEventType(str, Enum):
    UPDATE = "update"
    SNAPSHOT = "snapshot"


class MaisakaMonitorEventType(str, Enum):
    STAGE_SNAPSHOT = "stage.snapshot"


class ChatEventType(str, Enum):
    MESSAGE = "message"


@dataclass
class WSDomain:
    name: str
    event_types: set[str]
    subscribe_handler: Callable[..., Coroutine[Any, Any, None]]
    unsubscribe_handler: Callable[..., Coroutine[Any, Any, None]] | None = None
    call_handler: Callable[..., Coroutine[Any, Any, None]] | None = None


class WSDomainRegistry:
    def __init__(self) -> None:
        self._domains: dict[str, WSDomain] = {}

    def register(self, domain: WSDomain) -> None:
        self._domains[domain.name] = domain

    def get(self, name: str) -> WSDomain | None:
        return self._domains.get(name)

    def list_domains(self) -> list[str]:
        return list(self._domains.keys())


ws_domain_registry = WSDomainRegistry()