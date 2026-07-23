"""启动协调器 — 按阶段顺序执行组件初始化。"""

from __future__ import annotations

import asyncio
import time


from src.common.logger import get_logger
from src.core.startup.types import (
    ComponentStatus,
    CoreReadiness,
    PhaseResult,
    StartupComponent,
    StartupPhase,
    StartupResult,
)

logger = get_logger("core.startup.orchestrator")

# 阶段3 子系统单个组件超时（秒）
_SUBSYSTEM_TIMEOUT = 60.0

_PHASE_NAMES: dict[StartupPhase, str] = {
    StartupPhase.CONFIG_LOAD: "配置加载",
    StartupPhase.INFRASTRUCTURE: "基础设施",
    StartupPhase.CORE_SERVICES: "核心服务构造",
    StartupPhase.SUBSYSTEMS: "子系统启动",
    StartupPhase.SESSION_RESTORE: "会话恢复",
    StartupPhase.READY: "就绪",
}


class StartupOrchestrator:
    """启动流程的唯一编排入口。

    开发者通过 register() 声明组件，run() 按阶段顺序执行。
    """

    def __init__(self) -> None:
        self._components: list[StartupComponent] = []
        self._phase_results: dict[StartupPhase, PhaseResult] = {}
        self._core_readiness = CoreReadiness()
        self._subsystem_status: dict[str, ComponentStatus] = {}
        self._start_time: float = 0.0
        self._core_ready_time: float = 0.0

    def register(self, component: StartupComponent) -> None:
        """注册组件。

        Raises:
            ValueError: 组件名重复 或 phase+order 冲突
        """
        for existing in self._components:
            if existing.name == component.name:
                raise ValueError(f"组件名重复: {component.name}")
            if existing.phase == component.phase and existing.order == component.order:
                raise ValueError(
                    f"组件 {component.name} 与 {existing.name} "
                    f"在阶段 {component.phase.name} 序号 {component.order} 冲突"
                )
        self._components.append(component)

    async def run(self) -> StartupResult:
        """按 StartupPhase 枚举顺序执行全部 6 个阶段。"""
        self._start_time = time.monotonic()

        for phase in sorted(StartupPhase, key=lambda p: p.value):
            result = await self._run_phase(phase)
            self._phase_results[phase] = result
            if result.status == ComponentStatus.FAILED and phase != StartupPhase.SUBSYSTEMS:
                logger.error(f"启动中止: 阶段 {phase.name} 失败")
                break
            if phase == StartupPhase.CORE_SERVICES:
                self._update_core_readiness(result)

        total_ms = int((time.monotonic() - self._start_time) * 1000)
        failed = [c for c in self._components if c.status == ComponentStatus.FAILED]
        degraded = [c for c in self._components if c.status == ComponentStatus.FAILED and not c.critical]

        core_ready_ms = 0
        if self._core_readiness.core_ready and self._core_ready_time > 0:
            core_ready_ms = int((self._core_ready_time - self._start_time) * 1000)

        result = StartupResult(
            total_duration_ms=total_ms,
            phases=self._phase_results,
            failed_components=failed,
            degraded_components=degraded,
            ready=len(failed) == 0,
            core_ready=self._core_readiness.core_ready,
            core_ready_time_ms=core_ready_ms,
            subsystem_status=self._subsystem_status,
        )
        self._emit_startup_summary(result)
        return result

    def _emit_startup_summary(self, result: StartupResult) -> None:
        degraded_names = [c.name for c in result.degraded_components]
        lines = [
            f"[启动摘要] 总耗时={result.total_duration_ms}ms | 核心就绪={result.core_ready_time_ms}ms",
        ]
        for phase in sorted(StartupPhase, key=lambda p: p.value):
            pr = result.phases.get(phase)
            if pr is None:
                continue
            status = "✓" if pr.status == ComponentStatus.SUCCESS else "✗"
            phase_name = _PHASE_NAMES.get(phase, phase.name)
            async_mark = " (异步)" if phase == StartupPhase.SUBSYSTEMS else ""
            lines.append(f"  阶段{phase.value} {phase_name}: {pr.duration_ms}ms {status}{async_mark}")
            for c in pr.components:
                c_status = "✓" if c.status == ComponentStatus.SUCCESS else "✗"
                duration_str = "已发起" if phase == StartupPhase.SUBSYSTEMS else f"{c.duration_ms}ms"
                lines.append(f"    {c.name}: {duration_str} {c_status}")
        if degraded_names:
            lines.append(f"  降级组件: {', '.join(degraded_names)}")
        logger.info("\n".join(lines))

    def get_core_readiness(self) -> CoreReadiness:
        return self._core_readiness

    def get_subsystem_status(self, name: str) -> ComponentStatus:
        return self._subsystem_status.get(name, ComponentStatus.PENDING)

    async def _run_phase(self, phase: StartupPhase) -> PhaseResult:
        start = time.monotonic()
        phase_name = _PHASE_NAMES.get(phase, phase.name)
        components = sorted(
            [c for c in self._components if c.phase == phase],
            key=lambda c: c.order,
        )

        if not components:
            return PhaseResult(
                phase=phase,
                status=ComponentStatus.SUCCESS,
                start_time=start,
                end_time=start,
                duration_ms=0,
                components=[],
            )

        logger.info(f"[启动] 阶段{phase.value}: {phase_name} 状态=进行中（{len(components)} 个组件）")

        if not self._check_phase_entry(phase):
            raise RuntimeError(f"阶段 {phase.name} 未满足准入条件——前一阶段关键组件未全部成功")

        if phase == StartupPhase.SUBSYSTEMS:
            await self._run_subsystems_parallel(components)
        else:
            for component in components:
                await self._run_component(component)

        end = time.monotonic()
        duration_ms = int((end - start) * 1000)
        status = ComponentStatus.SUCCESS if all(
            c.status == ComponentStatus.SUCCESS for c in components
        ) else ComponentStatus.FAILED

        if status == ComponentStatus.SUCCESS:
            logger.info(f"[启动] 阶段{phase.value}: {phase_name} 状态=成功 耗时={duration_ms}ms")
        else:
            logger.error(f"[启动] 阶段{phase.value}: {phase_name} 状态=失败 耗时={duration_ms}ms")

        return PhaseResult(
            phase=phase,
            status=status,
            start_time=start,
            end_time=end,
            duration_ms=duration_ms,
            components=components,
        )

    async def _run_component(self, component: StartupComponent) -> None:
        component.status = ComponentStatus.IN_PROGRESS
        component.start_time = time.monotonic()
        try:
            await component.init_fn()
            component.status = ComponentStatus.SUCCESS
        except Exception as exc:
            component.status = ComponentStatus.FAILED
            component.error = exc
            logger.error(f"[{component.name}] 初始化失败: {exc}", exc_info=True)
            if component.critical:
                raise
            self._subsystem_status[component.name] = ComponentStatus.FAILED
        finally:
            component.end_time = time.monotonic()
            component.duration_ms = int((component.end_time - component.start_time) * 1000)

    async def _run_subsystems_parallel(self, components: list[StartupComponent]) -> None:
        tasks: list[asyncio.Task] = []
        for component in components:
            task = asyncio.create_task(
                self._run_component_safe(component),
                name=f"startup:{component.name}",
            )
            tasks.append(task)

        for task in tasks:
            try:
                await asyncio.wait_for(task, timeout=_SUBSYSTEM_TIMEOUT)
            except asyncio.TimeoutError:
                logger.warning(f"子系统启动超时: {task.get_name()}")

    async def _run_component_safe(self, component: StartupComponent) -> None:
        """执行单个组件——无论成败都不传播异常。"""
        component.status = ComponentStatus.IN_PROGRESS
        component.start_time = time.monotonic()
        try:
            await component.init_fn()
            component.status = ComponentStatus.SUCCESS
        except asyncio.TimeoutError:
            component.status = ComponentStatus.FAILED
            component.error = f"超时 {_SUBSYSTEM_TIMEOUT}s"
            logger.warning(f"[{component.name}] 子系统启动超时")
            self._subsystem_status[component.name] = ComponentStatus.FAILED
        except Exception as exc:
            component.status = ComponentStatus.FAILED
            component.error = exc
            logger.warning(f"[{component.name}] 子系统初始化失败（降级继续）: {exc}")
            self._subsystem_status[component.name] = ComponentStatus.FAILED
        finally:
            component.end_time = time.monotonic()
            component.duration_ms = int((component.end_time - component.start_time) * 1000)

    def _check_phase_entry(self, phase: StartupPhase) -> bool:
        """检查前一阶段所有关键组件是否全部成功。"""
        if phase == StartupPhase.CONFIG_LOAD:
            return True
        prev = StartupPhase(phase.value - 1)
        prev_components = [c for c in self._components if c.phase == prev]
        for c in prev_components:
            if c.critical and c.status != ComponentStatus.SUCCESS:
                return False
        return True

    def _update_core_readiness(self, result: PhaseResult) -> None:
        """阶段 2 完成后根据指定组件更新核心就绪状态。"""
        for c in result.components:
            if c.name == "session_port_registry" and c.status == ComponentStatus.SUCCESS:
                self._core_readiness.message_pipeline_ready = True
            elif c.name == "agent_registry" and c.status == ComponentStatus.SUCCESS:
                self._core_readiness.agent_thinking_ready = True
            elif c.name == "replyer_port" and c.status == ComponentStatus.SUCCESS:
                self._core_readiness.reply_capability_ready = True
        if self._core_readiness.core_ready and self._core_ready_time == 0.0:
            self._core_ready_time = time.monotonic()
