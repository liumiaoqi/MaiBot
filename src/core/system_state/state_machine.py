"""系统生命周期状态机核心。

对标 Linux system_state（kernel.h:180）+ kernel_power_off（reboot.c:705）。
核心不导入任何组件具体类。流程：Lock 串行化 → 查表 → 幂等检查 →
先通知后赋值（机制 5）→ 记历史。
"""

import asyncio
import time
from pathlib import Path

from src.common.logger import get_logger
from src.core.system_state.history import TransitionHistory
from src.core.system_state.notifier_chain import CallbackType, NotifierChain, RollbackType
from src.core.system_state.types import (
    IllegalTransitionError,
    SystemLifecycleState,
    SystemLifecycleView,
    TransitionReason,
    TransitionRecord,
)

logger = get_logger(__name__)


class SystemStateMachine:
    """系统生命周期状态机核心。"""

    # 合法迁移表（W1: BOOTING→DEGRADING 降级启动）
    _TRANSITION_TABLE: dict[
        tuple[SystemLifecycleState, TransitionReason], SystemLifecycleState
    ] = {
        (SystemLifecycleState.BOOTING, TransitionReason.STARTUP_COMPLETE): SystemLifecycleState.READY,
        (SystemLifecycleState.BOOTING, TransitionReason.STARTUP_COMPLETE_DEGRADED): SystemLifecycleState.DEGRADING,
        (SystemLifecycleState.READY, TransitionReason.HEALTH_LEVEL_CHANGE): SystemLifecycleState.DEGRADING,
        (SystemLifecycleState.DEGRADING, TransitionReason.RECOVERY): SystemLifecycleState.READY,
        (SystemLifecycleState.READY, TransitionReason.SHUTDOWN_SIGNAL): SystemLifecycleState.SHUTTING_DOWN,
        (SystemLifecycleState.DEGRADING, TransitionReason.SHUTDOWN_SIGNAL): SystemLifecycleState.SHUTTING_DOWN,
        (SystemLifecycleState.BOOTING, TransitionReason.SHUTDOWN_SIGNAL): SystemLifecycleState.SHUTTING_DOWN,
    }

    def __init__(
        self,
        history_capacity: int = 100,
        notify_timeout: float = 5.0,
    ) -> None:
        self._state = SystemLifecycleState.BOOTING
        self._lock = asyncio.Lock()
        self._notifier = NotifierChain(timeout=notify_timeout)
        self._history = TransitionHistory(history_capacity)
        self._shutdown_entered = False

    # ── 状态查询（无锁内存读取）──────────────────────────────

    def get_state(self) -> SystemLifecycleState:
        return self._state

    def is_booting(self) -> bool:
        return self._state.is_booting()

    def is_ready(self) -> bool:
        return self._state.is_ready()

    def is_degrading(self) -> bool:
        return self._state.is_degrading()

    def is_shutting_down(self) -> bool:
        return self._state.is_shutting_down()

    def is_running_like(self) -> bool:
        return self._state.is_running_like()

    # ── 订阅 ──────────────────────────────────────────────

    def subscribe(
        self,
        callback: CallbackType,
        priority: int = 20,
        on_rollback: RollbackType | None = None,
    ):
        """注册迁移回调（数值小先通知）。返回订阅句柄。"""
        return self._notifier.register(callback, priority=priority, on_rollback=on_rollback)

    def unsubscribe(self, subscriber) -> None:
        self._notifier.unregister(subscriber)

    # ── 迁移触发 ──────────────────────────────────────────

    async def trigger_startup_complete(self) -> None:
        """正常启动完成 → READY。"""
        await self._execute_transition(TransitionReason.STARTUP_COMPLETE)

    async def trigger_startup_complete_degraded(self) -> None:
        """降级启动完成 → DEGRADING（W1）。"""
        await self._execute_transition(TransitionReason.STARTUP_COMPLETE_DEGRADED)

    async def trigger_health_level_change(self, new_level) -> None:
        """健康等级变更驱动 READY↔DEGRADING（StateAggregator 衔接映射）。"""
        level_value = getattr(new_level, "value", new_level)
        if self._state == SystemLifecycleState.READY:
            if level_value in ("degraded", "fault"):
                await self._execute_transition(TransitionReason.HEALTH_LEVEL_CHANGE)
        elif self._state == SystemLifecycleState.DEGRADING:
            if level_value in ("healthy", "recovering"):
                await self._execute_transition(TransitionReason.RECOVERY)
        # BOOTING / SHUTTING_DOWN → 忽略（生命周期阶段优先）

    async def trigger_shutdown(self) -> None:
        """SHUTDOWN_SIGNAL（SIGTERM/SIGINT/shutdown()），幂等守卫。"""
        await self._execute_transition(TransitionReason.SHUTDOWN_SIGNAL)

    # ── 内省 ──────────────────────────────────────────────

    def get_view(self, health_level: str, core_readiness: tuple[bool, bool, bool]) -> SystemLifecycleView:
        return SystemLifecycleView(
            state=self._state,
            health_level=health_level,
            core_readiness=core_readiness,
            transition_history=self.get_history(),
            generated_at=time.time(),
        )

    def get_history(self) -> list[TransitionRecord]:
        return self._history.get_all()

    def export_history_to(self, path: Path) -> None:
        """导出迁移历史到指定路径（崩溃/关闭，best-effort）。"""
        self._history.export_to_jsonl(path)

    # ── 内部 ──────────────────────────────────────────────

    async def _execute_transition(self, reason: TransitionReason) -> None:
        """迁移执行流程（Lock 串行化 → 查表 → 幂等 → 先通知后赋值 → 记历史）。"""
        start = time.monotonic()
        async with self._lock:
            old = self._state

            # 幂等守卫（机制 4）：进入 SHUTTING_DOWN 后重复 SHUTDOWN_SIGNAL
            # （如 SIGTERM 后又 SIGINT）静默返回，不抛错也不重复通知。
            # 必须在查表前：终态下 SHUTDOWN_SIGNAL 不在迁移表中，先查表会误抛。
            if reason == TransitionReason.SHUTDOWN_SIGNAL and self._shutdown_entered:
                return

            target = self._TRANSITION_TABLE.get((old, reason))
            if target is None:
                raise IllegalTransitionError(
                    f"非法迁移: {old.snake_case} --({reason.value})--> ?"
                )

            if target == SystemLifecycleState.SHUTTING_DOWN:
                # robust 模式：STOP 否决 + 逆序回滚（机制 2）
                ok = await self._notifier.notify_robust(old, target, reason)
                if not ok:
                    logger.warning("→SHUTTING_DOWN 被订阅者否决，状态保持 %s", old.snake_case)
                    return
            else:
                # 普通模式：健康降级不可否决（AC-ADAPT-01-3）
                await self._notifier.notify(old, target, reason)

            # 先通知后迁移（机制 5）：全部放行后才赋值
            self._state = target
            duration_ms = (time.monotonic() - start) * 1000
            self._history.append(
                TransitionRecord(
                    timestamp=time.time(),
                    old_state=old,
                    new_state=target,
                    reason=reason,
                    duration_ms=round(duration_ms, 2),
                )
            )
            if target == SystemLifecycleState.SHUTTING_DOWN:
                self._shutdown_entered = True
                self._export_history_on_shutdown()
            logger.info(
                "系统状态迁移: %s → %s（原因: %s, 耗时 %.2fms）",
                old.snake_case, target.snake_case, reason.value, duration_ms,
            )

    def _export_history_on_shutdown(self) -> None:
        """正常关闭时导出迁移历史（提示 2）。best-effort。"""
        try:
            self._history.export_to_jsonl(self._history.default_export_path())
        except Exception:
            logger.exception("迁移历史关闭导出失败")
