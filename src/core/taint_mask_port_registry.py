"""TaintedMaskPort 注册点（ZG-7）。

供 main.py 注册、WebUI 诊断端点查询。未注册时 get_taint_mask_port 抛
RuntimeError（调用方应捕获并降级，保持渐进透明性）。
"""


from typing import Optional

from src.core.protocols import TaintedMaskPort

_taint_mask_port: Optional[TaintedMaskPort] = None


def get_taint_mask_port() -> TaintedMaskPort:
    """获取已注册的 TaintedMaskPort 实例。

    Returns:
        TaintedMaskPort 实例

    Raises:
        RuntimeError: TaintedMaskPort 未注册
    """
    if _taint_mask_port is None:
        raise RuntimeError("TaintedMaskPort 未注册")
    return _taint_mask_port


def set_taint_mask_port(port: TaintedMaskPort) -> None:
    """注册 TaintedMaskPort 实例。

    Args:
        port: TaintedMaskPort 实例（后注册覆盖）
    """
    global _taint_mask_port
    _taint_mask_port = port


def reset_taint_mask_port() -> None:
    """清空注册（测试用）。"""
    global _taint_mask_port
    _taint_mask_port = None
