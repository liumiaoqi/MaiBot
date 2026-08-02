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
    """
    try:
        from src.core.taint_mask_port_registry import get_taint_mask_port

        get_taint_mask_port().add_taint(flag)
    except Exception:
        pass


def mark_exception_swallowed(context: str = "") -> None:
    """快捷标记：异常吞没（except Exception: pass 路径）。"""
    if context:
        from src.common.logger import get_logger

        get_logger("taint_mask").debug("标记 TAINT_EXCEPTION_SWALLOWED: %s", context)
    mark_taint(TaintFlag.TAINT_EXCEPTION_SWALLOWED)
