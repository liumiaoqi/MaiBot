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


class SystemResourcesEventType(str, Enum):
    UPDATE = "update"
    SNAPSHOT = "snapshot"


class LLMStatsEventType(str, Enum):
    CALL_COMPLETED = "call_completed"
    SNAPSHOT = "snapshot"


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


def _collect_system_resources() -> dict[str, Any]:
    """采集系统资源数据。"""
    try:
        import psutil

        cpu_percent = psutil.cpu_percent(interval=0.0)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        return {
            "cpu_percent": cpu_percent,
            "memory_percent": mem.percent,
            "memory_used": mem.used,
            "memory_total": mem.total,
            "disk_percent": disk.percent,
            "disk_used": disk.used,
            "disk_total": disk.total,
            "timestamp": __import__("time").time(),
        }
    except ImportError:
        return {"error": "psutil 不可用", "timestamp": __import__("time").time()}


async def subscribe_system_resources(connection_id: str, request_id: str | None) -> None:
    """订阅系统资源域：立即推送 snapshot，之后每 5 秒推送 update。"""
    from src.webui.routers.websocket.manager import websocket_manager

    websocket_manager.subscribe(connection_id, domain="system_resources", topic="main")
    await websocket_manager.send_response(
        connection_id,
        request_id=request_id,
        ok=True,
        data={"domain": "system_resources", "topic": "main"},
    )
    snapshot_data = _collect_system_resources()
    await websocket_manager.send_event(
        connection_id,
        domain="system_resources",
        event="snapshot",
        topic="main",
        data=snapshot_data,
    )


async def unsubscribe_system_resources(connection_id: str, request_id: str | None) -> None:
    """退订系统资源域。"""
    from src.webui.routers.websocket.manager import websocket_manager

    websocket_manager.unsubscribe(connection_id, domain="system_resources", topic="main")
    await websocket_manager.send_response(
        connection_id,
        request_id=request_id,
        ok=True,
        data={"domain": "system_resources", "topic": "main"},
    )


async def subscribe_llm_stats(connection_id: str, request_id: str | None) -> None:
    """订阅 LLM 统计域：推送一次 snapshot（最近 24 小时统计摘要）。"""
    from src.webui.routers.websocket.manager import websocket_manager

    websocket_manager.subscribe(connection_id, domain="llm_stats", topic="main")
    await websocket_manager.send_response(
        connection_id,
        request_id=request_id,
        ok=True,
        data={"domain": "llm_stats", "topic": "main"},
    )
    try:
        from src.services.statistics_service import get_dashboard_statistics

        dashboard_data = await get_dashboard_statistics(hours=24, use_cache=True)
        snapshot_data = {
            "summary": dashboard_data.summary.model_dump(mode="json"),
            "model_stats": [m.model_dump(mode="json") for m in dashboard_data.model_stats],
            "timestamp": __import__("time").time(),
        }
    except Exception:
        snapshot_data = {"error": "获取统计数据失败", "timestamp": __import__("time").time()}

    await websocket_manager.send_event(
        connection_id,
        domain="llm_stats",
        event="snapshot",
        topic="main",
        data=snapshot_data,
    )


async def unsubscribe_llm_stats(connection_id: str, request_id: str | None) -> None:
    """退订 LLM 统计域。"""
    from src.webui.routers.websocket.manager import websocket_manager

    websocket_manager.unsubscribe(connection_id, domain="llm_stats", topic="main")
    await websocket_manager.send_response(
        connection_id,
        request_id=request_id,
        ok=True,
        data={"domain": "llm_stats", "topic": "main"},
    )


system_resources_domain = WSDomain(
    name="system_resources",
    event_types={"update", "snapshot"},
    subscribe_handler=subscribe_system_resources,
    unsubscribe_handler=unsubscribe_system_resources,
)

llm_stats_domain = WSDomain(
    name="llm_stats",
    event_types={"call_completed", "snapshot"},
    subscribe_handler=subscribe_llm_stats,
    unsubscribe_handler=unsubscribe_llm_stats,
)