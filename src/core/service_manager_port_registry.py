"""ServiceManager / CoreReadiness / HealthProbe Port 注册点。"""


from typing import Any, Optional

from src.core.protocols import CoreReadinessPort, HealthProbePort, ServiceManagerPort
from src.core.startup.types import StartupPhase

_service_manager: Optional[ServiceManagerPort] = None
_core_readiness: Optional[CoreReadinessPort] = None
_health_probe_registry: dict[str, HealthProbePort] = {}


def get_service_manager_port() -> Optional[ServiceManagerPort]:
    return _service_manager


def set_service_manager_port(port: ServiceManagerPort) -> None:
    global _service_manager
    _service_manager = port


def reset_service_manager_port() -> None:
    global _service_manager
    _service_manager = None


def get_core_readiness_port() -> Optional[CoreReadinessPort]:
    return _core_readiness


def set_core_readiness_port(port: CoreReadinessPort) -> None:
    global _core_readiness
    _core_readiness = port


def reset_core_readiness_port() -> None:
    global _core_readiness
    _core_readiness = None


def register_health_probe(component_id: str, probe: HealthProbePort) -> None:
    """注册组件健康探针。"""
    _health_probe_registry[component_id] = probe


def get_health_probe(component_id: str) -> Optional[HealthProbePort]:
    """查询组件健康探针。"""
    return _health_probe_registry.get(component_id)


def reset_health_probe_registry() -> None:
    _health_probe_registry.clear()


__service_descriptor__: dict[str, Any] = {
    "name": "service_manager_port",
    "phase": StartupPhase.READY,
    "order": 50,
    "critical": True,
    "protocol": ServiceManagerPort,
    "register_fn": set_service_manager_port,
    "depends_on": (),
}