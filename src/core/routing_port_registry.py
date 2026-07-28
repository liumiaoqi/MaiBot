"""AgentRoutingService 注册点。

遵循项目 Port 注册模式：模块级全局变量 + register/get 函数。
"""

from __future__ import annotations

from typing import Any, Optional

from src.core.protocols import AgentRoutingService
from src.core.startup.types import StartupPhase

_routing_service: Optional[AgentRoutingService] = None


def register_routing_service(service: AgentRoutingService) -> None:
    """注册全局 AgentRoutingService 实例（main.py 调用）。"""
    global _routing_service
    _routing_service = service


def get_routing_service() -> Optional[AgentRoutingService]:
    """获取已注册的 AgentRoutingService，未注册时返回 None。"""
    return _routing_service


__service_descriptor__: dict[str, Any] = {
    "name": "chat_manager_adapter",  # routing 是 adapter 的一部分
    "phase": StartupPhase.CORE_SERVICES,
    "order": 2,
    "critical": True,
    "protocol": AgentRoutingService,
    "register_fn": register_routing_service,
    "depends_on": ("agent_registry", "session_submodules"),
}
