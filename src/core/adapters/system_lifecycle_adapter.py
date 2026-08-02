"""SystemLifecycleAdapter — 将状态机核心与外部组件连接（6 衔接点）。

适配器层（唯一允许导入具体类的位置）。核心模块不导入具体类。
"""

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

from src.common.log_pipeline.suppressor import set_health_level_provider
from src.core.protocols import CoreReadinessPort
from src.core.service_manager.state_aggregator import StateAggregator
from src.core.system_state.state_machine import SystemStateMachine
from src.core.system_state.types import SystemLifecycleState, SystemLifecycleView

logger = logging.getLogger(__name__)

# 核心就绪三标志名（与 CoreReadiness 字段一致）
_CORE_FLAGS = (
    "message_pipeline_ready",
    "agent_thinking_ready",
    "reply_capability_ready",
)


class SystemLifecycleAdapter:
    """状态机适配器：StartupOrchestrator/StateAggregator/CoreReadiness/ZG-2/ServiceManager/信号 六衔接。"""

    def __init__(
        self,
        state_machine: SystemStateMachine,
        core_readiness_port: CoreReadinessPort,
        state_aggregator: StateAggregator,
        crash_export_dir: Path | None = None,
    ) -> None:
        self._sm = state_machine
        self._crp = core_readiness_port
        self._agg = state_aggregator
        self._crash_export_dir = crash_export_dir or Path("logs")
        self._main_loop = _try_get_running_loop()

        # 衔接 4：向 ZG-2 注册健康等级 provider
        set_health_level_provider(self._health_level_provider)

        # 衔接 2：订阅 StateAggregator 健康变更（同步回调 → 异步桥接）
        self._agg.subscribe(self._on_health_view_change)

        # 衔接 3：BOOTING 期间强制核心就绪三标志全 False
        self._force_core_readiness(False)

        # 崩溃导出钩子（提示 2：适配器自注册，不动 ZG-2 代码）
        self._register_crash_hooks()

    # ── 衔接 2：StateAggregator 健康变更 ────────────────────

    def _health_level_provider(self) -> object | None:
        """衔接 4：向 ZG-2 提供健康等级。"""
        try:
            view = self._agg.build_view()
            return view.level
        except Exception:
            from src.core.tainted_mask.mark import mark_exception_swallowed
            mark_exception_swallowed()
            return None

    def _on_health_view_change(self, view) -> None:
        """StateAggregator 同步回调 → 异步触发迁移（提示 1：无 loop 回退同步）。

        非 BOOTING 时同步三标志（CX 审查发现：__init__ 强制 False 后若无
        恢复点，标志永久 False——按聚合器计算值持续驱动）。
        """
        if not self._sm.is_booting():
            self._sync_core_readiness()

        async def _trigger() -> None:
            await self._sm.trigger_health_level_change(view.level)

        loop = self._main_loop or _try_get_running_loop()
        if loop is not None and loop.is_running():
            loop.create_task(_trigger())
        else:
            # 无运行 loop：同步触发（低频事件，可接受）
            asyncio.run(_trigger())

    # ── 衔接 1/6：启动完成 / 关闭信号 ───────────────────────

    async def trigger_startup_complete(self) -> None:
        """衔接 1：正常启动完成 → READY（迁移后按聚合器恢复三标志）。"""
        await self._sm.trigger_startup_complete()
        self._sync_core_readiness()

    async def trigger_startup_complete_degraded(self) -> None:
        """衔接 1：降级启动完成 → DEGRADING（W1，迁移后恢复三标志）。"""
        await self._sm.trigger_startup_complete_degraded()
        self._sync_core_readiness()

    async def trigger_shutdown(self) -> None:
        """衔接 6：信号/主动 shutdown → SHUTTING_DOWN（幂等）。"""
        await self._sm.trigger_shutdown()

    # ── 衔接 5：ServiceManager 查询 ────────────────────────

    def get_state(self) -> SystemLifecycleState:
        return self._sm.get_state()

    def get_view(self) -> SystemLifecycleView:
        """WebUI 内省视图：状态 + 健康等级 + 核心就绪三标志 + 迁移历史。"""
        health_level = self._health_level_provider()
        cr = self._crp.get_core_readiness()
        # ZG-7（T22）：注入污染状态（Port 未注册时保持默认 0/空，spec §4.1 规则 4）
        tainted_mask = 0
        tainted_verbose: list[str] = []
        try:
            from src.core.taint_mask_port_registry import get_taint_mask_port

            port = get_taint_mask_port()
            tainted_mask = port.get_taint()
            tainted_verbose = port.print_tainted_verbose()
        except Exception:
            from src.core.tainted_mask.mark import mark_exception_swallowed
            mark_exception_swallowed()
            pass
        return self._sm.get_view(
            health_level=health_level.value if health_level is not None else "healthy",
            core_readiness=(
                cr.message_pipeline_ready,
                cr.agent_thinking_ready,
                cr.reply_capability_ready,
            ),
            tainted_mask=tainted_mask,
            tainted_verbose=tainted_verbose,
        )

    def is_booting(self) -> bool:
        return self._sm.is_booting()

    def is_shutting_down(self) -> bool:
        return self._sm.is_shutting_down()

    def is_running_like(self) -> bool:
        return self._sm.is_running_like()

    # ── 衔接 3：CoreReadiness 强制 ─────────────────────────

    def _force_core_readiness(self, value: bool) -> None:
        """强制三标志为指定值（BOOTING 期间全 False）。"""
        for flag in _CORE_FLAGS:
            try:
                self._crp.update_flag(flag, value)
            except Exception:
                from src.core.tainted_mask.mark import mark_exception_swallowed
                mark_exception_swallowed()
                logger.exception("强制核心就绪标志失败: %s", flag)

    def _sync_core_readiness(self) -> None:
        """按聚合器计算值同步三标志（READY/DEGRADING 后由 StateAggregator 驱动）。

        CX 审查发现：__init__ 强制 False 后若无恢复点，标志永久 False——
        此处实现 core_readiness_port.py docstring 承诺的"运行时持续更新"语义。
        """
        try:
            msg, agent, reply = self._agg.compute_core_readiness()
            self._crp.update_flag("message_pipeline_ready", msg)
            self._crp.update_flag("agent_thinking_ready", agent)
            self._crp.update_flag("reply_capability_ready", reply)
        except Exception:
            from src.core.tainted_mask.mark import mark_exception_swallowed
            mark_exception_swallowed()
            logger.exception("同步核心就绪标志失败")

    # ── 崩溃导出钩子（提示 2）───────────────────────────────

    def _register_crash_hooks(self) -> None:
        """注册 excepthook + signal 兜底钩子，崩溃时导出迁移历史（best-effort）。

        生产环境 main.py 会在初始化后用 loop.add_signal_handler 后注册优雅
        退出 handler（覆盖本钩子，信号走 SHUTTING_DOWN 优雅路径）；本钩子仅作
        独立使用/测试场景的兜底，导出后链式调用前一个 handler（ZG-2 crash_dump
        的 handler），不丢既有崩溃导出。
        """
        try:
            for signum in (signal.SIGTERM, signal.SIGINT):
                prev = signal.getsignal(signum)
                signal.signal(signum, self._make_signal_handler(signum, prev))
        except Exception:
            from src.core.tainted_mask.mark import mark_exception_swallowed
            mark_exception_swallowed()
            pass  # 非主线程等场景注册失败忽略
        sys.excepthook = self._make_excepthook(sys.excepthook)

    def _make_signal_handler(self, signum: int, prev):
        """兜底信号处理：导出迁移历史后链式调用前一个 handler。"""

        def handler(sig, frame):
            self._export_history("signal")
            if callable(prev):
                prev(sig, frame)
            elif prev == signal.SIG_DFL:
                # 无前驱 handler：恢复默认行为（终止进程）
                signal.signal(signum, signal.SIG_DFL)
                os.kill(os.getpid(), signum)

        return handler

    def _make_excepthook(self, original):
        def hook(exc_type, exc_value, exc_tb):
            self._export_history(f"uncaught-{exc_type.__name__}")
            original(exc_type, exc_value, exc_tb)

        return hook

    def _export_history(self, reason: str) -> None:
        """尽力导出迁移历史。"""
        try:
            from src.core.system_state.history import TransitionHistory

            path = TransitionHistory.default_export_path(self._crash_export_dir)
            self._sm.export_history_to(path)
        except Exception:
            from src.core.tainted_mask.mark import mark_exception_swallowed
            mark_exception_swallowed()
            pass  # best-effort


def _try_get_running_loop() -> asyncio.AbstractEventLoop | None:
    """获取当前运行事件循环；无则返回 None。"""
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None
