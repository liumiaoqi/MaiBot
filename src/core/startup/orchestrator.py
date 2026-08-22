"""启动协调器 — 声明收集 + 拓扑仲裁 + 波次调度执行（ZG-10）。

对标 Linux initcall：相位（等级）决定大体顺序，相位内 Kahn 分波保证
依赖正确性与并行度。核心就绪屏障确保 SESSION_RESTORE/READY 相位在
核心贡献组件全部就绪后才开始。失败传播：STRONG→SKIPPED / WEAK→DEGRADED。
"""

import asyncio
import time

from src.common.logger import get_logger
from src.core.error_escalation.types import ErrorLevel
from src.core.service_manager.dependency_graph import DependencyGraph
from src.core.startup.arbiter import CoreReadinessBarrier, StartupArbiter, WavePlan
from src.core.startup.declaration import StartupItemDesc, _registry
from src.core.startup.propagator import FailurePropagator
from src.core.startup.types import (
    ComponentStatus,
    CoreReadiness,
    PhaseResult,
    StartupItemRuntimeState,
    StartupPhase,
    StartupResult,
)

logger = get_logger("core.startup.orchestrator")

# 子系统单个组件超时（秒，与存量行为一致）
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
    """启动流程的唯一编排入口 — 声明式注册 + 拓扑仲裁 + 波次调度。

    声明来源两种：@startup_item 装饰器（模块导入期收集）+
    编程式 register(StartupItemDesc)。两者统一进入仲裁。
    """

    def __init__(
        self,
        debug_mode: bool = False,
        skip_names: set[str] | None = None,
    ) -> None:
        self._items: dict[str, StartupItemDesc] = {}
        self._runtime_states: dict[str, StartupItemRuntimeState] = {}
        self._phase_results: dict[StartupPhase, PhaseResult] = {}
        self._core_readiness = CoreReadiness()
        self._subsystem_status: dict[str, ComponentStatus] = {}
        self._start_time: float = 0.0
        self._core_ready_time: float = 0.0
        self.debug_mode = debug_mode
        self.skip_names: set[str] = set(skip_names or ())
        self._barrier = CoreReadinessBarrier()
        self._wave_plan: WavePlan | None = None
        self._graph: DependencyGraph | None = None
        self._running = False

    # ── 注册 ─────────────────────────────────────────────────────

    def register(self, item: StartupItemDesc) -> None:
        """注册启动项（编程式入口，与 @startup_item 等价）。

        Args:
            item: StartupItemDesc 启动项声明

        Raises:
            ValueError: 名称重复
            RuntimeError: run() 执行期间注册
        """
        if self._running:
            raise RuntimeError("启动编排已开始执行，禁止注册新组件")
        if item.name in self._items:
            raise ValueError(f"组件名重复: {item.name}")
        self._items[item.name] = item

    def get_core_readiness(self) -> CoreReadiness:
        return self._core_readiness

    def get_subsystem_status(self, name: str) -> ComponentStatus:
        return self._subsystem_status.get(name, ComponentStatus.PENDING)

    def reclaim_after_startup(self) -> None:
        """启动后回收一次性数据（对标 __init 回收）。

        释放 item 声明元数据（含 init_fn 引用——闭包/绑定方法/模块引用可回收）、
        运行时状态与相位结果、仲裁中间结构（依赖图/波次计划/屏障）。
        保留运行期需要的数据：
        - _core_readiness：get_core_readiness() 消费者（CoreReadinessPort）运行期在用；
        - _start_time/_core_ready_time：纯数值，供 get_core_readiness 侧诊断；
        - _subsystem_status：StartupResult.subsystem_status 与它共享同一 dict
          （result 已持有引用，此处清空本对象引用不释放内存，故保留以维持
          get_subsystem_status 可用）。

        StartupResult 持有 phases/wave_info 的独立引用，清空本对象引用
        不影响结果消费方（adopt_from_startup 等）。
        """
        self._items = {}
        self._runtime_states = {}
        self._phase_results = {}
        self._wave_plan = None
        self._graph = None
        self._barrier = CoreReadinessBarrier()

    # ── 主流程 ───────────────────────────────────────────────────

    async def run(self) -> StartupResult:
        """收集声明 → 仲裁 → 逐相位逐波次执行 → 回调 → 冻结 → 摘要。"""
        self._start_time = time.monotonic()
        self._running = True
        _registry._running = True  # P1-4: 运行期禁止装饰器注册

        # 1. 收集声明（装饰器 + 编程式，合并去重）
        for name, desc in _registry.drain().items():
            if name in self._items:
                raise ValueError(f"启动项重复注册（装饰器与编程式同名）: {name}")
            self._items[name] = desc
        if not self._items:
            logger.warning("无启动项声明——启动流程为空")
            self._running = False
            _registry._running = False
            return StartupResult(total_duration_ms=0)

        # P0-3: skip 校验——核心就绪贡献组件不可跳过；未知名称告警
        for name in self.skip_names:
            desc = self._items.get(name)
            if desc is None:
                logger.warning(
                    "--skip-startup-item 包含未注册名称: %s（忽略）", name
                )
                continue
            if desc.core_readiness_flag:
                raise ValueError(
                    f"禁止跳过核心就绪贡献组件: {name}（{desc.core_readiness_flag}）"
                )

        # 2. 仲裁（构建图 + 屏障 + 相位分波 + 环检测）
        arbiter = StartupArbiter()
        self._wave_plan = arbiter.arbitrate(self._items, skip_names=self.skip_names)
        self._graph = arbiter.last_graph
        self._barrier = CoreReadinessBarrier()

        # 3. 运行时状态初始化
        failed: list[str] = []
        degraded: list[str] = []
        skipped: list[str] = []
        failure_chains: dict[str, str] = {}
        self._runtime_states = {
            name: StartupItemRuntimeState(name=name, status=ComponentStatus.PENDING)
            for name in self._items
        }
        propagator = FailurePropagator()
        for name in self.skip_names:
            if name in self._runtime_states:
                self._runtime_states[name].status = ComponentStatus.SKIPPED
                self._runtime_states[name].skip_reason = "命令行跳过"
                skipped.append(name)
                # P0-2: 跳过视为失败——STRONG 依赖方 SKIPPED / WEAK 依赖方 DEGRADED
                if self._graph is not None:
                    prop = propagator.propagate(name, self._graph, {
                        n: s.status for n, s in self._runtime_states.items()
                    })
                    for n, st in prop.state_updates.items():
                        if n == CoreReadinessBarrier.VIRTUAL_NODE_ID:
                            continue
                        self._runtime_states[n].status = st
                        if st == ComponentStatus.SKIPPED:
                            skipped.append(n)
                        elif st == ComponentStatus.DEGRADED:
                            degraded.append(n)
                    failure_chains.update(prop.failure_chains)
        plan = self._wave_plan
        phase_failed = False

        for phase in sorted(StartupPhase, key=lambda p: p.value):
            if phase_failed:
                # 前相位 critical 失败：跳过后续相位全部项
                self._mark_phase_skipped(phase, skipped, "前相位关键组件失败")
                continue
            waves = plan.phases.get(phase)
            if not waves:
                continue
            phase_result = await self._run_phase_waves(
                phase, waves, propagator, failure_chains,
                failed, degraded, skipped,
            )
            self._phase_results[phase] = phase_result
            if phase_result.status == ComponentStatus.FAILED:
                phase_failed = True
            # 核心就绪屏障检查
            if phase == StartupPhase.CORE_SERVICES:
                self._update_core_readiness()

        # 5. 等待异步子系统 settle（对标 async_synchronize_full）
        await self._wait_async_settle()

        # 6. 配置冻结
        self._freeze_config()

        # 7. 启动完成事件
        result = self._build_result(failed, degraded, skipped, failure_chains)
        await self._emit_startup_complete(result)

        # 8. 摘要（依赖 _items/_runtime_states——必须在回收之前）
        self._emit_startup_summary(result)

        # 9. 启动后回收一次性数据（对标 __init 回收：item 元数据/仲裁中间结构）
        self.reclaim_after_startup()
        self._running = False
        _registry._running = False
        return result

    async def _run_phase_waves(
        self,
        phase: StartupPhase,
        waves: list[list[str]],
        propagator: FailurePropagator,
        failure_chains: dict[str, str],
        failed: list[str],
        degraded: list[str],
        skipped: list[str],
    ) -> PhaseResult:
        """逐波次执行一个相位（波次内并行、波次间串行）。"""
        start = time.monotonic()
        phase_name = _PHASE_NAMES.get(phase, phase.name)
        phase_items = [
            n for wave in waves for n in wave
            if n != CoreReadinessBarrier.VIRTUAL_NODE_ID
        ]
        logger.info(
            f"[启动] 阶段{phase.value}: {phase_name} 状态=进行中"
            f"（{len(phase_items)} 个组件，{len(waves)} 个波次）"
        )

        for wave_index, wave in enumerate(waves):
            items = [n for n in wave if n != CoreReadinessBarrier.VIRTUAL_NODE_ID]
            if not items:
                continue
            if self.debug_mode:
                logger.info(
                    f"[启动] {phase_name} 波次{wave_index}: {', '.join(items)}"
                )
            # 波次内并行（SUBSYSTEMS 保留 safe 包装，其余直接执行）
            if phase == StartupPhase.SUBSYSTEMS:
                await asyncio.gather(
                    *[self._run_item_safe(name, wave_index) for name in items]
                )
            else:
                await asyncio.gather(
                    *[self._run_item(name, wave_index) for name in items]
                )
            # P1-1: critical 失败立即中止当前相位剩余波次（对标旧 _run_component raise）。
            # 传播先于中止（bad 进 failed 列表 + STRONG/WEAK 依赖方标记）
            if any(
                self._items[n].critical
                and self._runtime_states[n].status == ComponentStatus.FAILED
                for n in items
            ):
                for n in items:
                    if self._runtime_states[n].status == ComponentStatus.FAILED:
                        failed.append(n)
                logger.error(
                    f"[启动] {phase_name} 波次{wave_index} 关键组件失败，中止当前相位"
                )
                return self._phase_result_failed(phase, start)
            # 失败传播
            for name in items:
                state = self._runtime_states[name]
                if state.status == ComponentStatus.FAILED:
                    failed.append(name)
                    # ZG-14 接入（design §1.1.2）：启动失败上报 CRITICAL，
                    # 由升级梯分派 RESTART_COMPONENT；FailurePropagator
                    # 现有 STRONG→SKIPPED / WEAK→DEGRADED 语义不变
                    self._report_startup_failure(name)
                    if self._graph is not None:
                        prop = propagator.propagate(name, self._graph, {
                            n: s.status for n, s in self._runtime_states.items()
                        })
                        for n, st in prop.state_updates.items():
                            if n == CoreReadinessBarrier.VIRTUAL_NODE_ID:
                                continue  # 屏障虚拟节点不入运行时状态
                            self._runtime_states[n].status = st
                            if st == ComponentStatus.SKIPPED:
                                skipped.append(n)
                            elif st == ComponentStatus.DEGRADED:
                                degraded.append(n)
                        failure_chains.update(prop.failure_chains)

        # 相位状态
        critical_failed = any(
            self._runtime_states[n].status != ComponentStatus.SUCCESS
            for n in phase_items
            if self._items[n].critical
        )
        status = ComponentStatus.FAILED if critical_failed else ComponentStatus.SUCCESS
        end = time.monotonic()
        if status == ComponentStatus.SUCCESS:
            logger.info(f"[启动] 阶段{phase.value}: {phase_name} 状态=成功")
        else:
            logger.error(f"[启动] 阶段{phase.value}: {phase_name} 状态=失败（关键组件未全部成功）")
        return PhaseResult(
            phase=phase,
            status=status,
            start_time=start,
            end_time=end,
            duration_ms=int((end - start) * 1000),
            components=[],
        )

    def _report_startup_failure(self, component_id: str) -> None:
        """经 registry 获取 ZG-14 Port 上报启动失败（未注入跳过不影响传播）。

        通过 Protocol + 运行时注入获取，不直接导入 ZG-14 具体类
        （spec §5.7.1 规则 9）；上报失败仅记日志。
        """
        try:
            from src.core.error_escalation_port_registry import get_error_escalation_port

            port = get_error_escalation_port()
            if port is not None:
                port.report(
                    ErrorLevel.CRITICAL,
                    f"启动失败: {component_id}",
                    component_id=component_id,
                )
        except Exception as e:
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, 'ZG-14 启动失败上报出错，传播继续', exception=e)
            logger.warning("ZG-14 启动失败上报出错，传播继续: %s", e)

    def _mark_phase_skipped(
        self, phase: StartupPhase, skipped: list[str], reason: str
    ) -> None:
        """前相位失败：本相位全部项标记 SKIPPED。"""
        for name, desc in self._items.items():
            if desc.phase == phase and name not in skipped:
                self._runtime_states[name].status = ComponentStatus.SKIPPED
                self._runtime_states[name].skip_reason = reason
                skipped.append(name)

    # ── 单项执行 ─────────────────────────────────────────────────

    async def _run_item(self, name: str, wave: int = 0) -> None:
        state = self._runtime_states[name]
        if state.status not in (ComponentStatus.PENDING, ComponentStatus.DEGRADED):
            return
        was_degraded = state.status == ComponentStatus.DEGRADED
        state.status = ComponentStatus.IN_PROGRESS
        state.start_time = time.monotonic()
        try:
            await self._items[name].init_fn()
            # P0-1: WEAK 降级项仍执行；成功后保持 DEGRADED（降级运行）
            state.status = ComponentStatus.DEGRADED if was_degraded else ComponentStatus.SUCCESS
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                try:
                    port.report(ErrorLevel.ERROR, '启动组件失败', exception=exc)
                except Exception:
                    logger.warning("启动失败上报异常，不掩盖原始异常: %s", exc, exc_info=True)
            state.status = ComponentStatus.FAILED
            state.error = exc
            if self._items[name].critical:
                logger.error(f"[{name}] 关键组件初始化失败: {exc}", exc_info=True)
            else:
                logger.warning(f"[{name}] 非关键组件初始化失败（降级继续）: {exc}")
        finally:
            state.end_time = time.monotonic()
            state.duration_ms = int((state.end_time - state.start_time) * 1000)
            if self.debug_mode:
                logger.info(
                    f"启动项 {name} | 相位={self._items[name].phase.name} "
                    f"| 波次={wave} | 结果={state.status.name} | 耗时={state.duration_ms}ms"
                )

    async def _run_item_safe(self, name: str, wave: int = 0) -> None:
        """子系统单项——无论成败都不传播异常（与存量 safe 语义一致）。"""
        state = self._runtime_states[name]
        if state.status not in (ComponentStatus.PENDING, ComponentStatus.DEGRADED):
            return
        was_degraded = state.status == ComponentStatus.DEGRADED
        state.status = ComponentStatus.IN_PROGRESS
        state.start_time = time.monotonic()
        try:
            await asyncio.wait_for(
                self._items[name].init_fn(), timeout=_SUBSYSTEM_TIMEOUT
            )
            state.status = ComponentStatus.DEGRADED if was_degraded else ComponentStatus.SUCCESS
        except asyncio.TimeoutError:
            state.status = ComponentStatus.FAILED
            state.error = f"超时 {_SUBSYSTEM_TIMEOUT}s"
            self._subsystem_status[name] = ComponentStatus.FAILED
            logger.warning(f"[{name}] 子系统启动超时")
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, '启动编排失败', exception=exc)
            from src.core.tainted_mask.mark import mark_exception_swallowed
            mark_exception_swallowed()
            state.status = ComponentStatus.FAILED
            state.error = exc
            self._subsystem_status[name] = ComponentStatus.FAILED
            logger.warning(f"[{name}] 子系统初始化失败（降级继续）: {exc}")
        finally:
            state.end_time = time.monotonic()
            state.duration_ms = int((state.end_time - state.start_time) * 1000)
            if self.debug_mode:
                logger.info(
                    f"启动项 {name} | 相位={self._items[name].phase.name} "
                    f"| 波次={wave} | 结果={state.status.name} | 耗时={state.duration_ms}ms"
                )

    def _phase_result_failed(self, phase: StartupPhase, start: float) -> PhaseResult:
        """关键组件失败时立即返回失败相位结果（P1-1）。"""
        end = time.monotonic()
        return PhaseResult(
            phase=phase,
            status=ComponentStatus.FAILED,
            start_time=start,
            end_time=end,
            duration_ms=int((end - start) * 1000),
            components=[],
        )

    # ── 核心就绪 / 冻结 / 回调 ───────────────────────────────────

    def _update_core_readiness(self) -> None:
        """CORE_SERVICES 完成后按 core_readiness_flag 更新核心就绪。"""
        for name, desc in self._items.items():
            if (
                desc.core_readiness_flag
                and self._runtime_states[name].status == ComponentStatus.SUCCESS
            ):
                setattr(self._core_readiness, desc.core_readiness_flag, True)
        if self._core_readiness.core_ready and self._core_ready_time == 0.0:
            self._core_ready_time = time.monotonic()
        # 屏障就绪检查（贡献组件全部 SUCCESS）
        self._barrier.check({
            n: self._runtime_states[n].status for n in self._runtime_states
        })

    async def _wait_async_settle(self) -> None:
        """等待异步子系统 settle（对标 Linux async_synchronize_full）。"""
        # 当前实现：SUBSYSTEMS 波次已 gather 等待；保留钩子供未来异步回填
        await asyncio.sleep(0)

    def _freeze_config(self) -> None:
        """配置冻结（标记只读，对标 __init 内存回收前的同步点）。"""
        try:
            from src.core.app_config_port_registry import get_app_config_port

            port = get_app_config_port()
            if port is not None:
                port.freeze()
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, '配置冻结失败（不阻断启动）', exception=exc)
            logger.warning("配置冻结失败（不阻断启动）", exc_info=True)

    async def _emit_startup_complete(self, result: StartupResult) -> None:
        """发布启动完成事件（EventBus.emit，nofail 不阻断启动）。"""
        try:
            from src.core.event_bus import event_bus

            await event_bus.emit(
                "startup_complete",
                robust=False,
                nofail=True,
            )
            # EventBus.emit 仅接受 MaiMessages，result 详情由结构化日志承载
            logger.info(
                f"[启动] StartupCompleteEvent 已发布 | ready={result.ready} | "
                f"耗时={result.total_duration_ms}ms | failed={result.failed_components} | "
                f"skipped={result.skipped_components} | degraded={result.degraded_components}"
            )
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, 'StartupCompleteEvent 发布失败（不阻断启动）', exception=exc)
            logger.warning("StartupCompleteEvent 发布失败（不阻断启动）", exc_info=True)

    def _build_result(
        self,
        failed: list[str],
        degraded: list[str],
        skipped: list[str],
        failure_chains: dict[str, str],
    ) -> StartupResult:
        total_ms = int((time.monotonic() - self._start_time) * 1000)
        core_ready_ms = 0
        if self._core_readiness.core_ready and self._core_ready_time > 0:
            core_ready_ms = int((self._core_ready_time - self._start_time) * 1000)
        wave_info = {
            phase: [[n for n in wave if n != CoreReadinessBarrier.VIRTUAL_NODE_ID]
                    for wave in waves]
            for phase, waves in (self._wave_plan.phases if self._wave_plan else {}).items()
        }
        return StartupResult(
            total_duration_ms=total_ms,
            phases=self._phase_results,
            failed_components=list(dict.fromkeys(failed)),
            degraded_components=list(dict.fromkeys(degraded)),
            skipped_components=list(dict.fromkeys(skipped)),
            ready=all(
                not self._items[n].critical
                or self._runtime_states[n].status == ComponentStatus.SUCCESS
                for n in self._runtime_states
            ),
            core_ready=self._core_readiness.core_ready,
            core_ready_time_ms=core_ready_ms,
            subsystem_status=self._subsystem_status,
            wave_info=wave_info,
            failure_chains=failure_chains,
        )

    def _emit_startup_summary(self, result: StartupResult) -> None:
        lines = [
            f"[启动摘要] 总耗时={result.total_duration_ms}ms | "
            f"核心就绪={result.core_ready_time_ms}ms | ready={result.ready}",
        ]
        for phase in sorted(StartupPhase, key=lambda p: p.value):
            pr = result.phases.get(phase)
            if pr is None:
                continue
            status = "✓" if pr.status == ComponentStatus.SUCCESS else "✗"
            phase_name = _PHASE_NAMES.get(phase, phase.name)
            lines.append(f"  阶段{phase.value} {phase_name}: {pr.duration_ms}ms {status}")
            for name in self._items:
                if self._items[name].phase == phase:
                    st = self._runtime_states[name].status
                    mark = {"success": "✓", "failed": "✗", "skipped": "-",
                            "degraded": "~"}.get(st.value, "?")
                    lines.append(f"    {name}: {mark} {st.value}")
        if result.skipped_components:
            lines.append(f"  跳过: {', '.join(result.skipped_components)}")
        if result.failure_chains:
            lines.append(
                "  失败链: " + ", ".join(
                    f"{k}←{v}" for k, v in result.failure_chains.items()
                )
            )
        logger.info("\n".join(lines))
