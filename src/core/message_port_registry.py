"""全局 MessagePortV2 注册点。

核心模块通过 get_message_port_v2() 获取 MessagePortV2 实例，
不直接依赖 send_service 或其他组件。
"""


from typing import Any, Optional

from src.core.protocols import MessagePortV2
from src.core.startup.types import StartupPhase

_port_v2_instance: Optional[MessagePortV2] = None


def get_message_port_v2() -> MessagePortV2:
    """获取全局 MessagePortV2 实例。"""
    global _port_v2_instance
    if _port_v2_instance is None:
        raise RuntimeError("MessagePortV2 未注册，请在 main.py 启动时调用 set_message_port_v2()")
    return _port_v2_instance


def set_message_port_v2(port: MessagePortV2) -> None:
    """设置全局 MessagePortV2 实例（用于测试或替换实现）。"""
    global _port_v2_instance
    _port_v2_instance = port


# 已废弃（ZG-10 T31）：启动项元数据已由 @startup_item/StartupItemDesc 承载。
# 保留仅为过渡期兼容，禁止新代码读取。
__service_descriptor__: dict[str, Any] = {
    "name": "message_port_v2",
    "phase": StartupPhase.CORE_SERVICES,
    "order": 99,
    "critical": True,
    "protocol": MessagePortV2,
    "register_fn": set_message_port_v2,
    "depends_on": (),
}
