"""ZG-7 污染标记 — 不可逆污染位图核心。

对标 Linux `tainted_mask`（panic.c:59-60）+ `add_taint`（panic.c:954-965）：
- 位图只增不减（spec §2.1.1 规则 1），污染是历史烙记，与 ZG-6 状态机正交
- 幂等置位：重复 add_taint 不改变位图、不重复触发动作与广播（spec §2.1.1 规则 2）
- 首次记录：时间戳 + 调用栈，重复置位不覆盖（spec §2.1.1 规则 3）
- warn_count 每次 add_taint(TAINT_WARN) 递增（含幂等分支，计数非动作，
  对标 Linux `atomic_inc_return(&warn_count)` panic.c:234）
- warn_limit 累计封顶触发 TRIGGER_DEGRADE（对标 `check_panic_on_warn`，降级而非 panic）
- 无 clear/remove/reset API（spec §2.1.1 规则 5 禁止项）
"""

import asyncio
import time
import traceback
from typing import Any, Callable, Optional

from src.common.logger import get_logger
from src.core.tainted_mask.taint_action import TaintAction
from src.core.tainted_mask.taint_flag import TAINT_FLAGS_MAX, TaintFlag
from src.core.tainted_mask.types import TaintNotifyEvent, TaintRecord, TaintSubscriber

logger = get_logger("core.tainted_mask")

# 调用栈截断长度（spec §3.4：截断至 500 字符）
_STACK_MAX_LEN = 500
# 调用栈取样层数（design §3.4.2：最近 5 层）
_STACK_FRAMES = 5


