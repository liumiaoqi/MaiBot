"""WatchdogPort 注册点。"""


from typing import Optional

from src.core.protocols import WatchdogPort

_watchdog_port: Optional[WatchdogPort] = None


def get_watchdog_port() -> WatchdogPort:
    """获取已注册的 WatchdogPort 实例。

    Returns:
        WatchdogPort 实例

    Raises:
        RuntimeError: WatchdogPort 未注册
    """
    if _watchdog_port is None:
        raise RuntimeError("WatchdogPort 未注册")
    return _watchdog_port


def set_watchdog_port(port: WatchdogPort) -> None:
    """注册 WatchdogPort 实例。

    Args:
        port: WatchdogPort 实例

    Raises:
        RuntimeError: WatchdogPort 已注册
    """
    global _watchdog_port
    if _watchdog_port is not None:
        raise RuntimeError("WatchdogPort 已注册")
    _watchdog_port = port


def clear_watchdog_port() -> None:
    """清除注册（供测试清理）。"""
    global _watchdog_port
    _watchdog_port = None