from typing import TYPE_CHECKING, Any

from rich.traceback import install

import asyncio
import sys
import time

from pathlib import Path

from src.common.i18n import t
from src.common.logger import get_logger
from src.common.runtime_loop import set_main_loop
from src.config.config import global_config
from src.manager.async_task_manager import async_task_manager
from src.prompt.prompt_manager import prompt_manager

# from src.api.main import start_api_server

# 导入插件运行时
# 导入消息API和traceback模块
# from src.chat.utils.token_statistics import TokenStatisticsTask

install(extra_lines=3)

logger = get_logger("main")


if TYPE_CHECKING:
    from maim_message import MessageServer
    from src.common.message_server.server import Server
    from src.webui.webui_server import ThreadedWebUIServer


class MainSystem:
    def __init__(self) -> None:
        # 使用消息API替代直接的FastAPI实例
        self.app: MessageServer | None = None
        self.server: Server | None = None
        self.webui_server: ThreadedWebUIServer | None = None  # 独立线程中的 WebUI 服务器
        self._message_handlers_registered = False
        self._interaction_scheduler: Any | None = None
        self._agent_registry: Any | None = None
        self._model_config_port: Any | None = None
        self._chat_manager_adapter: Any | None = None
        self._replyer_adapter: Any | None = None
        self._v2_host_endpoint: Any | None = None
        self._init_start_time: float = 0.0
        self._orchestrator: Any | None = None
        self._service_manager: Any | None = None
        self._watchdog: Any | None = None
        self._watchdog_touch_task: asyncio.Task | None = None
        self._control_message: Any | None = None
        self._taint_mask: Any | None = None

    def _ensure_message_server(self) -> None:
        """按需初始化消息 API，避免阻塞主启动链路的早期阶段。"""

        if self.app is not None and self.server is not None:
            return

        from src.common.message_server import get_global_api
        from src.common.message_server.server import get_global_server

        self.app = get_global_api()
        self.server = get_global_server()

    def _register_message_handlers(self) -> None:
        """注册主消息处理器；消息服务实际调度前完成即可。"""

        if self._message_handlers_registered:
            return

        self._ensure_message_server()
        if self.app is None:
            raise RuntimeError("消息 API 初始化失败")

        from src.chat.message_receive.bot import chat_bot
        from src.core.adapters.message_ingestion_port import get_message_ingestion_port

        self.app.register_message_handler(get_message_ingestion_port().message_process)
        self.app.register_custom_message_handler("message_id_echo", chat_bot.echo_message_process)
        self._message_handlers_registered = True

    def _start_webui_server(self) -> None:
        """启动独立线程中的 WebUI 服务器。"""
        from src.config.config import global_config

        if not global_config.webui.enabled:
            logger.info(t("startup.webui_disabled"))
            return

        try:
            from src.webui.webui_server import get_threaded_webui_server

            self.webui_server = get_threaded_webui_server()
            self.webui_server.start()

        except Exception as e:
            logger.error(t("startup.webui_server_init_failed", error=e))

    async def initialize(self) -> None:
        """初始化系统组件"""
        logger.info(t("startup.waking_up", nickname=global_config.bot.nickname))

        try:
            await self._init_components()
        except Exception:
            logger.warning("操作异常 in main.py", exc_info=True)
            if self.webui_server:
                await self.webui_server.shutdown()
            raise

        logger.info(t("startup.initialization_completed_banner", nickname=global_config.bot.nickname))

    # ── 启动编排（SSD-4 startup_reform T2.2）──────────────────

    async def _init_components(self) -> None:
        """使用 StartupOrchestrator 按 6 阶段执行初始化。"""
        from src.core.startup import (

            StartupComponent,
            StartupOrchestrator,
            StartupPhase,
        )

        self._init_start_time = time.time()
        orchestrator = StartupOrchestrator()

        # 阶段 0：配置加载
        orchestrator.register(StartupComponent(
            name="config_manager", phase=StartupPhase.CONFIG_LOAD, order=0, critical=True,
            init_fn=self._noop_config_loaded,
        ))
        orchestrator.register(StartupComponent(
            name="config_validator", phase=StartupPhase.CONFIG_LOAD, order=1, critical=True,
            init_fn=self._validate_startup_config,
        ))

        # 阶段 1：基础设施
        orchestrator.register(StartupComponent(
            name="file_watcher", phase=StartupPhase.INFRASTRUCTURE, order=0, critical=True,
            init_fn=self._start_file_watcher,
        ))
        orchestrator.register(StartupComponent(
            name="tool_record_vacuum", phase=StartupPhase.INFRASTRUCTURE, order=1, critical=False,
            init_fn=self._run_tool_vacuum,
        ))

        # 阶段 2：核心服务
        orchestrator.register(StartupComponent(
            name="agent_registry", phase=StartupPhase.CORE_SERVICES, order=0, critical=True,
            init_fn=self._init_agent_registry,
            core_readiness_flag="agent_thinking_ready",
        ))
        orchestrator.register(StartupComponent(
            name="session_submodules", phase=StartupPhase.CORE_SERVICES, order=1, critical=True,
            init_fn=self._init_session_submodules,
        ))
        orchestrator.register(StartupComponent(
            name="chat_manager_adapter", phase=StartupPhase.CORE_SERVICES, order=2, critical=True,
            init_fn=self._init_adapter_and_ports,
            core_readiness_flag="message_pipeline_ready",
        ))
        orchestrator.register(StartupComponent(
            name="replyer_port", phase=StartupPhase.CORE_SERVICES, order=3, critical=True,
            init_fn=self._init_replyer_port,
            core_readiness_flag="reply_capability_ready",
        ))
        orchestrator.register(StartupComponent(
            name="image_port", phase=StartupPhase.CORE_SERVICES, order=4, critical=True,
            init_fn=self._init_image_port,
        ))
        orchestrator.register(StartupComponent(
            name="runtime_port", phase=StartupPhase.CORE_SERVICES, order=5, critical=True,
            init_fn=self._init_runtime_port,
        ))
        orchestrator.register(StartupComponent(
            name="model_config_port", phase=StartupPhase.CORE_SERVICES, order=6, critical=True,
            init_fn=self._init_model_config_port,
        ))
        orchestrator.register(StartupComponent(
            name="llm_service_port", phase=StartupPhase.CORE_SERVICES, order=7, critical=True,
            init_fn=self._init_llm_service_port,
        ))
        orchestrator.register(StartupComponent(
            name="message_ingestion_port", phase=StartupPhase.CORE_SERVICES, order=8, critical=True,
            init_fn=self._init_message_ingestion_port,
        ))
        orchestrator.register(StartupComponent(
            name="person_info_port", phase=StartupPhase.CORE_SERVICES, order=9, critical=True,
            init_fn=self._init_person_info_port,
        ))
        orchestrator.register(StartupComponent(
            name="bot_config_port", phase=StartupPhase.CORE_SERVICES, order=10, critical=True,
            init_fn=self._init_bot_config_port,
        ))
        orchestrator.register(StartupComponent(
            name="chat_config_port", phase=StartupPhase.CORE_SERVICES, order=11, critical=True,
            init_fn=self._init_chat_config_port,
        ))
        orchestrator.register(StartupComponent(
            name="app_config_port", phase=StartupPhase.CORE_SERVICES, order=12, critical=True,
            init_fn=self._init_app_config_port,
        ))
        orchestrator.register(StartupComponent(
            name="event_bus_port", phase=StartupPhase.CORE_SERVICES, order=13, critical=True,
            init_fn=self._init_event_bus_port,
        ))
        orchestrator.register(StartupComponent(
            name="prompt_manager", phase=StartupPhase.CORE_SERVICES, order=14, critical=True,
            init_fn=self._load_prompts,
        ))

        # 阶段 3：子系统
        orchestrator.register(StartupComponent(
            name="plugin_runtime", phase=StartupPhase.SUBSYSTEMS, order=0, critical=False,
            init_fn=self._start_plugin_runtime,
        ))
        orchestrator.register(StartupComponent(
            name="plugin_runtime_v2", phase=StartupPhase.SUBSYSTEMS, order=1, critical=False,
            init_fn=self._start_plugin_runtime_v2,
        ))
        orchestrator.register(StartupComponent(
            name="emoji_manager", phase=StartupPhase.SUBSYSTEMS, order=2, critical=False,
            init_fn=self._load_emoji,
        ))
        orchestrator.register(StartupComponent(
            name="model_config_port_inject", phase=StartupPhase.SUBSYSTEMS, order=3, critical=False,
            init_fn=self._inject_model_config_port,
        ))
        # a_memorix 内核初始化依赖 ModelConfigPort——必须在注入之后启动
        orchestrator.register(StartupComponent(
            name="a_memorix", phase=StartupPhase.SUBSYSTEMS, order=4, critical=False,
            init_fn=self._start_a_memorix,
        ))

        # 阶段 4：会话恢复
        orchestrator.register(StartupComponent(
            name="session_lifecycle", phase=StartupPhase.SESSION_RESTORE, order=0, critical=True,
            init_fn=self._restore_sessions,
        ))
        orchestrator.register(StartupComponent(
            name="memory_automation", phase=StartupPhase.SESSION_RESTORE, order=1, critical=False,
            init_fn=self._start_memory_automation,
        ))

        # 阶段 5：就绪
        orchestrator.register(StartupComponent(
            name="message_handlers", phase=StartupPhase.READY, order=0, critical=True,
            init_fn=self._register_handlers,
        ))
        orchestrator.register(StartupComponent(
            name="on_start_event", phase=StartupPhase.READY, order=1, critical=True,
            init_fn=self._emit_on_start,
        ))
        orchestrator.register(StartupComponent(
            name="webui_server", phase=StartupPhase.READY, order=2, critical=False,
            init_fn=self._start_webui,
        ))
        orchestrator.register(StartupComponent(
            name="scheduled_tasks", phase=StartupPhase.READY, order=3, critical=False,
            init_fn=self._add_scheduled_tasks,
        ))
        orchestrator.register(StartupComponent(
            name="interaction_scheduler", phase=StartupPhase.READY, order=4, critical=False,
            init_fn=self._start_interaction_scheduler,
        ))

        self._orchestrator = orchestrator
        self._startup_result = await orchestrator.run()

        if not self._startup_result.ready:
            failed_names = [c.name for c in self._startup_result.failed_components if c.critical]
            if failed_names:
                raise RuntimeError(f"关键组件初始化失败: {failed_names}")
            logger.warning(f"系统降级启动，失败组件: {[c.name for c in self._startup_result.failed_components]}")

        # ZG-1: 服务管理器接管运行时组件
        from src.core.adapters.service_manager_adapter import ServiceManagerAdapter
        from src.core.service_manager.descriptors import (
            get_dependency_relations,
            get_service_descriptors,
        )

        # 构建核心组件健康探针
        probe_functions: dict = {}
        if self._chat_manager_adapter is not None:
            probe_functions["chat_manager_adapter"] = self._chat_manager_adapter.health_probe
        if self._agent_registry is not None:
            probe_functions["agent_registry"] = self._agent_registry.health_probe
        if self._replyer_adapter is not None:
            probe_functions["replyer_port"] = self._replyer_adapter.health_probe

        # ZG-6 衔接 5：系统关闭谓词注入（恢复引擎关闭中不自动拉起组件）
        def _system_shutting_down() -> bool:
            try:
                from src.core.system_state_port_registry import get_system_lifecycle_adapter

                adapter = get_system_lifecycle_adapter()
                return bool(adapter and adapter.is_shutting_down())
            except Exception:
                return False

        self._service_manager = ServiceManagerAdapter(
            probe_functions=probe_functions,
            lifecycle_state_getter=_system_shutting_down,
        )
        await self._service_manager.adopt_from_startup(
            self._startup_result,
            get_service_descriptors(),
            get_dependency_relations(),
        )

        # ZG-6: 系统生命周期状态机 + 适配器（启动完成后创建，紧随其后触发迁移）
        # 时序约束：__init__ 强制核心就绪三标志 False 先于 trigger_startup_complete，
        # 同一协程内顺序执行，避免启动瞬间标志已置 True 的窗口。
        from src.config.config import config_manager as _cm
        from src.core.adapters.core_readiness_port import CoreReadinessPortAdapter
        from src.core.adapters.system_lifecycle_adapter import SystemLifecycleAdapter
        from src.core.system_state.state_machine import SystemStateMachine
        from src.core.system_state_port_registry import set_system_lifecycle_adapter

        sys_state_cfg = _cm.get_global_config().system_state
        self._lifecycle_sm = SystemStateMachine(
            history_capacity=sys_state_cfg.history_capacity,
            notify_timeout=sys_state_cfg.notify_timeout,
        )

        # ZG-4: EventBus 装配注入（配置已加载后；configure 幂等，未注入项保持默认）
        from src.core.event_bus import event_bus as _core_event_bus

        event_bus_cfg = _cm.get_global_config().event_bus
        _core_event_bus.configure(
            rollback_timeout=event_bus_cfg.rollback_timeout,
            vote_history_capacity=event_bus_cfg.vote_history_capacity,
        )
        self._lifecycle_adapter = SystemLifecycleAdapter(
            state_machine=self._lifecycle_sm,
            core_readiness_port=CoreReadinessPortAdapter(orchestrator.get_core_readiness()),
            state_aggregator=self._service_manager.get_state_aggregator(),
        )
        set_system_lifecycle_adapter(self._lifecycle_adapter)
        if self._startup_result.ready:
            await self._lifecycle_adapter.trigger_startup_complete()
        else:
            await self._lifecycle_adapter.trigger_startup_complete_degraded()

        # ZG-3: 注册 ServiceManagerPort + 启动看门狗
        from src.core.service_manager_port_registry import set_service_manager_port

        set_service_manager_port(self._service_manager)

        from src.core.adapters.watchdog_adapter import WatchdogAdapter
        from src.core.app_config_port_registry import get_app_config_port
        from src.core.watchdog_port_registry import set_watchdog_port

        watchdog_config = get_app_config_port().get_watchdog_config()
        self._watchdog = WatchdogAdapter(config=watchdog_config)
        set_watchdog_port(self._watchdog)
        await self._watchdog.start(asyncio.get_running_loop())

        # ZG-3: V1 Runner 批量注册到看门狗桥接（V1 在阶段 3 已启动，
        # 早于看门狗；group_name ∈ {builtin, third_party}，v1-* 与 V2 runner-* 隔离；
        # 看门狗/管理器异常时降级跳过，不阻断启动链路）
        try:
            from src.plugin_runtime.integration import get_plugin_runtime_manager

            for sv in get_plugin_runtime_manager().supervisors:
                self._watchdog.register_v1_supervisor(
                    f"v1-{sv.group_name}", sv, "plugin_runtime",
                )
        except Exception:
            logger.warning(
                "V1 Runner 注册到看门狗桥接失败，已降级跳过", exc_info=True
            )

        async def _watchdog_touch_loop() -> None:
            while True:
                self._watchdog.touch()
                await asyncio.sleep(watchdog_config.touch_interval_s)

        self._watchdog_touch_task = asyncio.create_task(
            _watchdog_touch_loop(), name="watchdog-touch"
        )

        # ZG-8: 控制消息优先级接线（适配器实例化 + 订阅 + force 触发 + 状态联动）
        await self._init_control_message()

        # ZG-7: 污染标记接线（适配器实例化 + 注册 + CrashDump 注入）
        await self._init_tainted_mask()

        # ZG-5: 资源限制接线（引擎 75 测试零接线收尾——registry + 实例化 + kill 回调）
        await self._init_resource_limit()

        init_time = int(1000 * (time.time() - self._init_start_time))
        logger.info(t("startup.initialization_completed_cycles", init_time=init_time))

    async def _init_resource_limit(self) -> None:
        """ZG-5: 资源限制接线。

        实例化 ResourceLimitAdapter（组装 5 引擎）并注册 ResourceLimitPort；
        kill_callback 两段式终止 v2 Runner（SIGTERM→5s→SIGKILL），
        豁免名单内插件（napcat adapter——用户交流通道）永不杀。
        依赖：event_bus / service_manager / app_config / watchdog / v2 插件运行时均已就绪。
        """
        try:
            from src.core.adapters.resource_limit_adapter import ResourceLimitAdapter
            from src.core.app_config_port_registry import get_app_config_port
            from src.core.event_bus_port_registry import get_event_bus_port
            from src.core.resource_limit_port_registry import (
                reset_resource_limit_port,
                set_resource_limit_port,
            )
            from src.core.service_manager_port_registry import get_service_manager_port
            from src.core.watchdog_port_registry import get_watchdog_port

            async def _kill_v2_runner(plugin_id: str) -> bool:
                """两段式终止 v2 Runner：SIGTERM → 5s → SIGKILL。"""
                try:
                    endpoint = getattr(self, "_v2_host_endpoint", None)
                    supervisor = endpoint.get_supervisor() if endpoint is not None else None
                    if supervisor is None:
                        logger.warning("ZG-5 OOM 处置: v2 插件运行时未就绪，无法杀除 %s", plugin_id)
                        return False
                    return await supervisor.kill_runner(f"runner-{plugin_id}")
                except Exception as exc:
                    logger.warning("ZG-5 OOM 杀除失败: %s error=%s", plugin_id, exc, exc_info=True)
                    return False

            # napcat adapter 是用户交流通道——OOM 处置豁免，永不杀
            kill_exempt = frozenset({"maibot-team.napcat-adapter"})

            adapter = ResourceLimitAdapter(
                event_bus_port=get_event_bus_port(),
                service_manager_port=get_service_manager_port(),
                app_config_port=get_app_config_port(),
                watchdog_port=get_watchdog_port(),
                kill_callback=_kill_v2_runner,
                kill_exempt_plugin_ids=kill_exempt,
            )
            reset_resource_limit_port()
            set_resource_limit_port(adapter)
            logger.info("ZG-5 资源限制已接线（豁免插件: %s）", ", ".join(sorted(kill_exempt)))
        except Exception as exc:
            logger.warning("ZG-5 资源限制接线失败，已降级跳过: %s", exc, exc_info=True)

    async def _init_tainted_mask(self) -> None:
        """ZG-7: 污染标记接线。

        实例化 TaintMaskAdapter（组装 TaintedMask + TaintActionMapper）并注册
        TaintedMaskPort；注入 CrashDump 污染状态查询接口。
        依赖：app_config / SystemStateMachine（self._lifecycle_sm）均已就绪
        （orchestrator.run() 之后、ZG-8 接线后）。照 ZG-8 模式定死实例化点，
        不重蹈 ZG-5 零接线教训。
        """
        try:
            from src.core.adapters.taint_mask_adapter import TaintMaskAdapter
            from src.core.app_config_port_registry import get_app_config_port
            from src.core.taint_mask_port_registry import set_taint_mask_port
        except Exception:
            logger.warning("ZG-7 接线依赖导入失败，已降级跳过", exc_info=True)
            return

        adapter = TaintMaskAdapter(
            state_machine_port=self._lifecycle_sm,
            app_config_port=get_app_config_port(),
        )
        self._taint_mask = adapter
        set_taint_mask_port(adapter)

        # T17: CrashDump 污染状态注入（模块级单例 setter）
        try:
            from src.common.logger import _crash_dump

            if _crash_dump is not None:
                _crash_dump.set_taint_mask_port(adapter)
        except Exception:
            logger.warning("ZG-7 CrashDump 注入失败，污染行跳过", exc_info=True)

        logger.info("ZG-7 污染标记已接线")

        # TAINT_PORT_BYPASS（位0）运行时守卫：检查核心模块是否违规导入禁止项
        self._check_port_bypass_violations()

    def _check_port_bypass_violations(self) -> None:
        """ZG-7 位0 守卫：运行时检测核心模块绕过 Protocol 直接导入禁止项。

        检查方式：遍历核心模块命名空间中对象的 __module__ 属性，
        判断其来源是否属于被禁模块前缀。键名检查无效（from X import Y 不留 X 键）。
        """
        try:
            import importlib
            import inspect

            from src.core.tainted_mask.mark import mark_taint
            from src.core.tainted_mask.taint_flag import TaintFlag

            _BANNED_MODULE_PREFIXES = (
                "src.services.chat_manager",
                "src.A_memorix.core",
                "src.config.config",
                "src.services.send_service",
                "src.core.adapters.service_manager_adapter",
                "src.core.adapters.watchdog_adapter",
            )
            core_pkg = importlib.import_module("src.core")
            core_dir = str(Path(inspect.getfile(core_pkg)).parent)
            # 适配器层豁免收窄：组件禁令整体豁免，但两个被禁适配器自身仍按精确名检查
            banned_adapters = (
                "src.core.adapters.service_manager_adapter",
                "src.core.adapters.watchdog_adapter",
            )

            def _is_banned(module_name: str) -> bool:
                """精确模块名边界匹配（== 或 banned + '.'）——避免前缀误伤。"""
                return any(
                    module_name == banned or module_name.startswith(f"{banned}.")
                    for banned in _BANNED_MODULE_PREFIXES
                )

            for mod_name, mod in list(sys.modules.items()):
                if not mod_name.startswith("src.core."):
                    continue
                if mod_name.startswith("src.core.adapters"):
                    # 适配器豁免：仅两个被禁适配器自身参与检查
                    if not any(
                        mod_name == banned or mod_name.startswith(f"{banned}.")
                        for banned in banned_adapters
                    ):
                        continue
                if mod is None:
                    continue
                try:
                    mod_file = getattr(mod, "__file__", None)
                    if mod_file and not mod_file.startswith(core_dir):
                        continue
                except Exception:
                    continue
                for name, obj in getattr(mod, "__dict__", {}).items():
                    if name.startswith("_"):
                        continue
                    obj_module = getattr(obj, "__module__", None)
                    if obj_module and _is_banned(obj_module):
                        mark_taint(TaintFlag.TAINT_PORT_BYPASS)
                        logger.warning("ZG-7 守卫: %s.%s 违规导入自 %s", mod_name, name, obj_module)
        except Exception:
            pass

    async def _init_control_message(self) -> None:
        """ZG-8: 控制消息优先级接线。

        实例化 ControlMessageAdapter（组装 8 引擎）并注册 ControlMessagePort；
        订阅 ZG-3 看门狗超时（T16）、ZG-6 状态机联动（T17）、
        会话生命周期回调（T18）；声明核心组件 UNKILLABLE（T20）。
        依赖：app_config / event_bus / service_manager / watchdog / session_lifecycle
        均已就绪（orchestrator.run() 之后）。
        """
        try:
            from src.core.adapters.control_message_adapter import ControlMessageAdapter
            from src.core.app_config_port_registry import get_app_config_port
            from src.core.control_message_port_registry import set_control_message_port
            from src.core.event_bus_port_registry import get_event_bus_port
            from src.core.service_manager_port_registry import get_service_manager_port
            from src.core.session_port_registry import get_session_lifecycle_port
            from src.core.watchdog_port_registry import get_watchdog_port
        except Exception:
            logger.warning("ZG-8 接线依赖导入失败，已降级跳过", exc_info=True)
            return

        adapter = ControlMessageAdapter(
            event_bus_port=get_event_bus_port(),
            service_manager_port=get_service_manager_port(),
            app_config_port=get_app_config_port(),
            watchdog_port=get_watchdog_port(),
            session_lifecycle_port=get_session_lifecycle_port(),
        )
        self._control_message = adapter
        set_control_message_port(adapter)

        # T19: 健康探针动态注册到 ServiceManager（control_message 晚于 service_manager 实例化）
        try:
            if self._service_manager is not None:
                self._service_manager.register_probe("control_message", adapter.health_probe)
        except Exception:
            logger.warning("ZG-8 health_probe 注册失败，跳过", exc_info=True)

        global_enabled = get_app_config_port().get_control_message_global_enabled()

        # T16: ZG-3 看门狗超时 → force 投递 EMERGENCY_STOP（spec §5.7.1 规则 3）
        async def _force_on_timeout(event: object) -> None:
            try:
                await adapter.force_send(
                    1,  # ControlMessageKind.EMERGENCY_STOP（系统级强制，IntEnum 值）
                    target_session_id="",
                    target_entity=getattr(event, "component_id", ""),
                    reason=f"watchdog timeout: {getattr(event, 'reason', '')}",
                    caller="watchdog",
                )
            except Exception:
                logger.warning("ZG-8 force 投递失败（watchdog 超时）", exc_info=True)

        def _watchdog_timeout_handler(event: object) -> None:
            asyncio.create_task(_force_on_timeout(event), name="zg8-force-timeout")

        watchdog = get_watchdog_port()
        if watchdog is not None:
            watchdog.subscribe_timeout(_watchdog_timeout_handler)

        # T17: ZG-6 系统状态机联动（DEGRADING 屏蔽调试/追踪，SHUTTING_DOWN 收紧类别）
        if self._lifecycle_sm is not None:
            self._lifecycle_sm.subscribe(self._on_system_state_change, priority=10)

        # T18: 会话生命周期回调（私有队列创建/清理 + 致命扩散）
        lifecycle = get_session_lifecycle_port()
        if lifecycle is not None:
            lifecycle.subscribe_session_created(
                lambda sid: asyncio.create_task(adapter.on_session_created(sid))
            )
            lifecycle.subscribe_session_destroyed(
                lambda sid: asyncio.create_task(adapter.on_session_destroyed(sid))
            )

        # T20: 声明核心组件 UNKILLABLE（Orchestrator 角色 = 启动编排）
        try:
            for entity in ("agent:primary", "component:orchestrator", "component:message_port"):
                await adapter.declare_unkillable(entity)
        except Exception:
            logger.warning("ZG-8 UNKILLABLE 声明失败", exc_info=True)

        logger.info(
            "ZG-8 控制消息优先级已接线（global_enabled=%s）", global_enabled
        )

    async def _on_system_state_change(
        self, from_state: object, to_state: object, reason: object
    ) -> object:
        """T17: ZG-6 状态迁移联动 — 委托适配器 apply_system_state。

        ZG-8 不维护系统状态，只订阅 ZG-6 状态变更（spec §7.6 规则 2）。
        """
        from src.core.vote import Vote

        try:
            adapter = self._control_message
            if adapter is not None:
                await adapter.apply_system_state(getattr(to_state, "name", str(to_state)))
        except Exception:
            logger.warning("ZG-8 状态联动失败", exc_info=True)
        return Vote.OK

    # ── 阶段 0 闭包 ───────────────────────────────────────────

    async def _noop_config_loaded(self) -> None:
        """阶段0占位：config_manager 已在模块级初始化，T5.1 将改为延迟初始化。"""
        pass

    async def _validate_startup_config(self) -> None:
        from src.config.config import config_manager as _cm
        from src.core.startup.validator import StartupValidator
        errors = StartupValidator.validate(global_config, _cm.get_model_config())
        if errors:
            raise ValueError(f"启动配置校验失败: {'; '.join(errors)}")

    # ── 阶段 1 闭包 ───────────────────────────────────────────

    async def _start_file_watcher(self) -> None:
        from src.config.config import config_manager as _cm
        await _cm.start_file_watcher()

    async def _run_tool_vacuum(self) -> None:
        from src.services.tool_record_cleanup_service import run_startup_tool_record_vacuum_if_needed
        await asyncio.to_thread(run_startup_tool_record_vacuum_if_needed)

    # ── 阶段 2 闭包 ───────────────────────────────────────────

    async def _init_session_submodules(self) -> None:
        from src.chat.message_receive.session_store import SessionStore
        from src.chat.message_receive.message_registry import MessageRegistry
        from src.chat.message_receive.session_name_cache import SessionNameCache
        from src.chat.message_receive.session_resolver import SessionResolver
        from src.chat.message_receive.binding_restorer import BindingRestorer
        from src.chat.message_receive.session_lifecycle import SessionLifecycle
        from src.maisaka.agent.router import AgentRouter
        from src.core.adapters.agent_config_port import get_agent_config_provider

        self._session_store = SessionStore()
        self._message_registry = MessageRegistry(self._session_store)
        self._session_store.set_message_registry(self._message_registry)
        self._name_cache = SessionNameCache(self._session_store)
        self._resolver = SessionResolver(self._session_store)
        agent_router = AgentRouter(get_agent_config_provider())
        self._binding_restorer = BindingRestorer(agent_router)
        self._session_lifecycle = SessionLifecycle(self._session_store, self._message_registry, agent_router)
        self._agent_router = agent_router

    async def _init_adapter_and_ports(self) -> None:
        from src.core.adapters.chat_manager_adapter import ChatManagerAdapter
        from src.core.adapters.routing_adapter import ChatManagerRoutingAdapter
        from src.core.session_port_registry import (
            register_session_info_port,
            register_session_lifecycle_port,
            register_session_query_port,
            register_message_registry_port,
        )
        from src.core.routing_port_registry import register_routing_service

        routing_adapter = ChatManagerRoutingAdapter(self._agent_router)
        register_routing_service(routing_adapter)
        _adapter = ChatManagerAdapter(
            routing_service=routing_adapter,
            session_store=self._session_store,
            message_registry=self._message_registry,
            name_cache=self._name_cache,
            resolver=self._resolver,
            binding_restorer=self._binding_restorer,
            session_lifecycle=self._session_lifecycle,
        )
        self._chat_manager_adapter = _adapter
        register_session_info_port(_adapter)
        register_session_lifecycle_port(_adapter)
        register_session_query_port(_adapter)
        register_message_registry_port(_adapter)

    async def _init_replyer_port(self) -> None:
        from src.chat.replyer.replyer_manager import replyer_manager
        from src.core.adapters.replyer_service_adapter import ReplyerServiceAdapter
        from src.core.replyer_port_registry import register_replyer_service_port

        adapter = ReplyerServiceAdapter(replyer_manager)
        self._replyer_adapter = adapter
        register_replyer_service_port(adapter)

    @staticmethod
    async def _init_image_port() -> None:
        from src.chat.image_system.image_manager import image_manager
        from src.core.adapters.image_description_adapter import ImageDescriptionAdapter
        from src.core.image_port_registry import register_image_description_port

        register_image_description_port(ImageDescriptionAdapter(image_manager))

    @staticmethod
    async def _init_runtime_port() -> None:
        from src.core.adapters.runtime_registry import HeartflowRuntimeRegistry
        from src.chat.heart_flow.heartflow_manager import heartflow_manager
        from src.core.runtime_port_registry import (
            register_chat_runtime_factory,
            register_chat_runtime_registry,
        )
        from src.maisaka.runtime import MaisakaRuntimeFactory

        register_chat_runtime_registry(HeartflowRuntimeRegistry(heartflow_manager))
        register_chat_runtime_factory(MaisakaRuntimeFactory())

    async def _init_agent_registry(self) -> None:
        from src.maisaka.agent.registry import AgentConfigRegistry

        self._agent_registry = AgentConfigRegistry.get_instance()
        self._agent_registry.load()

        from src.core.adapters.agent_config_port import AgentConfigProviderAdapter, set_agent_config_provider
        set_agent_config_provider(AgentConfigProviderAdapter(self._agent_registry))

    async def _init_model_config_port(self) -> None:
        from src.A_memorix.host_service import a_memorix_host_service
        from src.config.config import config_manager as _cm
        from src.core.adapters.model_config_port import ConfigManagerModelConfigPort

        self._model_config_port = ConfigManagerModelConfigPort(
            config_manager=_cm,
            agent_config_resolver=lambda aid: self._agent_registry.get_agent(aid) if self._agent_registry.has_agent(aid) else None,
        )
        a_memorix_host_service.set_model_config_port(self._model_config_port)

    @staticmethod
    async def _init_llm_service_port() -> None:
        from src.core.adapters.llm_service_port import LLMServiceAdapter, set_llm_service
        set_llm_service(LLMServiceAdapter())

    @staticmethod
    async def _init_message_ingestion_port() -> None:
        from src.chat.message_receive.bot import chat_bot
        from src.core.adapters.message_ingestion_port import ChatBotMessageIngestionPort, set_message_ingestion_port
        set_message_ingestion_port(ChatBotMessageIngestionPort(chat_bot))

    @staticmethod
    async def _init_person_info_port() -> None:
        from src.core.adapters.person_info_port import PersonInfoPortAdapter
        from src.core.person_info_port_registry import set_person_info_port
        set_person_info_port(PersonInfoPortAdapter())

    @staticmethod
    async def _init_bot_config_port() -> None:
        from src.core.adapters.bot_config_port import GlobalConfigBotConfigPort
        from src.core.bot_config_port_registry import set_bot_config_port
        set_bot_config_port(GlobalConfigBotConfigPort())

    @staticmethod
    async def _init_chat_config_port() -> None:
        from src.core.adapters.chat_config_port import GlobalConfigChatConfigPort
        from src.core.chat_config_port_registry import set_chat_config_port
        set_chat_config_port(GlobalConfigChatConfigPort())

    @staticmethod
    async def _init_app_config_port() -> None:
        from src.core.adapters.app_config_port import GlobalConfigAppConfigPort
        from src.core.app_config_port_registry import set_app_config_port
        set_app_config_port(GlobalConfigAppConfigPort())

    @staticmethod
    async def _init_event_bus_port() -> None:
        from src.maisaka.agent_autonomy.event_bus import AutonomyEventBus
        from src.core.event_bus_port_registry import set_event_bus_port
        set_event_bus_port(AutonomyEventBus())

    @staticmethod
    async def _load_prompts() -> None:
        prompt_manager.load_prompts()

    # ── 阶段 3 闭包 ───────────────────────────────────────────

    @staticmethod
    async def _start_plugin_runtime() -> None:
        from src.plugin_runtime.integration import get_plugin_runtime_manager

        manager = get_plugin_runtime_manager()
        await manager.start()

    async def _start_plugin_runtime_v2(self) -> None:
        from src.core.app_config_port_registry import get_app_config_port

        app_port = get_app_config_port()
        if not app_port.get_plugin_runtime_v2_enabled():
            logger.info("v2 插件运行时未启用，跳过")
            return
        try:
            from src.plugin_runtime_v2.bootstrap import init_v2_host_endpoint

            self._v2_host_endpoint = await init_v2_host_endpoint(app_port)
            await self._inject_scope_services_to_webui()
            logger.info("v2 插件运行时已启动")
        except Exception as e:
            logger.error("v2 插件运行时启动失败: %s", e)

    async def _inject_scope_services_to_webui(self) -> None:
        if self._v2_host_endpoint is None:
            return
        try:
            from src.webui.webui_server import get_threaded_webui_server
            webui = get_threaded_webui_server()
            if webui is not None and webui.app is not None:
                webui.app.state.scope_store = self._v2_host_endpoint._scope_store
                webui.app.state.token_service = self._v2_host_endpoint._token_service
        except Exception:
            logger.warning("操作异常 in main.py", exc_info=True)

    @staticmethod
    async def _start_a_memorix() -> None:
        from src.A_memorix.host_service import a_memorix_host_service
        from src.common.service_registry import service_registry

        service_registry.register("a_memorix_host_service", a_memorix_host_service)
        a_memorix_host_service.register_config_reload_callback()
        await a_memorix_host_service.start()

    @staticmethod
    async def _load_emoji() -> None:
        from src.emoji_system.emoji_manager import emoji_manager

        await asyncio.to_thread(emoji_manager.load_emojis_from_db)

    async def _inject_model_config_port(self) -> None:
        from src.llm_models import model_client
        from src.llm_models import utils_model
        from src.services import service_task_resolver

        utils_model.set_model_config_port(self._model_config_port)
        model_client.base_client.set_model_config_port(self._model_config_port)
        model_client.set_model_config_port(self._model_config_port)
        service_task_resolver.set_model_config_port(self._model_config_port)

    # ── 阶段 4 闭包 ───────────────────────────────────────────

    @staticmethod
    async def _restore_sessions() -> None:
        from src.core.session_port_registry import get_session_lifecycle_port

        lifecycle_port = get_session_lifecycle_port()
        await lifecycle_port.initialize()
        asyncio.create_task(lifecycle_port.regularly_save_sessions())

    @staticmethod
    async def _start_memory_automation() -> None:
        from src.services.memory_flow_service import memory_automation_service

        await memory_automation_service.start()

    # ── 阶段 5 闭包 ───────────────────────────────────────────

    async def _register_handlers(self) -> None:
        self._register_message_handlers()

    @staticmethod
    async def _emit_on_start() -> None:
        from src.core.event_bus import event_bus
        from src.core.types import EventType

        await event_bus.emit(event_type=EventType.ON_START)

    async def _start_webui(self) -> None:
        self._start_webui_server()

    @staticmethod
    async def _add_scheduled_tasks() -> None:
        from src.chat.utils.statistic import OnlineTimeRecordTask, StatisticOutputTask

        await async_task_manager.add_task(OnlineTimeRecordTask())
        await async_task_manager.add_task(StatisticOutputTask())

    async def _start_interaction_scheduler(self) -> None:
        try:
            from src.maisaka.agent_interaction.bootstrap import build_interaction_scheduler
            from src.maisaka.agent_interaction.relationship_manager import AgentRelationshipManager
            from src.core.adapters import get_memory_service_port

            scheduler = build_interaction_scheduler(get_memory_service_port())
            if scheduler is not None:
                relationship_mgr = AgentRelationshipManager()
                await relationship_mgr.initialize_from_config()
                await scheduler.start()
                self._interaction_scheduler = scheduler
                logger.info(t("startup.agent_interaction_started"))
        except Exception as e:
            logger.warning(t("startup.agent_interaction_failed", error=e))

    async def schedule_tasks(self) -> None:

        """调度定时任务"""
        try:
            from src.chat.image_system.image_cache_cleanup import periodic_image_cache_cleanup
            from src.emoji_system.emoji_cache_cleanup import periodic_emoji_cache_cleanup
            from src.emoji_system.emoji_manager import emoji_manager
            from src.services.image_path_maintenance_service import (
                run_image_path_maintenance_background,
                should_schedule_image_path_maintenance_background,
            )

            if self.app is None or self.server is None:
                raise RuntimeError("消息服务未初始化")

            tasks = [
                emoji_manager.periodic_emoji_maintenance(),
                periodic_emoji_cache_cleanup(),
                periodic_image_cache_cleanup(),
                self.app.run(),
                self.server.run(),
            ]
            image_path_maintenance_needed = await asyncio.to_thread(should_schedule_image_path_maintenance_background)
            if image_path_maintenance_needed:
                tasks.append(run_image_path_maintenance_background())

            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            logger.info(t("startup.schedule_cancelled"))
            raise


