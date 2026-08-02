"""健康检查引擎 — 主动探测循环 + 被动心跳接收 + 连续失败转故障。

异步，不阻塞主事件循环。
"""


import asyncio
import time
from typing import Awaitable, Callable

from src.core.service_manager.types import (
    FaultReason,
    HealthCheckMode,
    HealthCheckResult,
    ServiceDescriptor,
    ServiceState,
    ServiceStateSnapshot,
)

from src.common.logger import get_logger

logger = get_logger(__name__)


class HealthCheckEngine:
    """健康检查引擎 — 主动探测 + 被动心跳 + 连续失败转故障。

    内部维护：
    - _registry: 组件注册表引用（只读，不写入）
    - _descriptors: 组件描述符表引用（只读）
    - _probe_functions: component_id → 探针可调用对象
    - _fault_callback: 连续失败达阈值时的异步回调
    - _consecutive_failures: component_id → 连续失败次数（内部跟踪）
    - _last_heartbeats: component_id → 最近心跳时间戳
    """

    def __init__(
        self,
        component_registry: dict[str, ServiceStateSnapshot],
        descriptors: dict[str, ServiceDescriptor],
        probe_functions: dict[str, Callable[[], Awaitable[HealthCheckResult]]],
        fault_callback: Callable[[str, FaultReason, str], Awaitable[None]],
        probe_timeout_sec: float = 5.0,
        consecutive_fail_threshold: int = 2,
    ) -> None:
        self._registry = component_registry
        self._descriptors = descriptors
        self._probe_functions = probe_functions
        self._fault_callback = fault_callback
        self._probe_timeout = probe_timeout_sec
        self._fail_threshold = consecutive_fail_threshold
        self._consecutive_failures: dict[str, int] = {}
        self._last_heartbeats: dict[str, float] = {}

    async def run_loop(self, stop_event: asyncio.Event) -> None:
        """主检查循环，按各组件 check_interval_sec 周期触发。

        stop_event set 时退出。
        """
        next_check: dict[str, float] = {}
        now = time.monotonic()

        for cid in self._registry:
            next_check[cid] = now

        while not stop_event.is_set():
            now = time.monotonic()

            # 探测到期组件
            due = [cid for cid, t in next_check.items() if t <= now]
            for cid in due:
                if stop_event.is_set():
                    break
                await self._probe_one(cid)
                desc = self._descriptors.get(cid)
                interval = desc.check_interval_sec if desc else 30
                next_check[cid] = time.monotonic() + interval

            # 检查心跳超时
            await self._check_heartbeat_timeout()

            # 新加入的组件纳入调度
            for cid in self._registry:
                if cid not in next_check:
                    next_check[cid] = time.monotonic()

            # 计算下次唤醒时间
            if next_check:
                min_next = min(next_check.values())
                sleep_sec = max(0.1, min_next - time.monotonic())
            else:
                sleep_sec = 1.0

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=sleep_sec)
            except asyncio.TimeoutError:
                pass

    async def _probe_one(self, component_id: str) -> None:
        """对单个 ACTIVE_PROBE 模式组件调用探针。

        超时或异常计一次健康失败，连续失败达阈值时触发故障回调。
        """
        snapshot = self._registry.get(component_id)
        if snapshot is None:
            return

        # 跳过非运行态组件（spec.md 5.2.1 规则 6）
        if snapshot.state in (
            ServiceState.STOPPED,
            ServiceState.STOPPING,
            ServiceState.UNMANAGED,
            ServiceState.FAULT_MANUAL,
        ):
            return

        probe_fn = self._probe_functions.get(component_id)
        if probe_fn is None:
            return

        try:
            result = await asyncio.wait_for(
                probe_fn(), timeout=self._probe_timeout
            )
            if result.alive:
                self._consecutive_failures.pop(component_id, None)
            else:
                await self._on_check_fail(
                    component_id,
                    FaultReason.HEALTH_CHECK_CONSECUTIVE_FAIL,
                    f"探针返回不可用: {result.detail}",
                )
        except asyncio.TimeoutError:
            await self._on_check_fail(
                component_id,
                FaultReason.PROBE_EXCEPTION,
                f"探针超时({self._probe_timeout}s)",
            )
        except Exception as e:
            from src.core.tainted_mask.mark import mark_exception_swallowed
            mark_exception_swallowed()
            await self._on_check_fail(
                component_id,
                FaultReason.PROBE_EXCEPTION,
                f"探针异常: {e}",
            )

    async def _on_check_fail(
        self, component_id: str, reason: FaultReason, detail: str
    ) -> None:
        """记录一次健康检查失败，达阈值时触发故障回调并重置计数。"""
        count = self._consecutive_failures.get(component_id, 0) + 1
        self._consecutive_failures[component_id] = count

        if count >= self._fail_threshold:
            self._consecutive_failures.pop(component_id, None)
            await self._fault_callback(component_id, reason, detail)

    def report_heartbeat(self, component_id: str, timestamp: float) -> None:
        """更新组件最近心跳时间戳。

        时间戳回跳或重复时忽略并记录警告（spec.md 5.2.3 异常场景 2）。
        """
        last = self._last_heartbeats.get(component_id)
        if last is not None and timestamp <= last:
            logger.warning(
                "组件 %s 心跳时间戳回跳或重复 (last=%.3f, recv=%.3f)，已忽略",
                component_id,
                last,
                timestamp,
            )
            return
        self._last_heartbeats[component_id] = timestamp

    async def _check_heartbeat_timeout(self) -> None:
        """检查 PASSIVE_HEARTBEAT 组件心跳超时，触发主动探测确认。

        spec.md 5.2.1 规则 4：2 × check_interval_sec 未收到心跳则触发一次主动探测。
        """
        now = time.monotonic()
        for cid, snapshot in list(self._registry.items()):
            desc = self._descriptors.get(cid)
            if desc is None:
                continue
            if desc.health_mode != HealthCheckMode.PASSIVE_HEARTBEAT:
                continue
            if snapshot.state in (
                ServiceState.STOPPED,
                ServiceState.STOPPING,
                ServiceState.UNMANAGED,
                ServiceState.FAULT_MANUAL,
            ):
                continue

            last_hb = self._last_heartbeats.get(cid)
            if last_hb is None:
                # 从未收到心跳，检查是否超过 2 倍间隔
                continue

            if now - last_hb > 2 * desc.check_interval_sec:
                logger.warning("组件 %s 心跳超时，触发主动探测确认", cid)
                await self._probe_one(cid)
                self._last_heartbeats[cid] = time.monotonic()
