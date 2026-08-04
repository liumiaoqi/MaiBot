"""SystemLifecycleAdapter Port 注册点（ZG-6）。

供 main.py 注册、WebUI 端点查询。未注册时返回 None（调用方自决默认值）。
"""

from typing import Any, Optional

_lifecycle_adapter: Optional[Any] = None


def get_system_lifecycle_adapter() -> Optional[Any]:
    """查询已注册的 SystemLifecycleAdapter；未注册返回 None。"""
    return _lifecycle_adapter


def set_system_lifecycle_adapter(adapter: Any) -> None:
    """注册 SystemLifecycleAdapter（后注册覆盖）。"""
    global _lifecycle_adapter
    _lifecycle_adapter = adapter


def reset_system_lifecycle_adapter() -> None:
    """清空注册（测试用）。"""
    global _lifecycle_adapter
    _lifecycle_adapter = None
