"""IPC 桥接端口注册点。"""


from typing import Any, Optional

from src.core.protocols import IpcBridgePort
from src.core.startup.types import StartupPhase

_port_instance: Optional[IpcBridgePort] = None


def get_ipc_bridge_port() -> Optional[IpcBridgePort]:
    """查询已注入的 IPC 桥接端口；未注入返回 None（优雅降级）。"""
    return _port_instance


def set_ipc_bridge_port(port: IpcBridgePort) -> None:
    """注册 IPC 桥接端口（后注册覆盖）。"""
    global _port_instance
    _port_instance = port


def reset_ipc_bridge_port() -> None:
    """清空注册（测试和关闭流程使用）。"""
    global _port_instance
    _port_instance = None


# 已废弃（ZG-10 T31）：启动项元数据已由 @startup_item/StartupItemDesc 承载。
# 保留仅为过渡期兼容，禁止新代码读取。
__service_descriptor__: dict[str, Any] = {
    "name": "ipc_bridge_port",
    "phase": StartupPhase.SUBSYSTEMS,
    "order": 1,
    "critical": False,
    "protocol": IpcBridgePort,
    "register_fn": set_ipc_bridge_port,
    "depends_on": ("plugin_runtime",),
}
