"""状态聚合引擎 — 纯内存聚合，≤100ms，无 I/O。

计算系统健康等级并推送变更事件。
"""


import time
from typing import Callable

from src.core.service_manager.types import (
    ServiceState,
    ServiceStateSnapshot,
    SystemHealthLevel,
    SystemHealthView,
)

from src.common.logger import get_logger

logger = get_logger(__name__)


class StateAggregator:
    """状态聚合引擎 — 计算系统健康四等级，推送等级变更事件。

    内部维护：
    - _registry: 组件注册表引用（外部拥有，本类只读 + 聚合）
    - _core_readiness_map: component_id → core_readiness_flag 映射
    - _subscribers: 健康等级变更回调列表
    """

    def __init__(
        self,
        component_registry: dict[str, ServiceStateSnapshot],
        core_readiness_map: dict[str, str],
    ) -> None:
        self._registry = component_registry
        self._core_readiness_map = core_readiness_map
        self._subscribers: list[Callable[[SystemHealthView], None]] = []

    def compute_level(self) -> SystemHealthLevel:
        """按 spec.md 5.5.1 规则计算系统健康四等级。

        优先级：
        1. 存在 RESTARTING 状态组件 → RECOVERING
        2. 核心就绪贡献组件任一非 RUNNING → FAULT
        3. 存在 DEGRADED 或非核心的 FAULT 组件 → DEGRADED
        4. 全部 RUNNING → HEALTHY
        """
        has_restarting = False
        has_core_fault = False
        has_degraded_or_non_core_fault = False

        for snapshot in self._registry.values():
            if snapshot.state == ServiceState.RESTARTING:
                has_restarting = True
            elif snapshot.identifier in self._core_readiness_map:
                # 核心就绪贡献组件：任一非 RUNNING → FAULT
                if snapshot.state != ServiceState.RUNNING:
                    has_core_fault = True
            elif snapshot.state in (
                ServiceState.FAULT,
                ServiceState.FAULT_MANUAL,
                ServiceState.DEGRADED,
            ):
                has_degraded_or_non_core_fault = True

        if has_restarting:
            return SystemHealthLevel.RECOVERING
        if has_core_fault:
            return SystemHealthLevel.FAULT
        if has_degraded_or_non_core_fault:
            return SystemHealthLevel.DEGRADED
        return SystemHealthLevel.HEALTHY

    def compute_core_readiness(self) -> tuple[bool, bool, bool]:
        """根据核心就绪贡献组件状态重算三标志。

        Returns:
            (message_pipeline_ready, agent_thinking_ready, reply_capability_ready)
        """
        flags: dict[str, bool] = {
            "message_pipeline_ready": False,
            "agent_thinking_ready": False,
            "reply_capability_ready": False,
        }

        for component_id, flag_name in self._core_readiness_map.items():
            snapshot = self._registry.get(component_id)
            if snapshot is not None and snapshot.state == ServiceState.RUNNING:
                flags[flag_name] = True

        return (
            flags["message_pipeline_ready"],
            flags["agent_thinking_ready"],
            flags["reply_capability_ready"],
        )

    def build_view(self) -> SystemHealthView:
        """聚合全部组件快照 + 等级 + 核心就绪三标志 + 降级组件清单 + 生成时间戳。"""
        level = self.compute_level()
        msg_ready, agent_ready, reply_ready = self.compute_core_readiness()
        core_ready = msg_ready and agent_ready and reply_ready

        degraded_components = [
            snap.identifier
            for snap in self._registry.values()
            if snap.state
            in (
                ServiceState.DEGRADED,
                ServiceState.FAULT,
                ServiceState.FAULT_MANUAL,
            )
        ]

        return SystemHealthView(
            level=level,
            core_ready=core_ready,
            message_pipeline_ready=msg_ready,
            agent_thinking_ready=agent_ready,
            reply_capability_ready=reply_ready,
            component_states=list(self._registry.values()),
            degraded_components=degraded_components,
            generated_at=time.monotonic(),
        )

    def check_and_notify(
        self, old_level: SystemHealthLevel, new_level: SystemHealthLevel
    ) -> None:
        """等级变更时遍历订阅回调列表推送 SystemHealthView。

        订阅方异常时捕获并记录警告（spec.md 5.5.3 异常场景 2）。
        """
        if old_level == new_level:
            return

        view = self.build_view()
        for callback in self._subscribers:
            try:
                callback(view)
            except Exception as exc:
                from src.core.error_escalation.types import ErrorLevel
                from src.core.error_escalation_port_registry import get_error_escalation_port
                port = get_error_escalation_port()
                if port is not None:
                    port.report(ErrorLevel.WARNING, "健康等级变更订阅回调异常", exception=exc)
                from src.core.tainted_mask.mark import mark_exception_swallowed
                mark_exception_swallowed()
                logger.warning("健康等级变更订阅回调异常，已跳过", exc_info=True)

    def subscribe(self, callback: Callable[[SystemHealthView], None]) -> None:
        """注册健康等级变更回调。"""
        if callback not in self._subscribers:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[SystemHealthView], None]) -> None:
        """取消注册健康等级变更回调。"""
        if callback in self._subscribers:
            self._subscribers.remove(callback)
