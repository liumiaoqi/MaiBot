"""ErrorEscalationPort 注册点（ZG-14）。

供 main.py 注册、各接线点（except 改造 / ZG-7 委托 / OOM / 启动）获取。
未注册时 get_error_escalation_port 返回 None——调用方走兜底
（mark_exception_swallowed + logger.error），保持渐进透明
（spec §5.7.3 异常场景 2）。

port_registry 仅依赖 Protocol 接口做类型标注，具体实现由
main.py 启动时注入（核心禁止项 13）。
"""


from typing import Optional

from src.core.protocols import ErrorEscalationPort

_error_escalation_port: Optional[ErrorEscalationPort] = None


def get_error_escalation_port() -> Optional[ErrorEscalationPort]:
    """获取已注册的 ErrorEscalationPort 实例。

    Returns:
        ErrorEscalationPort 实例；未注册时返回 None（调用方走兜底）
    """
    return _error_escalation_port


def set_error_escalation_port(port: ErrorEscalationPort) -> None:
    """注册 ErrorEscalationPort 实例。

    Args:
        port: ErrorEscalationPort 实例（后注册覆盖）
    """
    global _error_escalation_port
    _error_escalation_port = port


def reset_error_escalation_port() -> None:
    """清空注册（测试用）。"""
    global _error_escalation_port
    _error_escalation_port = None
