"""ResourceLimitPort 注册点（ZG-5）。

供 main.py 注册、查询。未注册时返回 None（调用方自决默认值）。
"""

from typing import Optional

from src.core.protocols import ResourceLimitPort

_resource_limit: Optional[ResourceLimitPort] = None


def get_resource_limit_port() -> Optional[ResourceLimitPort]:
    """查询已注册的 ResourceLimitPort；未注册返回 None。"""
    return _resource_limit


def set_resource_limit_port(adapter: ResourceLimitPort) -> None:
    """注册 ResourceLimitPort（后注册覆盖）。"""
    global _resource_limit
    _resource_limit = adapter


def reset_resource_limit_port() -> None:
    """清空注册（测试用）。"""
    global _resource_limit
    _resource_limit = None
