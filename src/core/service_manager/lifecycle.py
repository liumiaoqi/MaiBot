"""生命周期管理引擎 — 执行 start/stop/restart，强制级联顺序与依赖就绪校验。

核心编排逻辑。
"""


import asyncio
from dataclasses import dataclass, replace
from typing import Awaitable, Callable

from src.core.service_manager.dependency_graph import DependencyGraph
from src.core.service_manager.exceptions import (
    ConfirmationRequiredError,
    DependencyNotReadyError,
    RestartInProgressError,
    UnknownComponentError,
)
from src.core.service_manager.types import (
    DependencyKind,
    LifecycleActionResult,
    ServiceDescriptor,
    ServiceState,
    ServiceStateSnapshot,
)

from src.common.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ComponentActions:
    """组件生命周期动作回调。"""

    stop_fn: Callable[[], Awaitable[None]]
    start_fn: Callable[[], Awaitable[None]]


class LifecycleManager:
    """生命周期管理引擎 — 执行 start/stop/restart，强制级联顺序与依赖就绪校验。

    内部维护：
    - _registry: 组件注册表引用（读写，状态变更时创建新 frozen 快照）
    - _descriptors: 组件描述符表引用（只读）
    - _graph: DependencyGraph 引用（只读）
    - _actions: component_id → ComponentActions（stop/start 回调）
    - _core_readiness_components: 核心就绪贡献组件 ID 集合
    - _stop_timeout: 单组件停止超时（秒）
    """

    def __init__(
        self,
        component_registry: dict[str, ServiceStateSnapshot],
        descriptors: dict[str, ServiceDescriptor],
        dependency_graph: DependencyGraph,
        actions: dict[str, ComponentActions],
        core_readiness_components: set[str],
        stop_timeout_sec: float = 30.0,
    ) -> None:
        self._registry = component_registry
        self._descriptors = descriptors
        self._graph = dependency_graph
        self._actions = actions
        self._core_readiness_components = core_readiness_components
        self._stop_timeout = stop_timeout_sec

    def _update_state(
        self, component_id: str, new_state: ServiceState, **changes: object
    ) -> None:
        """更新组件状态（创建新 frozen 快照替换旧快照）。"""
        old = self._registry.get(component_id)
        if old is None:
            return
        self._registry[component_id] = replace(old, state=new_state, **changes)

    async def stop(
        self,
        component_id: str,
        *,
        force: bool = False,
        confirmed: bool = False,
    ) -> LifecycleActionResult:
        """停止组件（级联停止强依赖方，弱依赖方降级）。

        Args:
            component_id: 目标组件 ID
            force: 强制停止（跳过确认检查，恢复引擎内部调用用）
            confirmed: 核心就绪贡献组件的二次确认

        Raises:
            UnknownComponentError: 组件未纳入管理
            RestartInProgressError: 组件处于重启中
            ConfirmationRequiredError: 核心组件未确认
        """
        snapshot = self._registry.get(component_id)
        if snapshot is None:
            raise UnknownComponentError(f"组件未纳入管理: {component_id}")

        if snapshot.state == ServiceState.RESTARTING:
            raise RestartInProgressError(f"组件处于重启中: {component_id}")

        if (
            component_id in self._core_readiness_components
            and not confirmed
            and not force
        ):
            raise ConfirmationRequiredError(
                f"核心就绪贡献组件需二次确认: {component_id}"
            )

        strong_stop, weak_degrade = self._graph.cascade_stop_order(component_id)
        cascaded = bool(strong_stop or weak_degrade)

        # 级联停止强依赖方（按拓扑序逆序，依赖方先停）
        for cid in strong_stop:
            if cid not in self._registry:
                continue
            self._update_state(cid, ServiceState.STOPPING)
            actions = self._actions.get(cid)
            if actions is not None:
                try:
                    await asyncio.wait_for(
                        actions.stop_fn(), timeout=self._stop_timeout
                    )
                    self._update_state(cid, ServiceState.STOPPED)
                except asyncio.TimeoutError:
                    logger.warning("组件 %s 级联停止超时，标记故障", cid)
                    self._update_state(cid, ServiceState.FAULT)
                except Exception:
                    from src.core.tainted_mask.mark import mark_exception_swallowed
                    mark_exception_swallowed()
                    logger.warning(
                        "组件 %s 级联停止异常，继续停止剩余", cid, exc_info=True
                    )
                    self._update_state(cid, ServiceState.FAULT)
            else:
                self._update_state(cid, ServiceState.STOPPED)

        # 停止目标组件
        self._update_state(component_id, ServiceState.STOPPING)
        actions = self._actions.get(component_id)
        if actions is not None:
            try:
                await asyncio.wait_for(
                    actions.stop_fn(), timeout=self._stop_timeout
                )
                self._update_state(component_id, ServiceState.STOPPED)
            except asyncio.TimeoutError:
                logger.warning("组件 %s 停止超时，标记故障", component_id)
                self._update_state(component_id, ServiceState.FAULT)
                return LifecycleActionResult(
                    success=False,
                    component_id=component_id,
                    new_state=ServiceState.FAULT,
                    cascaded=cascaded,
                    error="停止超时",
                )
            except Exception as e:
                from src.core.tainted_mask.mark import mark_exception_swallowed
                mark_exception_swallowed()
                logger.warning("组件 %s 停止异常", component_id, exc_info=True)
                self._update_state(component_id, ServiceState.FAULT)
                return LifecycleActionResult(
                    success=False,
                    component_id=component_id,
                    new_state=ServiceState.FAULT,
                    cascaded=cascaded,
                    error=str(e),
                )
        else:
            self._update_state(component_id, ServiceState.STOPPED)

        # 弱依赖方降级
        for cid in weak_degrade:
            if cid in self._registry:
                self._update_state(cid, ServiceState.DEGRADED)

        return LifecycleActionResult(
            success=True,
            component_id=component_id,
            new_state=ServiceState.STOPPED,
            cascaded=cascaded,
        )

    async def start(self, component_id: str) -> LifecycleActionResult:
        """启动组件（校验强依赖就绪，未就绪拒绝）。

        Raises:
            UnknownComponentError: 组件未纳入管理
            DependencyNotReadyError: 强依赖未就绪
        """
        snapshot = self._registry.get(component_id)
        if snapshot is None:
            raise UnknownComponentError(f"组件未纳入管理: {component_id}")

        # 校验强依赖就绪
        deps_with_kind = self._graph.dependencies_with_kind(component_id)
        missing: list[str] = []
        has_weak_fault = False

        for dep_id, kind in deps_with_kind.items():
            dep_snap = self._registry.get(dep_id)
            if dep_snap is None or dep_snap.state != ServiceState.RUNNING:
                if kind == DependencyKind.STRONG:
                    missing.append(dep_id)
                else:
                    has_weak_fault = True

        if missing:
            raise DependencyNotReadyError(
                f"强依赖未就绪: {missing}", missing
            )

        self._update_state(component_id, ServiceState.RESTARTING)

        actions = self._actions.get(component_id)
        if actions is not None:
            try:
                await actions.start_fn()
            except Exception as e:
                from src.core.tainted_mask.mark import mark_exception_swallowed
                mark_exception_swallowed()
                logger.warning("组件 %s 启动失败", component_id, exc_info=True)
                self._update_state(component_id, ServiceState.FAULT)
                return LifecycleActionResult(
                    success=False,
                    component_id=component_id,
                    new_state=ServiceState.FAULT,
                    cascaded=False,
                    error=str(e),
                )

        # 启动成功：弱依赖故障 → DEGRADED，否则 RUNNING
        new_state = ServiceState.DEGRADED if has_weak_fault else ServiceState.RUNNING
        self._update_state(component_id, new_state)

        return LifecycleActionResult(
            success=True,
            component_id=component_id,
            new_state=new_state,
            cascaded=False,
        )

    async def restart(
        self, component_id: str, *, confirmed: bool = False
    ) -> LifecycleActionResult:
        """重启组件（停止后启动，总限时 30s）。

        Raises:
            UnknownComponentError: 组件未纳入管理
            RestartInProgressError: 组件已处于重启中
        """
        snapshot = self._registry.get(component_id)
        if snapshot is None:
            raise UnknownComponentError(f"组件未纳入管理: {component_id}")

        if snapshot.state == ServiceState.RESTARTING:
            raise RestartInProgressError(f"组件处于重启中: {component_id}")

        async def _restart_inner() -> LifecycleActionResult:
            await self.stop(component_id, force=True, confirmed=confirmed)
            return await self.start(component_id)

        try:
            return await asyncio.wait_for(
                _restart_inner(), timeout=self._stop_timeout
            )
        except asyncio.TimeoutError:
            self._update_state(component_id, ServiceState.FAULT)
            return LifecycleActionResult(
                success=False,
                component_id=component_id,
                new_state=ServiceState.FAULT,
                cascaded=False,
                error="重启超时",
            )