class TaintedMask:
    """不可逆污染位图 — 置位 / 查询 / 内省输出。

    非单例：由 TaintMaskAdapter 创建并持有唯一实例（ADR-6）。
    """

    def __init__(
        self,
        on_taint: Optional[dict[TaintFlag, TaintAction]] = None,
        warn_limit: int = 0,
        state_machine_port: Any = None,
        time_func: Callable[[], float] = time.time,
        preset_mask: int = 0,
        degrade_on_taint_mask: int = 0,
    ) -> None:
        """初始化污染位图。

        Args:
            on_taint: 动作映射表（缺省标志默认 RECORD，spec §2.3.1 规则 1）
            warn_limit: WARN 累计阈值（0 = 禁用，spec §4.2 规则 3）
            state_machine_port: ZG-6 SystemStateMachine（TRIGGER_DEGRADE 使用，
                None 时降级为 WARN）
            time_func: 时间函数注入点（测试可替换，spec §5.3 规则 4）
            preset_mask: 预置位掩码（对标 CONFIG_RANDSTRUCT 预置，spec §2.1.1 规则 4）
            degrade_on_taint_mask: 掩码级降级触发掩码（0=禁用，对标 Linux panic_on_taint）

        Raises:
            ValueError: preset_mask 或 degrade_on_taint_mask 超范围（> TAINT_FLAGS_MAX）
        """
        if preset_mask & ~TAINT_FLAGS_MAX:
            raise ValueError(f"preset_mask 超范围: 0x{preset_mask:X} > 0x{TAINT_FLAGS_MAX:X}")
        if degrade_on_taint_mask & ~TAINT_FLAGS_MAX:
            raise ValueError(f"degrade_on_taint_mask 超范围: 0x{degrade_on_taint_mask:X} > 0x{TAINT_FLAGS_MAX:X}")
        self._mask: int = preset_mask
        self._first_taints: dict[int, TaintRecord] = {}
        self._on_taint: dict[TaintFlag, TaintAction] = dict(on_taint or {})
        self._subscribers: list[TaintSubscriber] = []
        self._warn_count: int = 0
        self._warn_limit: int = max(0, int(warn_limit))
        self._time_func = time_func
        self._state_machine_port = state_machine_port
        self._degrade_on_taint_mask: int = degrade_on_taint_mask

    # ── 置位 / 查询 ──────────────────────────────────────────────

    def add_taint(self, flag: TaintFlag) -> None:
        """置位污染标志（幂等，只增不减）。

        流程：校验 → 幂等检查 → 置位 → 记录首次 → 结构化日志 →
        执行动作（fire-and-forget）→ 广播通知（design §3.1.3）。

        Args:
            flag: 污染标志

        Raises:
            ValueError: flag 不在 TaintFlag 枚举中（spec §2.1.3 异常场景 1）
        """
        if not isinstance(flag, TaintFlag):
            raise ValueError(f"非法污染标志: {flag!r}")

        is_first = not (self._mask & flag.value)

        if is_first:
            # 首次置位：先判定实际 action，再创建 TaintRecord
            stack = self._capture_stack()
            mask_matched = flag.value & self._degrade_on_taint_mask != 0
            if mask_matched:
                action = TaintAction.TRIGGER_DEGRADE
                taint_trigger_source = "degrade_mask"
            else:
                action = self._on_taint.get(flag, TaintAction.RECORD)
                taint_trigger_source = "on_taint"
            record = TaintRecord(
                flag=flag,
                first_ts=self._time_func(),
                first_stack=stack,
                action_taken=action,
            )
            self._first_taints[flag.bit_position] = record
            self._mask |= flag.value

            # 结构化日志（spec §4.2 规则 1）
            logger.info(
                "污染位置位: flag=%s, first_ts=%.3f, action=%s, current_mask=0x%X",
                flag.name,
                record.first_ts,
                action.name,
                self._mask,
                taint_flag=flag.name,
                taint_first_ts=record.first_ts,
                taint_stack=stack,
                taint_action=action.name,
                taint_mask=self._mask,
                taint_trigger_source=taint_trigger_source,
            )

            # 执行动作（fire-and-forget：同步方法内调度异步操作）
            self._execute_action(flag, action)

            # 广播通知（nofail 语义）
            event = TaintNotifyEvent(flag=flag, first_ts=record.first_ts, current_mask=self._mask)
            self._notify_nofail(event)
        # warn_count 每次 add_taint(TAINT_WARN) 递增（含首次与幂等分支，
        # 计数非动作，spec §4.2 规则 2；对标 atomic_inc_return）
        # 掩码匹配时跳过阈值降级（避免同一次 add_taint 双触发 TRIGGER_DEGRADE）
        self._bump_warn_count(flag, mask_matched=is_first and mask_matched)

    def _bump_warn_count(self, flag: TaintFlag, *, mask_matched: bool = False) -> None:
        """warn_count 递增（每次 add_taint(TAINT_WARN) 调用时，含幂等分支）。

        对标 Linux `atomic_inc_return(&warn_count)`（panic.c:234）；
        warn_limit > 0 且累计达到阈值时触发 TRIGGER_DEGRADE（对标
        `check_panic_on_warn`，但降级而非 panic）。
        掩码匹配时跳过阈值降级（掩码已触发降级，避免双触发）。
        """
        if flag is not TaintFlag.TAINT_WARN:
            return
        self._warn_count += 1
        if self._warn_limit > 0 and self._warn_count >= self._warn_limit:
            if mask_matched:
                logger.info(
                    "warn_count=%d 达到 warn_limit=%d，但掩码已触发降级，跳过阈值降级",
                    self._warn_count,
                    self._warn_limit,
                )
                return
            logger.warning(
                "warn_count=%d 达到 warn_limit=%d，触发 TRIGGER_DEGRADE",
                self._warn_count,
                self._warn_limit,
            )
            self._execute_action(flag, TaintAction.TRIGGER_DEGRADE)

    def test_taint(self, flag: TaintFlag) -> bool:
        """测试污染标志是否置位（O(1) 位运算）。"""
        return (self._mask & flag.value) != 0

    def get_taint(self) -> int:
        """查询污染位图值。"""
        return self._mask

    def get_degrade_on_taint_mask(self) -> int:
        """查询当前掩码级降级触发掩码值（只读，0=禁用）。"""
        return self._degrade_on_taint_mask

    # ── 内省输出 ────────────────────────────────────────────────

    def print_tainted(self) -> str:
        """输出污染状态单行字符串（spec §2.4.1 规则 1）。

        全干净 → "Not tainted"；有脏位 → "Tainted: " + 逐位拼字符
        （置位输出 c_true，未置位输出 c_false）。不含位号/时间戳（规则 5）。
        """
        if self._mask == 0:
            return "Not tainted"
        parts = []
        for flag in TaintFlag:
            if self._mask & flag.value:
                parts.append(flag.c_true)
            else:
                parts.append(flag.c_false)
        return "Tainted: " + "".join(parts)

    def print_tainted_verbose(self) -> list[str]:
        """仅列置位项，格式 "[c_true]=[标志名]"（spec §2.4.1 规则 2）。"""
        return [f"{flag.c_true}={flag.name}" for flag in TaintFlag if self._mask & flag.value]

    def get_taint_records(self) -> dict[int, TaintRecord]:
        """查询全部首次置位记录（副本）。"""
        return dict(self._first_taints)

    @property
    def warn_count(self) -> int:
        """WARN 累计计数（只读，对标 /sys/kernel/warn_count）。"""
        return self._warn_count

    # ── 订阅（T8：轻量订阅表，非 NotifierChain）──────────────────

    def subscribe(self, callback: TaintSubscriber) -> int:
        """订阅污染位变化通知（首次置位时广播）。

        Args:
            callback: 回调（同步或异步，接收 TaintNotifyEvent）

        Returns:
            订阅句柄（用于 unsubscribe）
        """
        self._subscribers.append(callback)
        return len(self._subscribers) - 1

    def unsubscribe(self, handle: int) -> None:
        """取消订阅。"""
        if 0 <= handle < len(self._subscribers):
            self._subscribers[handle] = None  # type: ignore[assignment]

    def _notify_nofail(self, event: TaintNotifyEvent) -> None:
        """广播通知（nofail 语义：遍历到底，订阅者异常仅记日志不阻断）。

        对标 Linux `panic_notifier_list` 的遍历到底语义（spec §4.1 规则 1）。
        """
        for callback in list(self._subscribers):
            if callback is None:
                continue
            try:
                result = callback(event)
                if result is not None and asyncio.iscoroutine(result):
                    # 异步回调：fire-and-forget
                    try:
                        asyncio.get_running_loop().create_task(result)
                    except RuntimeError:
                        logger.warning("无事件循环，跳过异步订阅回调", exc_info=True)
            except Exception:
                from src.core.tainted_mask.mark import mark_exception_swallowed
                mark_exception_swallowed()
                logger.warning("污染通知订阅回调异常（flag=%s）", event.flag.name, exc_info=True)

    # ── 内部工具 ─────────────────────────────────────────────────

    def _execute_action(self, flag: TaintFlag, action: TaintAction) -> None:
        """执行 on_taint 动作（design §3.3.3）。

        RECORD：仅记录（主流程已完成）
        WARN：额外 WARNING 日志
        TRIGGER_DEGRADE：驱动 ZG-6 降级；失败不回滚污染位（spec §2.3.1 规则 5）
        """
        match action:
            case TaintAction.RECORD:
                pass
            case TaintAction.WARN:
                logger.warning("污染位 %s 触发 WARN 动作", flag.name)
            case TaintAction.TRIGGER_DEGRADE:
                if self._state_machine_port is None:
                    # 无状态机端口：降级为 WARN（design §5.1）
                    logger.warning(
                        "TAINT_ACTION_FAILED: state_machine_port 未注入，"
                        "TRIGGER_DEGRADE 降级为 WARN（flag=%s）",
                        flag.name,
                    )
                    return
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(self._trigger_degrade_async(flag))
                except RuntimeError:
                    # 无事件循环（如 import hook 早期）或循环已关闭（shutdown 路径）：
                    # 跳过异步操作，污染位已正确置位（design §3.1.3 无事件循环降级；
                    # CX P2：create_task 也可能抛 RuntimeError，动作失败不阻断调用方）
                    logger.warning(
                        "TAINT_ASYNC_SKIP: 无事件循环或已关闭，TRIGGER_DEGRADE 跳过（flag=%s）",
                        flag.name,
                    )
                except Exception:
                    from src.core.tainted_mask.mark import mark_exception_swallowed
                    mark_exception_swallowed()
                    logger.error(
                        "TAINT_ACTION_FAILED: 污染位 %s 的 TRIGGER_DEGRADE 调度失败",
                        flag.name,
                        exc_info=True,
                    )

    async def _trigger_degrade_async(self, flag: TaintFlag) -> None:
        """TRIGGER_DEGRADE 异步执行：驱动 READY→DEGRADING（spec §2.3.1 规则 4）。"""
        try:
            await self._state_machine_port.trigger_health_level_change("fault")
        except Exception:
            # 动作失败不回滚污染位（不可逆优先，spec §2.3.1 规则 5）
            from src.core.tainted_mask.mark import mark_exception_swallowed
            mark_exception_swallowed()
            logger.error(
                "TAINT_ACTION_FAILED: 污染位 %s 的 TRIGGER_DEGRADE 动作执行失败",
                flag.name,
                exc_info=True,
            )

    def _capture_stack(self) -> str:
        """调用栈摘要：最近 5 层，截断至 500 字符（design §3.4.2）。"""
        frames = traceback.format_stack()[-_STACK_FRAMES:]
        return "".join(frames)[:_STACK_MAX_LEN]
