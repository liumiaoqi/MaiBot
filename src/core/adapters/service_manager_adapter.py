"""服务管理器适配器 — 实现 ServiceManagerPort，组装 5 引擎 + 依赖图。

适配器层，唯一允许导入组件具体类的地方。将引擎组装为完整服务管理器。
"""


import asyncio
import time
from collections import deque
from dataclasses import replace
from typing import Awaitable, Callable, Optional

from src.core.service_manager.dependency_graph import DependencyGraph
from src.core.service_manager.exceptions import DependencyCycleError
from src.core.service_manager.health_check import HealthCheckEngine
from src.core.service_manager.lifecycle import ComponentActions, LifecycleManager
from src.core.service_manager.recovery import RecoveryEngine
from src.core.service_manager.state_aggregator import StateAggregator
from src.core.service_manager.types import (
    AdoptionResult,
    DependencyRelation,
    FaultReason,
    FaultRecord,
    HealthCheckResult,
    LifecycleActionResult,
    ServiceDescriptor,
    ServiceState,
    ServiceStateSnapshot,
    SystemHealthView,
)
from src.core.startup.types import ComponentStatus, StartupResult

from src.common.logger import get_logger

logger = get_logger(__name__)


class ServiceManagerAdapter:
    """服务管理器适配器 — 实现 ServiceManagerPort。

    组装 DependencyGraph + StateAggregator + RecoveryEngine + HealthCheckEngine + LifecycleManager，
    提供组件生命周期控制、状态查询、健康视图、故障恢复的完整服务管理。
    """

    def __init__(
        self,
        probe_functions: Optional[
            dict[str, Callable[[], Awaitable[HealthCheckResult]]]
        ] = None,
        component_actions: Optional[dict[str, ComponentActions]] = None,
        oom_hook: Optional[Callable[[str], Awaitable[None]]] = None,
        lifecycle_state_getter: Optional[Callable[[], bool]] = None,
    ) -> None:
        # 数据结构
        self._registry: dict[str, ServiceStateSnapshot] = {}
        self._descriptors: dict[str, ServiceDescriptor] = {}
        self._fault_history: dict[str, deque[FaultRecord]] = {}
        self._graph = DependencyGraph()

        # 组件回调
        self._probe_functions = probe_functions or {}
        self._component_actions = component_actions or {}
        self._oom_hook = oom_hook
        # ZG-6 衔接 5：系统关闭谓词（true=关闭中，恢复引擎跳过自动拉起）
        self._is_shutting_down = lifecycle_state_getter or (lambda: False)

        # 引擎（adopt 后创建）
        self._state_aggregator: Optional[StateAggregator] = None
        self._recovery_engine = RecoveryEngine()
        self._health_check_engine: Optional[HealthCheckEngine] = None
        self._lifecycle_manager: Optional[LifecycleManager] = None

        # 后台任务
        self._health_check_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._recovery_tasks: dict[str, asyncio.Task] = {}

        # 状态
        self._adopted = False

    def register_probe(self, component_id: str, probe_fn: Callable[[], Awaitable[HealthCheckResult]]) -> None:
        """运行时注册健康探针（T19 ZG-8：control_message 在接管后实例化，需动态注册）。

        HealthCheckEngine 持有同一 probe_functions dict 引用，注册后下轮健康检查即生效。
        """
        self._probe_functions[component_id] = probe_fn

    def _ensure_adopted(self) -> None:
        """检查是否已完成接管。"""
        if not self._adopted:
            raise RuntimeError("服务管理器尚未接管组件，请先调用 adopt_from_startup")

    def _update_state(
        self, component_id: str, new_state: ServiceState, **changes: object
    ) -> None:
        """更新组件状态（创建新 frozen 快照替换旧快照）。"""
        old = self._registry.get(component_id)
        if old is None:
            return
        self._registry[component_id] = replace(old, state=new_state, **changes)

    def _record_fault(
        self, component_id: str, reason: FaultReason, detail: str
    ) -> None:
        """记录故障到环形缓冲。"""
        history = self._fault_history.setdefault(
            component_id, deque(maxlen=100)
        )
        history.append(
            FaultRecord(
                component_id=component_id,
                fault_time=time.monotonic(),
                reason=reason,
                detail=detail,
            )
        )

    def _notify_level_change(self) -> None:
        """计算等级变更并推送通知。"""
        if self._state_aggregator is None:
            return
        # 由于无法在此处获取 old_level，调用方应在更新前获取
        # 此方法仅用于无通知场景的占位
        pass

    # ============================================================
    # ServiceManagerPort 实现
    # ============================================================

    async def adopt_from_startup(
        self,
        result: StartupResult,
        descriptors: list[ServiceDescriptor],
        dependencies: tuple[DependencyRelation, ...] = (),
    ) -> AdoptionResult:
        """从 StartupOrchestrator 结果接管组件。

        1. 遍历 result.phases 中 status=SUCCESS 的组件，按 descriptors 匹配创建快照
        2. 构建 DependencyGraph，检测环
        3. 识别悬空依赖
        4. 创建引擎实例，启动健康检查循环
        """
        # 填充描述符表
        for desc in descriptors:
            self._descriptors[desc.identifier] = desc

        # 构建核心就绪映射
        core_readiness_map: dict[str, str] = {}
        for desc in descriptors:
            if desc.core_readiness_flag:
                core_readiness_map[desc.identifier] = desc.core_readiness_flag
        core_readiness_components = set(core_readiness_map.keys())

        # 从 StartupResult 接管 SUCCESS 组件
        total_components = 0
        adopted_count = 0
        for phase_result in result.phases.values():
            for component in phase_result.components:
                total_components += 1
                if component.status == ComponentStatus.SUCCESS:
                    desc = self._descriptors.get(component.name)
                    if desc is not None:
                        self._registry[component.name] = ServiceStateSnapshot(
                            identifier=component.name,
                            display_name=desc.display_name,
                            state=ServiceState.RUNNING,
                            health_mode=desc.health_mode,
                        )
                        adopted_count += 1

        skipped_count = total_components - adopted_count

        # 构建依赖图
        for dep in dependencies:
            self._graph.add_relation(dep)

        cycle = self._graph.detect_cycle()
        if cycle is not None:
            raise DependencyCycleError(f"依赖声明形成环: {cycle}", cycle)

        # 识别悬空依赖
        dangling: list[str] = []
        for dep in dependencies:
            if dep.dependency not in self._registry:
                dangling.append(dep.dependency)
        dangling = list(set(dangling))

        # 创建引擎
        self._state_aggregator = StateAggregator(
            self._registry, core_readiness_map
        )
        self._lifecycle_manager = LifecycleManager(
            self._registry,
            self._descriptors,
            self._graph,
            self._component_actions,
            core_readiness_components,
        )
        self._health_check_engine = HealthCheckEngine(
            self._registry,
            self._descriptors,
            self._probe_functions,
            self._on_fault,
        )

        # 启动健康检查循环
        self._stop_event.clear()
        self._health_check_task = asyncio.create_task(
            self._health_check_engine.run_loop(self._stop_event)
        )

        self._adopted = True
        logger.info(
            "服务管理器已接管 %d 个组件（跳过 %d，悬空依赖 %d）",
            adopted_count,
            skipped_count,
            len(dangling),
        )

        return AdoptionResult(
            adopted_count=adopted_count,
            skipped_count=skipped_count,
            dangling_dependencies=dangling,
        )

    async def stop(
        self,
        component_id: str,
        *,
        force: bool = False,
        confirmed: bool = False,
    ) -> LifecycleActionResult:
        """停止组件（委托 LifecycleManager，通知等级变更）。"""
        self._ensure_adopted()
        assert self._state_aggregator is not None
        assert self._lifecycle_manager is not None

        old_level = self._state_aggregator.compute_level()
        result = await self._lifecycle_manager.stop(
            component_id, force=force, confirmed=confirmed
        )
        new_level = self._state_aggregator.compute_level()
        self._state_aggregator.check_and_notify(old_level, new_level)
        return result

    async def start(self, component_id: str) -> LifecycleActionResult:
        """启动组件（委托 LifecycleManager，通知等级变更）。"""
        self._ensure_adopted()
        assert self._state_aggregator is not None
        assert self._lifecycle_manager is not None

        old_level = self._state_aggregator.compute_level()
        result = await self._lifecycle_manager.start(component_id)
        new_level = self._state_aggregator.compute_level()
        self._state_aggregator.check_and_notify(old_level, new_level)
        return result

    async def restart(
        self, component_id: str, *, confirmed: bool = False
    ) -> LifecycleActionResult:
        """重启组件（委托 LifecycleManager，通知等级变更）。"""
        self._ensure_adopted()
        assert self._state_aggregator is not None
        assert self._lifecycle_manager is not None

        old_level = self._state_aggregator.compute_level()
        result = await self._lifecycle_manager.restart(
            component_id, confirmed=confirmed
        )
        new_level = self._state_aggregator.compute_level()
        self._state_aggregator.check_and_notify(old_level, new_level)
        return result

    def get_state(self, component_id: str) -> Optional[ServiceStateSnapshot]:
        """查询单个组件状态（内存，≤100ms）。"""
        return self._registry.get(component_id)

    def list_states(
        self, *, filter_state: Optional[ServiceState] = None
    ) -> list[ServiceStateSnapshot]:
        """查询全部组件状态，可按状态过滤。"""
        if filter_state is None:
            return list(self._registry.values())
        return [
            snap for snap in self._registry.values() if snap.state == filter_state
        ]

    def get_system_health_view(self) -> SystemHealthView:
        """查询系统健康视图（内存聚合，≤100ms，无 I/O）。"""
        self._ensure_adopted()
        assert self._state_aggregator is not None
        return self._state_aggregator.build_view()

    def get_state_aggregator(self) -> Optional[StateAggregator]:
        """返回状态聚合引擎（ZG-6 生命周期适配器衔接用）。"""
        return self._state_aggregator

    def get_fault_history(
        self, component_id: str, *, limit: int = 100
    ) -> list[FaultRecord]:
        """查询组件故障历史（环形缓冲，最近 limit 条）。"""
        history = self._fault_history.get(component_id)
        if history is None:
            return []
        return list(history)[-limit:]

    async def report_heartbeat(self, component_id: str, timestamp: float) -> None:
        """接收组件心跳上报（委托 HealthCheckEngine）。"""
        if self._health_check_engine is not None:
            self._health_check_engine.report_heartbeat(component_id, timestamp)

    async def report_external_fault(
        self, component_id: str, reason: str, detail: str = ""
    ) -> None:
        """接收外部故障事件 — 转故障 + 记录 + 触发恢复。"""
        self._ensure_adopted()
        assert self._state_aggregator is not None

        old_level = self._state_aggregator.compute_level()
        self._update_state(component_id, ServiceState.FAULT)
        self._record_fault(component_id, FaultReason.EXTERNAL_EVENT, detail)
        new_level = self._state_aggregator.compute_level()
        self._state_aggregator.check_and_notify(old_level, new_level)

        # 触发恢复（后台任务）
        if component_id not in self._recovery_tasks:
            task = asyncio.create_task(self._do_recover(component_id))
            self._recovery_tasks[component_id] = task

    def subscribe_health_change(
        self, callback: Callable[[SystemHealthView], None]
    ) -> None:
        """订阅系统健康等级变更事件。"""
        if self._state_aggregator is not None:
            self._state_aggregator.subscribe(callback)

    def unsubscribe_health_change(
        self, callback: Callable[[SystemHealthView], None]
    ) -> None:
        """取消订阅。"""
        if self._state_aggregator is not None:
            self._state_aggregator.unsubscribe(callback)

    async def shutdown(self) -> None:
        """停止健康检查循环，取消所有后台任务。"""
        self._stop_event.set()

        if self._health_check_task is not None:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
            self._health_check_task = None

        for task in list(self._recovery_tasks.values()):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._recovery_tasks.clear()

        logger.info("服务管理器已关闭")

    # ============================================================
    # 内部回调
    # ============================================================

    async def _on_fault(
        self, component_id: str, reason: FaultReason, detail: str
    ) -> None:
        """健康检查故障回调 — 转故障 + 记录 + 触发恢复。

        恢复以后台任务启动，不阻塞健康检查循环。
        """
        assert self._state_aggregator is not None

        old_level = self._state_aggregator.compute_level()
        self._update_state(component_id, ServiceState.FAULT)
        self._record_fault(component_id, reason, detail)
        new_level = self._state_aggregator.compute_level()
        self._state_aggregator.check_and_notify(old_level, new_level)

        # 触发恢复（后台任务）
        if component_id not in self._recovery_tasks:
            task = asyncio.create_task(self._do_recover(component_id))
            self._recovery_tasks[component_id] = task

    async def _do_recover(self, component_id: str) -> None:
        """执行恢复流程（后台任务）。"""
        assert self._state_aggregator is not None
        assert self._lifecycle_manager is not None

        # ZG-6 衔接 5：系统关闭中不自动恢复组件（避免关闭过程被恢复拉起）
        if self._is_shutting_down():
            logger.info(f"系统关闭中，跳过组件 {component_id} 的自动恢复")
            return

        try:
            descriptor = self._descriptors.get(component_id)
            success = await self._recovery_engine.recover(
                component_id,
                self._lifecycle_manager,
                descriptor,
                self._oom_hook,
            )

            old_level = self._state_aggregator.compute_level()
            if not success:
                # 风暴保护，转 FAULT_MANUAL
                self._update_state(component_id, ServiceState.FAULT_MANUAL)
            else:
                # 恢复成功，重置退避计数
                self._recovery_engine.reset_count(component_id)
            new_level = self._state_aggregator.compute_level()
            self._state_aggregator.check_and_notify(old_level, new_level)
        except Exception:
            from src.core.tainted_mask.mark import mark_exception_swallowed
            mark_exception_swallowed()
            logger.error(
                "组件 %s 恢复流程异常，转入故障(需人工)",
                component_id,
                exc_info=True,
            )
            old_level = self._state_aggregator.compute_level()
            self._update_state(component_id, ServiceState.FAULT_MANUAL)
            new_level = self._state_aggregator.compute_level()
            self._state_aggregator.check_and_notify(old_level, new_level)
        finally:
            self._recovery_tasks.pop(component_id, None)