async def main() -> None:
    """主函数"""
    set_main_loop(asyncio.get_running_loop())
    from src.config.config import initialize_config
    initialize_config()
    system = MainSystem()
    try:
        await system.initialize()

        # ZG-6 W2: SIGTERM/SIGINT → SHUTTING_DOWN（幂等）+ 联动主循环退出。
        # 后注册覆盖 ZG-2 crash_dump / ZG-6 适配器的 signal handler，生产走优雅关闭链：
        # trigger_shutdown 通知订阅者 → gather 被打断 → finally 执行现有关闭链。
        import signal as _signal

        main_task = asyncio.current_task()

        def _on_terminate_signal() -> None:
            asyncio.create_task(system._lifecycle_adapter.trigger_shutdown())
            if main_task is not None and not main_task.done():
                main_task.cancel()

        for _sig in (_signal.SIGTERM, _signal.SIGINT):
            try:
                asyncio.get_running_loop().add_signal_handler(_sig, _on_terminate_signal)
            except NotImplementedError:
                pass  # 仅主线程可用；不可用则保留适配器兜底 handler

        await system.schedule_tasks()
    finally:
        if system._watchdog_touch_task is not None:
            system._watchdog_touch_task.cancel()
            try:
                await system._watchdog_touch_task
            except asyncio.CancelledError:
                pass
        if system._watchdog is not None:
            await system._watchdog.stop()
        if system._service_manager is not None:
            await system._service_manager.shutdown()
        if system._interaction_scheduler is not None:
            await system._interaction_scheduler.stop()
        if system.webui_server:
            await system.webui_server.shutdown()
        from src.common.service_registry import service_registry
        from src.emoji_system.emoji_manager import emoji_manager
        from src.plugin_runtime.integration import get_plugin_runtime_manager
        from src.services.memory_flow_service import memory_automation_service

        emoji_manager.shutdown()
        await memory_automation_service.shutdown()
        if service_registry.has("a_memorix_host_service"):
            await service_registry.get("a_memorix_host_service").stop()
        if system._v2_host_endpoint is not None:
            await system._v2_host_endpoint.stop()
        await get_plugin_runtime_manager().bridge_event("on_stop")
        await get_plugin_runtime_manager().stop()
        await async_task_manager.stop_and_wait_all_tasks()
        from src.config.config import config_manager as _cm
        await _cm.stop_file_watcher()
        set_main_loop(None)


if __name__ == "__main__":
    asyncio.run(main())
