"""ForwardFetchPort 注册点（ZG16-1）。

供 main.py 注册、maisaka prefetch_forward_nodes 获取。
未注册时 get_forward_fetch_port 返回 None——调用方走兜底
（不写缓存，同步渲染降级为 [合并转发(拉取失败)]），保持渐进透明。

port_registry 仅依赖 Protocol 接口做类型标注，具体实现由
main.py 启动时注入（核心禁止项 13）。
"""


from typing import Optional

from src.core.protocols import ForwardFetchPort

_forward_fetch_port: Optional[ForwardFetchPort] = None


def get_forward_fetch_port() -> Optional[ForwardFetchPort]:
    """获取已注册的 ForwardFetchPort 实例。

    Returns:
        ForwardFetchPort 实例；未注册时返回 None（调用方走兜底）
    """
    return _forward_fetch_port


def set_forward_fetch_port(port: ForwardFetchPort) -> None:
    """注册 ForwardFetchPort 实例。

    Args:
        port: ForwardFetchPort 实例（后注册覆盖）
    """
    global _forward_fetch_port
    _forward_fetch_port = port


def reset_forward_fetch_port() -> None:
    """清空注册（测试用）。"""
    global _forward_fetch_port
    _forward_fetch_port = None