"""污染标记统一入口 — 各接线点调用，registry 未注册时透明跳过（渐进启用）。

用法（接线点）：
    from src.core.tainted_mask.mark import mark_taint
    from src.core.tainted_mask.taint_flag import TaintFlag
    ...
    except Exception:
        mark_taint(TaintFlag.TAINT_EXCEPTION_SWALLOWED)
"""

from src.core.tainted_mask.taint_flag import TaintFlag


def mark_taint(flag: TaintFlag) -> None:
    """标记污染位（幂等）；TaintedMaskPort 未注册或调用失败时跳过。

    ZG-7 spec §4.5 渐进启用：接线点不因 registry 未就绪而崩溃。
    未注册（port 为 None）是预期降级状态，静默跳过不上报；port 存在但
    add_taint 真失败才上报（防噪音——2026-08-07 修复：CRITICAL 动作链在
    registry 未就绪时连报 3 次 WARNING）。
    """
    try:
        from src.core.taint_mask_port_registry import get_taint_mask_port

        port = get_taint_mask_port()
        if port is None:
            return  # ZG-7 渐进启用：registry 未就绪是预期状态，静默跳过
        port.add_taint(flag)
    except Exception as exc:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        es_port = get_error_escalation_port()
        if es_port is not None:
            es_port.report(ErrorLevel.WARNING, "写入 taint 标记失败", exception=exc)


def mark_exception_swallowed(context: str = "") -> None:
    """快捷标记：异常吞没（except Exception: pass 路径）。"""
    if context:
        from src.common.logger import get_logger

        get_logger("taint_mask").debug("标记 TAINT_EXCEPTION_SWALLOWED: %s", context)
    mark_taint(TaintFlag.TAINT_EXCEPTION_SWALLOWED)
