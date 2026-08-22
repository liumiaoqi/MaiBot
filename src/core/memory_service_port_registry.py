"""MemoryServicePort 注册点。

核心模块（invariants/health_checks）通过此 registry 获取 MemoryServicePort，
不直接导入适配器层（核心禁止项：核心不导入适配器层）。
main.py 启动时通过 set_memory_service_port() 注入；
未注入时 get 返回 None（调用方走兜底）。

port_registry 仅依赖 Protocol 接口做类型标注，具体实现由
main.py 启动时注入（核心禁止项 13）。
"""


from typing import Optional

from src.core.protocols import MemoryServicePort

_provider: Optional[MemoryServicePort] = None


def get_memory_service_port() -> Optional[MemoryServicePort]:
    """获取已注册的 MemoryServicePort 实例。

    Returns:
        MemoryServicePort 实例；未注册时返回 None（调用方走兜底）
    """
    return _provider


def set_memory_service_port(port: MemoryServicePort) -> None:
    """注册 MemoryServicePort 实例。

    Args:
        port: MemoryServicePort 实例（后注册覆盖）
    """
    global _provider
    _provider = port


def reset_memory_service_port() -> None:
    """清空注册（测试用）。"""
    global _provider
    _provider = None