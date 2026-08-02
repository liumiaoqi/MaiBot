"""故障恢复引擎 — 指数退避 + 重启风暴保护 + OOM 重应用。

委托 LifecycleManager 执行停止/启动。
"""


import asyncio
import time
from collections import deque
from typing import TYPE_CHECKING, Awaitable, Callable, Optional

from src.core.service_manager.types import ServiceDescriptor

if TYPE_CHECKING:
    from src.core.service_manager.lifecycle import LifecycleManager

from src.common.logger import get_logger

logger = get_logger(__name__)


class RecoveryEngine:
    """故障恢复引擎 — 指数退避 + 滑动窗口风暴保护。

    内部维护：
    - _backoff_base: 退避基数（秒）
    - _backoff_cap: 退避上限（秒）
    - _storm_window: 风暴窗口（秒）
    - _storm_threshold: 风暴阈值（次）
    - _failure_windows: component_id → 最近失败时间戳队列
    - _backoff_counts: component_id → 连续退避次数
    - _cancel_events: component_id → 取消事件（退避期间手动操作时 set）
    """

    def __init__(
        self,
        backoff_base_sec: float = 1.0,
        backoff_cap_sec: float = 300.0,
        storm_window_sec: float = 600.0,
        storm_threshold: int = 5,
    ) -> None:
        self._backoff_base = backoff_base_sec
        self._backoff_cap = backoff_cap_sec
        self._storm_window = storm_window_sec
        self._storm_threshold = storm_threshold
        self._failure_windows: dict[str, deque[float]] = {}
        self._backoff_counts: dict[str, int] = {}
        self._cancel_events: dict[str, asyncio.Event] = {}

    def compute_backoff(self, backoff_count: int) -> float:
        """返回 min(基数 × 2^n, 上限)。"""
        return min(self._backoff_base * (2 ** backoff_count), self._backoff_cap)

    def record_failure(self, component_id: str) -> None:
        """记录一次失败时间戳到滑动窗口。"""
        now = time.monotonic()
        window = self._failure_windows.setdefault(component_id, deque())
        window.append(now)
        cutoff = now - self._storm_window
        while window and window[0] < cutoff:
            window.popleft()

    def is_storm(self, component_id: str) -> bool:
        """滑动窗口内失败次数 ≥ 阈值则返回 True。"""
        window = self._failure_windows.get(component_id)
        if window is None:
            return False
        now = time.monotonic()
        cutoff = now - self._storm_window
        while window and window[0] < cutoff:
            window.popleft()
        return len(window) >= self._storm_threshold

    def reset_count(self, component_id: str) -> None:
        """恢复成功时清零退避计数与滑动窗口。"""
        self._backoff_counts.pop(component_id, None)
        self._failure_windows.pop(component_id, None)

    def get_backoff_count(self, component_id: str) -> int:
        """获取组件当前连续退避次数。"""
        return self._backoff_counts.get(component_id, 0)

    async def recover(
        self,
        component_id: str,
        lifecycle_manager: "LifecycleManager",
        descriptor: Optional[ServiceDescriptor] = None,
        oom_hook: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> bool:
        """完整恢复流程。

        1. 检查 is_storm，达阈值则返回 False（调用方置 FAULT_MANUAL）
        2. 计算退避时间，await asyncio.sleep（支持取消）
        3. 委托 lifecycle_manager.stop 停止残留
        4. 委托 lifecycle_manager.start 启动
        5. 若 oom_hook 非空且组件 oom_protected，调用 OOM 重应用钩子
        6. 返回 True 表示恢复流程已执行

        Returns:
            True 表示恢复流程已执行；False 表示风暴保护触发，需人工介入
        """
        if self.is_storm(component_id):
            logger.warning("组件 %s 触发重启风暴保护，转入故障(需人工)", component_id)
            return False

        backoff_count = self.get_backoff_count(component_id)
        backoff_sec = self.compute_backoff(backoff_count)
        self._backoff_counts[component_id] = backoff_count + 1

        cancel_event = asyncio.Event()
        self._cancel_events[component_id] = cancel_event

        try:
            # 退避等待，支持取消
            try:
                await asyncio.wait_for(
                    asyncio.shield(cancel_event.wait()),
                    timeout=backoff_sec,
                )
                # cancel_event 被 set，说明手动操作取消了自动恢复
                logger.info("组件 %s 自动恢复被手动操作取消", component_id)
                self.reset_count(component_id)
                return True
            except asyncio.TimeoutError:
                pass  # 退避时间到，继续恢复

            # 委托停止残留
            try:
                await lifecycle_manager.stop(component_id, force=True, confirmed=True)
            except Exception:
                from src.core.tainted_mask.mark import mark_exception_swallowed
                mark_exception_swallowed()
                logger.warning(
                    "组件 %s 恢复流程停止残留异常，继续尝试启动",
                    component_id,
                    exc_info=True,
                )

            # 委托启动
            await lifecycle_manager.start(component_id)

            # OOM 重应用（ZG-9 OS 级 OOM 保护的兼容回退路径 = TAINT_COMPAT_FALLBACK）
            if (
                oom_hook is not None
                and descriptor is not None
                and descriptor.oom_protected
            ):
                try:
                    from src.core.tainted_mask.mark import mark_taint
                    from src.core.tainted_mask.taint_flag import TaintFlag

                    mark_taint(TaintFlag.TAINT_COMPAT_FALLBACK)
                    await oom_hook(component_id)
                except Exception:
                    from src.core.tainted_mask.mark import mark_exception_swallowed
                    mark_exception_swallowed()
                    logger.warning(
                        "组件 %s OOM 重应用异常", component_id, exc_info=True
                    )

            return True
        except Exception:
            from src.core.tainted_mask.mark import mark_exception_swallowed
            mark_exception_swallowed()
            logger.error(
                "组件 %s 恢复流程异常，需人工介入", component_id, exc_info=True
            )
            return False
        finally:
            self._cancel_events.pop(component_id, None)

    def cancel_recovery(self, component_id: str) -> None:
        """手动操作时取消待执行的自动恢复。"""
        event = self._cancel_events.get(component_id)
        if event is not None:
            event.set()
