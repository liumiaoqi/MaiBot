"""ResourceLimitAdapter — 实现 ResourceLimitPort，组装 5 核心引擎。

适配器层，唯一允许导入资源限制引擎类的地方。
核心通过 ResourceLimitPort Protocol 接口交互，不直接导入本模块。
"""


import logging
from typing import Any, Optional

from src.core.protocols import ResourceLimitPort
from src.core.resource_limit.oom_handler import OOMHandler
from src.core.resource_limit.pressure_detector import PressureDetector
from src.core.resource_limit.resource_counter import ResourceCounter
from src.core.resource_limit.resource_event_propagator import ResourceEventPropagator
from src.core.resource_limit.resource_limit_config import ResourceLimitConfigManager
from src.core.resource_limit.types import (
    ChargeResult,
    OOMDecision,
    OOMDecisionRecord,
    PressureHistoryEntry,
    PressureLevel,
    ResourceDimension,
    ResourceTreeView,
    ResourceUsageSnapshot,
)

logger = logging.getLogger(__name__)


class ResourceLimitAdapter(ResourceLimitPort):
    """资源限制适配器 — 组装 5 引擎，实现 ResourceLimitPort。

    适配器层唯一入口，核心模块不导入资源限制具体类（spec §7.1 规则 1）。
    """

    def __init__(
        self,
        event_bus_port: Any = None,
        service_manager_port: Any = None,
        app_config_port: Any = None,
        watchdog_port: Any = None,
        plugin_runtime_port: Any = None,
        kill_callback: Optional[Any] = None,
        kill_exempt_plugin_ids: frozenset[str] = frozenset(),
    ):
        self._event_bus = event_bus_port
        self._service_manager = service_manager_port
        self._app_config = app_config_port
        self._watchdog = watchdog_port
        self._plugin_runtime = plugin_runtime_port
        self._kill_callback = kill_callback
        # OOM 处置豁免名单（如 napcat adapter——用户交流通道，永不杀）
        self._kill_exempt_plugin_ids = kill_exempt_plugin_ids

        # 配置管理器
        self._config_manager = ResourceLimitConfigManager()

        # 压力检测器
        self._pressure_detector = PressureDetector(event_bus=event_bus_port)

        # 资源计数器（max_limit_provider 委托配置管理器，pressure_sample_callback 委托压力检测器）
        self._counter = ResourceCounter(
            max_limit_provider=self._config_manager.get_max,
            pressure_sample_callback=self._on_pressure_sample,
        )

        # OOM 处理器（kill 回调带豁免包装——豁免插件永不杀，如 napcat adapter）
        self._oom_handler = OOMHandler(
            resource_counter=self._counter,
            config_manager=self._config_manager,
            event_bus=event_bus_port,
            service_manager=service_manager_port,
            kill_callback=self._wrap_kill_callback(kill_callback),
        )

        # 事件传播器
        self._event_propagator = ResourceEventPropagator(
            event_bus=event_bus_port,
            config_manager=self._config_manager,
        )

    def _wrap_kill_callback(self, kill_callback: Optional[Any]) -> Optional[Any]:
        """包装 kill 回调：豁免名单内插件永不杀（用户交流通道），返回 False 交回 OOM 处置。"""
        if kill_callback is None:
            return None

        def _kill(plugin_id: str) -> bool:
            if plugin_id in self._kill_exempt_plugin_ids:
                logging.getLogger("resource_limit").warning(
                    "OOM 处置跳过豁免插件 %s（用户交流通道，永不杀）", plugin_id
                )
                return False
            return bool(kill_callback(plugin_id))

        return _kill

        # 压力历史
        self._pressure_history: list[PressureHistoryEntry] = []

    def _on_pressure_sample(self, scanned: int, reclaimed: int) -> None:
        """charge 内部压力采样回调。"""
        changed = self._pressure_detector.record_sample(scanned, reclaimed)
        if changed is not None:
            import time
            self._pressure_history.append(PressureHistoryEntry(
                level=changed,
                scanned=self._pressure_detector.window.scanned,
                reclaimed=self._pressure_detector.window.reclaimed,
                ratio=0.0 if self._pressure_detector.window.scanned == 0
                else (self._pressure_detector.window.scanned - self._pressure_detector.window.reclaimed)
                / self._pressure_detector.window.scanned * 100,
                timestamp=time.monotonic(),
            ))

    # --- ResourceLimitPort 实现 ---

    def charge(
        self, plugin_id: str, dimension: ResourceDimension, amount: int
    ) -> ChargeResult:
        """投机充值（同步，热路径）。"""
        result = self._counter.charge(plugin_id, dimension, amount)

        if not result.accepted and result.overflow_dimension is not None:
            # 超 max，检查是否需要触发 OOM
            snapshot = self._counter.get_usage_snapshot(plugin_id)
            if snapshot:
                usage = snapshot.token_usage if dimension == ResourceDimension.TOKEN else \
                    snapshot.message_usage if dimension == ResourceDimension.MESSAGE else \
                    snapshot.concurrent_usage if dimension == ResourceDimension.CONCURRENT else \
                    snapshot.memory_usage
                limit = self._config_manager.get_max(result.overflow_node_id or plugin_id, dimension)
                if limit is not None:
                    # OOM 触发是异步的，这里不等待
                    import asyncio
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            loop.create_task(
                                self._oom_handler.trigger_oom(
                                    plugin_id, dimension, usage, limit
                                )
                            )
                        else:
                            logger.warning("事件循环未运行，OOM 触发延迟到下次 charge")
                    except RuntimeError:
                        logger.warning("无事件循环，OOM 触发延迟")

        return result

    def uncharge(
        self, plugin_id: str, dimension: ResourceDimension, amount: int
    ) -> None:
        """递减计量（同步）。"""
        self._counter.uncharge(plugin_id, dimension, amount)

    def get_usage_snapshot(
        self, plugin_id: str
    ) -> Optional[ResourceUsageSnapshot]:
        """查询单插件资源计量快照。"""
        return self._counter.get_usage_snapshot(plugin_id)

    async def register_plugin(
        self, plugin_id: str, parent_id: Optional[str] = None
    ) -> None:
        """注册插件到资源计量树。"""
        self._counter.register_plugin(plugin_id, parent_id)

    async def unregister_plugin(self, plugin_id: str) -> None:
        """注销插件，孤儿子节点挂根。"""
        self._counter.unregister_plugin(plugin_id)

    async def reload_config(self) -> None:
        """热更新配置，≤5s 生效。"""
        # 实际配置从 AppConfigPort 读取，这里先占位
        # 适配器注册后由启动编排器注入实际配置
        logger.info("资源限制配置热更新")

    def record_pressure_sample(
        self, scanned: int, reclaimed: int, scan_priority: int = 12
    ) -> Optional[PressureLevel]:
        """记录压力采样。"""
        return self._pressure_detector.record_sample(scanned, reclaimed, scan_priority)

    async def trigger_oom(
        self,
        trigger_plugin_id: str,
        dimension: ResourceDimension,
        usage: int,
        limit: int,
    ) -> Optional[OOMDecision]:
        """触发 OOM 处理。"""
        return await self._oom_handler.trigger_oom(
            trigger_plugin_id, dimension, usage, limit
        )

    def get_resource_tree_view(self) -> ResourceTreeView:
        """查询资源计量树全貌快照。"""
        nodes = [n.to_snapshot() for n in self._counter.all_nodes()]
        topology: dict[str, Optional[str]] = {}
        for n in self._counter.all_nodes():
            topology[n.plugin_id] = n.parent.plugin_id if n.parent else None
        return ResourceTreeView(nodes=nodes, topology=topology)

    def get_pressure_history(
        self, limit: int = 100
    ) -> list[PressureHistoryEntry]:
        """查询压力等级历史。"""
        return self._pressure_history[-limit:]

    def get_oom_history(
        self, limit: int = 100
    ) -> list[OOMDecisionRecord]:
        """查询 OOM 决策历史。"""
        return self._oom_handler.get_oom_history(limit)