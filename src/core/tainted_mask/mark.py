"""污染标记统一入口 — 各接线点调用，registry 未注册时透明跳过（渐进启用）。

用法（接线点）：
    from src.core.tainted_mask.mark import mark_taint
    from src.core.tainted_mask.taint_flag import TaintFlag
    ...
    except Exception:
        mark_taint(TaintFlag.TAINT_EXCEPTION_SWALLOWED)
"""

from src.common.logger import get_logger
from src.core.tainted_mask.taint_flag import TaintFlag

logger = get_logger("core.tainted_mask.mark")


# ── 日志政策（2026-10-16，见 .shared/decisions/log_policy_roadmap.md）──────────
# 稳态只出声两次：**首次跳过**（进降级）+ **恢复**（降级→就绪），中间只累加计数。
# 改前每次调用都落一条 DEBUG ⇒ 宿主实测 135,635 行 / 32.8 MB（占全部行数 55%）。
# 它记的**不是跃迁**，而是"registry 在这个进程的存活期里一直没就绪"这一条稳态事实。
# 级别用 INFO（不是 DEBUG）：默认 file_log_level=INFO 之后 DEBUG 不落盘，而
# "标记被丢了多少次"正是要留给排障的那一行（政策 §0.2：状态跃迁 → INFO）。
_not_ready_logged = False
_skipped_count = 0


def taint_skip_stats() -> dict[str, int | bool]:
    """内省：预期降级跳过累计次数 + 是否已出声（供巡检/测试，不参与业务判断）。"""
    return {"not_ready_logged": _not_ready_logged, "skipped": _skipped_count}


def mark_taint(flag: TaintFlag) -> None:
    """标记污染位（幂等）；TaintedMaskPort 未注册或调用失败时跳过。

    ZG-7 spec §4.5 渐进启用：接线点不因 registry 未就绪而崩溃。
    未注册（port 为 None）是预期降级状态，静默跳过不上报；port 存在但
    add_taint 真失败才上报（防噪音——2026-08-07 修复：CRITICAL 动作链在
    registry 未就绪时连报 3 次 WARNING）。

    出声口径（2026-10-16 日志政策）：**首次跳过**与**恢复**各一条 INFO，
    其余只计数，可用 `taint_skip_stats()` 查。
    """
    global _not_ready_logged, _skipped_count
    try:
        from src.core.taint_mask_port_registry import get_taint_mask_port

        get_taint_mask_port().add_taint(flag)
    except RuntimeError as exc:
        # ZG-7 渐进启用：registry 未就绪（RuntimeError）是预期降级状态
        # P0-7: 出声（预期降级不上报）（ZG-31）
        _skipped_count += 1
        if not _not_ready_logged:
            _not_ready_logged = True
            logger.info(
                "taint registry 未就绪，跳过标记（预期降级；本条只报首次，其后只计数）: %s", exc
            )
    except Exception as exc:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        es_port = get_error_escalation_port()
        if es_port is not None:
            es_port.report(ErrorLevel.WARNING, "写入 taint 标记失败", exception=exc)
    else:
        # 降级→就绪是一次**跃迁**：出声一条，并把期间被丢掉的次数一次说清
        if _not_ready_logged:
            _not_ready_logged = False
            logger.info("taint registry 已就绪，恢复标记（此前跳过 %d 次）", _skipped_count)
            _skipped_count = 0


def mark_exception_swallowed(context: str = "") -> None:
    """快捷标记：异常吞没（except Exception: pass 路径）。"""
    if context:
        logger.debug("标记 TAINT_EXCEPTION_SWALLOWED: %s", context)
    mark_taint(TaintFlag.TAINT_EXCEPTION_SWALLOWED)
