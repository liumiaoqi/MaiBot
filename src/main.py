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
from src.core.service_manager.types import DependencyKind

from src.core.startup import StartupPhase, startup_item
from src.manager.async_task_manager import async_task_manager
from src.prompt.prompt_manager import prompt_manager

def run_model_config_check() -> int:
    """--check-model-config：校验注册表 + @model_requirement 声明后退出。

    对标 Linux device probe：声明不可满足 → 可见地不可用（不假装驱动了设备）。

    Returns:
        0 = 全部满足；1 = 非 critical 声明降级；2 = critical 声明不满足（拒绝启动）
    """
    from src.config.config import MODEL_CONFIG_PATH, MODEL_CONFIG_VERSION, ModelConfig, load_config_from_file
    from src.core.adapters.model_config_port import ConfigManagerModelConfigPort as _Port
    from src.llm_models.declaration_validator import DeclarationValidator, STATUS_FAST_FAIL
    from src.llm_models.model_registry import ModelRegistry

    # 收集全部 @model_requirement 声明（import 声明模块触发注册）
    _DECLARATION_MODULES = (
        "src.maisaka.agent_autonomy.thinking_organ",
        "src.maisaka.agent_autonomy.butler",
        "src.maisaka.agent_autonomy.reminder",
        "src.maisaka.replyer.generator_base",
        "src.maisaka.builtin_tool.send_emoji",
        "src.services.embedding_service",
        "src.emoji_system.emoji_manager",
        "src.chat.image_system.image_manager",
        "src.common.utils.utils_voice",
        "src.learners.jargon_learner",
        "src.learners.expression_learner",
        "src.learners.jargon_miner",
        "src.A_memorix.core.runtime.sdk_memory_kernel",
        "src.maisaka.memory.heuristic_injector",
        "src.services.memory_flow_service",
        "src.maisaka.memory.mid_term",
    )
    import importlib

    for module_name in _DECLARATION_MODULES:
        try:
            importlib.import_module(module_name)
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, "声明模块导入失败，组件声明未收集", exception=exc)
            print(f"  ⚠️ 声明模块 {module_name} 导入失败（该组件声明未收集）: {exc}")

    model_config, _ = load_config_from_file(
        ModelConfig, MODEL_CONFIG_PATH, MODEL_CONFIG_VERSION, override_repr=True,
    )
    registry = ModelRegistry()
    entries = [_Port._to_entry(m) for m in model_config.models]
    registry.build_index(list(model_config.api_providers), entries)

    report = DeclarationValidator().validate_all_declarations(registry)
    print("=" * 60)
    print("模型配置校验（--check-model-config）")
    print("=" * 60)
    for item in report.items:
        mark = {"passed": "✅", "fast_fail": "❌", "degraded": "⚠️"}.get(item.status, "?")
        detail = item.detail or f"解析到 ({item.resolved_model})"
        print(f"  {mark} {item.component_name}: {detail}")
    print("-" * 60)
    print(f"结果: {report.status}（{len(report.items)} 项声明）")
    if report.status == STATUS_FAST_FAIL:
        print(f"  critical 声明不可满足: {report.fast_fail_components}")
        return 2
    if report.degraded_components:
        return 1
    return 0


# from src.api.main import start_api_server

# 导入插件运行时
# 导入消息API和traceback模块
# from src.chat.utils.token_statistics import TokenStatisticsTask

install(extra_lines=3)

logger = get_logger("main")

# ZG-10 迁移适配：@startup_item 在类定义期收集零参 init_fn（StartupItemDesc 无参约定）。
# MainSystem 方法若需实例状态，通过模块级 _main_system 闭包引用取当前实例——
# 生产路径 main()/bot.py 均为"先构造 MainSystem 再 initialize()"，单实例场景成立。
_main_system: "MainSystem | None" = None


def _require_main_system() -> "MainSystem":
    """返回当前 MainSystem 实例（零参 init_fn 的实例状态入口）。"""
    system = _main_system
    if system is None:
        raise RuntimeError("MainSystem 实例尚未创建，启动项无法访问实例状态")
    return system


if TYPE_CHECKING:
    from maim_message import MessageServer
    from src.common.message_server.server import Server
    from src.webui.webui_server import ThreadedWebUIServer


class MainSystem:
    def __init__(self, debug_startup: bool = False, skip_startup_items: set[str] | None = None) -> None:
        global _main_system
        _main_system = self
        self._debug_startup = debug_startup
        self._skip_startup_items = set(skip_startup_items or ())
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
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.ERROR, "启动 WebUI 服务失败", exception=e)
            logger.error(t("startup.webui_server_init_failed", error=e))

    async def initialize(self) -> None:
        """初始化系统组件"""
        logger.info(t("startup.waking_up", nickname=global_config.bot.nickname))

        try:
            await self._init_components()
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.CRITICAL, "主系统初始化异常", exception=exc)
            logger.warning("操作异常 in main.py", exc_info=True)
            if self.webui_server:
                await self.webui_server.shutdown()
            raise

        logger.info(t("startup.initialization_completed_banner", nickname=global_config.bot.nickname))

    # ── 启动编排（SSD-4 startup_reform T2.2）──────────────────

    async def _init_components(self) -> None:
        """使用 StartupOrchestrator 按 6 阶段执行初始化。

        启动项已迁移为 init_fn 定义处的 @startup_item 装饰器声明
        （ZG-10 T20-T29）；StartupComponent 兼容注册入口已在收尾批次移除。
        """
        from src.core.startup import StartupOrchestrator

        self._init_start_time = time.time()
        orchestrator = StartupOrchestrator(
            debug_mode=self._debug_startup,
            skip_names=self._skip_startup_items,
        )

        self._orchestrator = orchestrator
        self._startup_result = await orchestrator.run()

        if not self._startup_result.ready:
            failed_names = list(self._startup_result.failed_components)
            if failed_names:
                raise RuntimeError(f"关键组件初始化失败: {failed_names}")
            logger.warning(f"系统降级启动，失败组件: {failed_names}")

        # ZG-1: 服务管理器接管运行时组件（adopt——ServiceManagerAdapter 构造与
        # ServiceManagerPort 注册已移入 CORE_SERVICES 相位 watchdog 启动项；
        # adopt_from_startup 需 StartupResult，只能在 run() 完成后执行）
        from src.core.service_manager.descriptors import (
            get_dependency_relations,
            get_service_descriptors,
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

        # ZG-3: V1 Runner 批量注册到看门狗桥接（watchdog 本体已由 CORE_SERVICES
        # ZG-32: v1 plugin runtime disabled, V1 看门狗注册跳过
        logger.info("v1 plugin runtime disabled, skip watchdog registration")
        # try:
        #     from src.plugin_runtime.integration import get_plugin_runtime_manager
        #
        #     for sv in get_plugin_runtime_manager().supervisors:
        #         self._watchdog.register_v1_supervisor(
        #             f"v1-{sv.group_name}", sv, "plugin_runtime",
        #         )
        # except Exception as exc:
        #     from src.core.error_escalation.types import ErrorLevel
        #     from src.core.error_escalation_port_registry import get_error_escalation_port
        #     port = get_error_escalation_port()
        #     if port is not None:
        #         port.report(ErrorLevel.WARNING, "V1 Runner 注册到看门狗桥接失败，已降级跳过", exception=exc)
        #     logger.warning(
        #         "V1 Runner 注册到看门狗桥接失败，已降级跳过", exc_info=True
        #     )

        # ZG-8: 控制消息优先级接线（适配器实例化 + 订阅 + force 触发 + 状态联动）
        await self._init_control_message()

        # ZG-7: 污染标记接线（适配器实例化 + 注册 + CrashDump 注入）
        await self._init_tainted_mask()

        # ZG-14: 错误升级梯接线（依赖 ZG-7/ZG-8 已注入）
        await self._init_error_escalation()

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
                    return await supervisor.kill_runner(plugin_id)
                except Exception as exc:
                    from src.core.error_escalation.types import ErrorLevel
                    from src.core.error_escalation_port_registry import get_error_escalation_port
                    port = get_error_escalation_port()
                    if port is not None:
                        port.report(ErrorLevel.WARNING, "ZG-5 OOM 杀除失败", exception=exc)
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
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, "ZG-5 资源限制接线失败，已降级跳过", exception=exc)
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
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, "ZG-7 接线依赖导入失败，已降级跳过", exception=exc)
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
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, "ZG-7 CrashDump 注入失败，污染行跳过", exception=exc)
            logger.warning("ZG-7 CrashDump 注入失败，污染行跳过", exc_info=True)

        logger.info("ZG-7 污染标记已接线")

        # TAINT_PORT_BYPASS（位0）运行时守卫：检查核心模块是否违规导入禁止项
        self._check_port_bypass_violations()

    async def _init_error_escalation(self) -> None:
        """ZG-14 错误升级梯接线（适配器实例化 + 各 Port 注入 + 注册 + ZG-7 委托）。

        依赖：app_config / tainted_mask / lifecycle_sm / service_manager /
        event_bus / control_message / crash_dump / rate_limiter 均已就绪
        （在 _init_control_message 与 _init_tainted_mask 之后接线）。
        注入失败时 ZG-7 回退独立运行（spec §5.9.3 异常场景 1）。
        """
        try:
            from src.common.logger import _crash_dump, _rate_limiter
            from src.core.app_config_port_registry import get_app_config_port
            from src.core.control_message_port_registry import get_control_message_port
            from src.core.error_escalation.adapter import ErrorEscalationAdapter
            from src.core.error_escalation_port_registry import set_error_escalation_port
            from src.core.event_bus_port_registry import get_event_bus_port
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, "ZG-14 接线依赖导入失败，已降级跳过（ZG-7 独立运行）", exception=exc)
            logger.warning("ZG-14 接线依赖导入失败，已降级跳过（ZG-7 独立运行）", exc_info=True)
            return

        adapter = ErrorEscalationAdapter(
            app_config_port=get_app_config_port(),
            taint_mask_port=self._taint_mask,
            state_machine_port=self._lifecycle_sm,
            service_manager_port=self._service_manager,
            event_bus_port=get_event_bus_port(),
            crash_dump_port=_crash_dump,
            rate_limiter_port=_rate_limiter,
            control_message_port=get_control_message_port(),
        )
        self._error_escalation = adapter
        set_error_escalation_port(adapter)

        # ZG-7 委托注入：warn_count 达阈委托升级梯（spec §5.9.1）
        if self._taint_mask is not None:
            try:
                self._taint_mask.set_error_escalation_port(adapter)
            except Exception as exc:
                from src.core.error_escalation.types import ErrorLevel
                from src.core.error_escalation_port_registry import get_error_escalation_port
                port = get_error_escalation_port()
                if port is not None:
                    port.report(ErrorLevel.WARNING, "ZG-7 委托注入失败，回退独立运行", exception=exc)
                logger.warning("ZG-7 委托注入失败，回退独立运行", exc_info=True)

        logger.info("ZG-14 错误升级梯已接线")

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
                except Exception as exc:
                    from src.core.error_escalation.types import ErrorLevel
                    from src.core.error_escalation_port_registry import get_error_escalation_port
                    port = get_error_escalation_port()
                    if port is not None:
                        port.report(ErrorLevel.WARNING, "检查模块文件路径失败", exception=exc)
                    continue
                for name, obj in getattr(mod, "__dict__", {}).items():
                    if name.startswith("_"):
                        continue
                    obj_module = getattr(obj, "__module__", None)
                    # 排除模块自身定义的对象（obj_module == mod_name）——
                    # 适配器模块里定义的类 __module__ 等于自身，误判"违规导入自自身"
                    if obj_module and obj_module != mod_name and _is_banned(obj_module):
                        mark_taint(TaintFlag.TAINT_PORT_BYPASS)
                        logger.warning("ZG-7 守卫: %s.%s 违规导入自 %s", mod_name, name, obj_module)
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, "端口绕过违规检查失败", exception=exc)
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
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, "ZG-8 接线依赖导入失败，已降级跳过", exception=exc)
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
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, "ZG-8 health_probe 注册失败，跳过", exception=exc)
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
            except Exception as exc:
                from src.core.error_escalation.types import ErrorLevel
                from src.core.error_escalation_port_registry import get_error_escalation_port
                port = get_error_escalation_port()
                if port is not None:
                    port.report(ErrorLevel.WARNING, "ZG-8 force 投递失败（watchdog 超时）", exception=exc)
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
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, "ZG-8 UNKILLABLE 声明失败", exception=exc)
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
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, "ZG-8 状态联动失败", exception=exc)
            logger.warning("ZG-8 状态联动失败", exc_info=True)
        return Vote.OK

    # ── 阶段 0 闭包 ───────────────────────────────────────────

    @staticmethod
    @startup_item(
        name="config_manager",
        phase=StartupPhase.CONFIG_LOAD,
        order=0,
        critical=True,
    )
    async def _noop_config_loaded() -> None:
        """阶段0占位：config_manager 已在模块级初始化，T5.1 将改为延迟初始化。"""
        pass

    @staticmethod
    @startup_item(
        name="config_validator",
        phase=StartupPhase.CONFIG_LOAD,
        order=1,
        critical=True,
        depends_on=["config_manager"],
        dependency_kind={"config_manager": DependencyKind.STRONG},
    )
    async def _validate_startup_config() -> None:
        from src.config.config import config_manager as _cm
        from src.core.startup.validator import StartupValidator
        errors = StartupValidator.validate(global_config, _cm.get_model_config())
        if errors:
            raise ValueError(f"启动配置校验失败: {'; '.join(errors)}")

    # ── 阶段 1 闭包 ───────────────────────────────────────────

    @staticmethod
    @startup_item(
        name="file_watcher",
        phase=StartupPhase.INFRASTRUCTURE,
        order=0,
        critical=True,
        depends_on=["config_manager"],
        dependency_kind={"config_manager": DependencyKind.STRONG},
    )
    async def _start_file_watcher() -> None:
        from src.config.config import config_manager as _cm
        await _cm.start_file_watcher()

    @staticmethod
    @startup_item(
        name="tool_record_vacuum",
        phase=StartupPhase.INFRASTRUCTURE,
        order=1,
        critical=False,
    )
    async def _run_tool_vacuum() -> None:
        from src.services.tool_record_cleanup_service import run_startup_tool_record_vacuum_if_needed
        await asyncio.to_thread(run_startup_tool_record_vacuum_if_needed)

    # ── 阶段 2 闭包 ───────────────────────────────────────────

    @staticmethod
    @startup_item(
        name="session_submodules",
        phase=StartupPhase.CORE_SERVICES,
        order=1,
        critical=True,
        depends_on=["agent_registry"],
        dependency_kind={"agent_registry": DependencyKind.STRONG},
    )
    async def _init_session_submodules() -> None:
        system = _require_main_system()
        from src.chat.message_receive.session_store import SessionStore
        from src.chat.message_receive.message_registry import MessageRegistry
        from src.chat.message_receive.session_name_cache import SessionNameCache
        from src.chat.message_receive.session_resolver import SessionResolver
        from src.chat.message_receive.binding_restorer import BindingRestorer
        from src.chat.message_receive.session_lifecycle import SessionLifecycle
        from src.maisaka.agent.router import AgentRouter
        from src.core.adapters.agent_config_port import get_agent_config_provider

        system._session_store = SessionStore()
        system._message_registry = MessageRegistry(system._session_store)
        system._session_store.set_message_registry(system._message_registry)
        system._name_cache = SessionNameCache(system._session_store)
        system._resolver = SessionResolver(system._session_store)
        agent_router = AgentRouter(get_agent_config_provider())
        system._binding_restorer = BindingRestorer(agent_router)
        system._session_lifecycle = SessionLifecycle(
            system._session_store, system._message_registry, agent_router
        )
        system._agent_router = agent_router

    @staticmethod
    @startup_item(
        name="chat_manager_adapter",
        phase=StartupPhase.CORE_SERVICES,
        order=2,
        critical=True,
        depends_on=["session_submodules", "agent_registry"],
        dependency_kind={
            "session_submodules": DependencyKind.STRONG,
            "agent_registry": DependencyKind.STRONG,
        },
        core_readiness_flag="message_pipeline_ready",
    )
    async def _init_adapter_and_ports() -> None:
        system = _require_main_system()
        from src.core.adapters.chat_manager_adapter import ChatManagerAdapter
        from src.core.adapters.routing_adapter import ChatManagerRoutingAdapter
        from src.core.session_port_registry import (
            register_session_info_port,
            register_session_lifecycle_port,
            register_session_query_port,
            register_message_registry_port,
        )
        from src.core.routing_port_registry import register_routing_service

        routing_adapter = ChatManagerRoutingAdapter(system._agent_router)
        register_routing_service(routing_adapter)
        _adapter = ChatManagerAdapter(
            routing_service=routing_adapter,
            session_store=system._session_store,
            message_registry=system._message_registry,
            name_cache=system._name_cache,
            resolver=system._resolver,
            binding_restorer=system._binding_restorer,
            session_lifecycle=system._session_lifecycle,
        )
        system._chat_manager_adapter = _adapter
        register_session_info_port(_adapter)
        register_session_lifecycle_port(_adapter)
        register_session_query_port(_adapter)
        register_message_registry_port(_adapter)

    @staticmethod
    @startup_item(
        name="replyer_port",
        phase=StartupPhase.CORE_SERVICES,
        order=3,
        critical=True,
        depends_on=["chat_manager_adapter", "agent_registry"],
        dependency_kind={
            "chat_manager_adapter": DependencyKind.STRONG,
            "agent_registry": DependencyKind.STRONG,
        },
        core_readiness_flag="reply_capability_ready",
    )
    async def _init_replyer_port() -> None:
        system = _require_main_system()
        from src.chat.replyer.replyer_manager import replyer_manager
        from src.core.adapters.replyer_service_adapter import ReplyerServiceAdapter
        from src.core.replyer_port_registry import register_replyer_service_port

        adapter = ReplyerServiceAdapter(replyer_manager)
        system._replyer_adapter = adapter
        register_replyer_service_port(adapter)

    @staticmethod
    @startup_item(
        name="image_port",
        phase=StartupPhase.CORE_SERVICES,
        order=4,
        critical=True,
    )
    async def _init_image_port() -> None:
        from src.chat.image_system.image_manager import image_manager
        from src.core.adapters.image_description_adapter import ImageDescriptionAdapter
        from src.core.image_port_registry import register_image_description_port

        register_image_description_port(ImageDescriptionAdapter(image_manager))

    @staticmethod
    @startup_item(
        name="runtime_port",
        phase=StartupPhase.CORE_SERVICES,
        order=5,
        critical=True,
    )
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

    @staticmethod
    @startup_item(
        name="agent_registry",
        phase=StartupPhase.CORE_SERVICES,
        order=0,
        critical=True,
        core_readiness_flag="agent_thinking_ready",
    )
    async def _init_agent_registry() -> None:
        system = _require_main_system()
        from src.maisaka.agent.registry import AgentConfigRegistry

        system._agent_registry = AgentConfigRegistry.get_instance()
        system._agent_registry.load()

        from src.core.adapters.agent_config_port import AgentConfigProviderAdapter, set_agent_config_provider
        set_agent_config_provider(AgentConfigProviderAdapter(system._agent_registry))

    @staticmethod
    @startup_item(
        name="model_config_port",
        phase=StartupPhase.CORE_SERVICES,
        order=6,
        critical=True,
        depends_on=["agent_registry", "config_manager"],
        dependency_kind={
            "agent_registry": DependencyKind.STRONG,
            "config_manager": DependencyKind.STRONG,
        },
    )
    async def _init_model_config_port() -> None:
        system = _require_main_system()
        from src.A_memorix.host_service import a_memorix_host_service
        from src.config.config import config_manager as _cm
        from src.core.adapters.model_config_port import ConfigManagerModelConfigPort

        system._model_config_port = ConfigManagerModelConfigPort(
            config_manager=_cm,
            agent_config_resolver=lambda aid: (
                system._agent_registry.get_agent(aid)
                if system._agent_registry.has_agent(aid)
                else None
            ),
        )
        a_memorix_host_service.set_model_config_port(system._model_config_port)

    @staticmethod
    @startup_item(
        name="llm_service_port",
        phase=StartupPhase.CORE_SERVICES,
        order=7,
        critical=True,
    )
    async def _init_llm_service_port() -> None:
        from src.core.adapters.llm_service_port import LLMServiceAdapter, set_llm_service
        set_llm_service(LLMServiceAdapter())

    @staticmethod
    @startup_item(
        name="message_ingestion_port",
        phase=StartupPhase.CORE_SERVICES,
        order=8,
        critical=True,
        depends_on=["chat_manager_adapter"],
        dependency_kind={"chat_manager_adapter": DependencyKind.STRONG},
    )
    async def _init_message_ingestion_port() -> None:
        from src.chat.message_receive.bot import chat_bot
        from src.core.adapters.message_ingestion_port import ChatBotMessageIngestionPort, set_message_ingestion_port
        set_message_ingestion_port(ChatBotMessageIngestionPort(chat_bot))

    @staticmethod
    @startup_item(
        name="person_info_port",
        phase=StartupPhase.CORE_SERVICES,
        order=9,
        critical=True,
    )
    async def _init_person_info_port() -> None:
        from src.core.adapters.person_info_port import PersonInfoPortAdapter
        from src.core.person_info_port_registry import set_person_info_port
        set_person_info_port(PersonInfoPortAdapter())

    @staticmethod
    @startup_item(
        name="bot_config_port",
        phase=StartupPhase.CORE_SERVICES,
        order=10,
        critical=True,
        depends_on=["config_manager"],
        dependency_kind={"config_manager": DependencyKind.STRONG},
    )
    async def _init_bot_config_port() -> None:
        from src.core.adapters.bot_config_port import GlobalConfigBotConfigPort
        from src.core.bot_config_port_registry import set_bot_config_port
        set_bot_config_port(GlobalConfigBotConfigPort())

    @staticmethod
    @startup_item(
        name="chat_config_port",
        phase=StartupPhase.CORE_SERVICES,
        order=11,
        critical=True,
        depends_on=["config_manager"],
        dependency_kind={"config_manager": DependencyKind.STRONG},
    )
    async def _init_chat_config_port() -> None:
        from src.core.adapters.chat_config_port import GlobalConfigChatConfigPort
        from src.core.chat_config_port_registry import set_chat_config_port
        set_chat_config_port(GlobalConfigChatConfigPort())

    @staticmethod
    @startup_item(
        name="app_config_port",
        phase=StartupPhase.CORE_SERVICES,
        order=12,
        critical=True,
        depends_on=["config_manager"],
        dependency_kind={"config_manager": DependencyKind.STRONG},
    )
    async def _init_app_config_port() -> None:
        from src.core.adapters.app_config_port import GlobalConfigAppConfigPort
        from src.core.app_config_port_registry import set_app_config_port
        set_app_config_port(GlobalConfigAppConfigPort())

    @staticmethod
    @startup_item(
        name="event_bus_port",
        phase=StartupPhase.CORE_SERVICES,
        order=13,
        critical=True,
    )
    async def _init_event_bus_port() -> None:
        from src.maisaka.agent_autonomy.event_bus import AutonomyEventBus
        from src.core.event_bus_port_registry import set_event_bus_port

        # ZG-21: AutonomyEventBus 启动 SoftirqBatcher drainer（事件循环已运行）
        _autonomy_bus = AutonomyEventBus()
        set_event_bus_port(_autonomy_bus)
        _autonomy_bus.start()

        # ZG-4: EventBus 装配注入（配置已加载后；configure 幂等，未注入项保持默认）。
        # P1-1 修复：configure 从 run() 之后移入 CORE_SERVICES 相位，保证 on_start_event
        # 触发时 EventBus 已配置完成（T22/T24）。
        from src.config.config import config_manager as _cm
        from src.core.event_bus import event_bus as _core_event_bus

        event_bus_cfg = _cm.get_global_config().event_bus
        _core_event_bus.configure(
            rollback_timeout=event_bus_cfg.rollback_timeout,
            vote_history_capacity=event_bus_cfg.vote_history_capacity,
        )
        # ZG-21: 核心 EventBus 启动 SoftirqBatcher drainer
        _core_event_bus.start()

    @staticmethod
    @startup_item(
        name="prompt_manager",
        phase=StartupPhase.CORE_SERVICES,
        order=14,
        critical=True,
    )
    async def _load_prompts() -> None:
        prompt_manager.load_prompts()

    # ── 阶段 3 闭包 ───────────────────────────────────────────

    # ZG-32: v1 插件运行时已废弃（2026-08-18），收敛到 v2 单一运行时
    # 对齐 dsh Cordis 单一运行时模型（设计参考铁律——智能体类标注 dsh 源码参考）
    # v1 源码保留（v1-compat 依赖 v1 runner 桥接），仅禁用启动
    # 若需恢复 v1，取消下方注释即可（生命周期可逆，对齐 dsh agent-lifecycle）
    logger.info("v1 plugin runtime disabled (ZG-32), converged to v2 single runtime")
    # @startup_item(
    #     name="plugin_runtime",
    #     phase=StartupPhase.SUBSYSTEMS,
    #     order=0,
    #     critical=False,
    #     depends_on=["llm_service_port"],
    #     dependency_kind={"llm_service_port": DependencyKind.WEAK},
    # )
    # async def _start_plugin_runtime() -> None:
    #     from src.plugin_runtime.integration import get_plugin_runtime_manager
    #
    #     manager = get_plugin_runtime_manager()
    #     await manager.start()

    @staticmethod
    @startup_item(
        name="plugin_runtime_v2",
        phase=StartupPhase.SUBSYSTEMS,
        order=2,
        critical=False,
        depends_on=["app_config_port", "llm_service_port"],
        dependency_kind={
            "app_config_port": DependencyKind.STRONG,
            "llm_service_port": DependencyKind.WEAK,
        },
    )
    async def _start_plugin_runtime_v2() -> None:
        system = _require_main_system()
        from src.core.app_config_port_registry import get_app_config_port

        app_port = get_app_config_port()
        if not app_port.get_plugin_runtime_v2_enabled():
            logger.info("v2 插件运行时未启用，跳过")
            return
        try:
            from src.plugin_runtime_v2.bootstrap import init_v2_host_endpoint

            system._v2_host_endpoint = await init_v2_host_endpoint(app_port)
            await system._inject_scope_services_to_webui()
            logger.info("v2 插件运行时已启动")
        except Exception as e:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.ERROR, "v2 插件运行时启动失败", exception=e)
            logger.error("v2 插件运行时启动失败: %s", e)

    async def _stop_plugin_runtime_v2(self) -> None:
        """ZG-15：plugin_runtime_v2 组件 stop——发 ShutdownRequest 排空 + 停 endpoint。

        Runner 端 _handle_shutdown 已改造为 mark_going → wait_drained →
        unload_plugin（引用计数驱动排空，非固定 sleep）。
        """
        endpoint = getattr(self, "_v2_host_endpoint", None)
        if endpoint is None:
            return
        try:
            await endpoint.stop()
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, "v2 插件运行时停止异常", exception=exc)
            logger.warning("v2 插件运行时停止异常: %s", exc)

    async def _start_plugin_runtime_v2_stub(self) -> None:
        """ZG-15：start_fn 占位（组件由 startup_item 启动，start_fn 仅满足 actions 契约）。"""

    async def _inject_scope_services_to_webui(self) -> None:
        if self._v2_host_endpoint is None:
            return
        try:
            from src.webui.webui_server import get_threaded_webui_server
            webui = get_threaded_webui_server()
            webui_inner = getattr(webui, "_server", None) if webui is not None else None
            if webui_inner is not None and webui_inner.app is not None:
                webui_inner.app.state.scope_store = self._v2_host_endpoint._scope_store
                webui_inner.app.state.token_service = self._v2_host_endpoint._token_service
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, "注入 WebUI 作用域服务失败", exception=exc)
            logger.warning("操作异常 in main.py", exc_info=True)

    @staticmethod
    @startup_item(
        name="a_memorix",
        phase=StartupPhase.SUBSYSTEMS,
        order=5,
        critical=False,
        depends_on=["model_config_port_inject", "model_config_port"],
        dependency_kind={
            "model_config_port_inject": DependencyKind.STRONG,
            "model_config_port": DependencyKind.STRONG,
        },
    )
    async def _start_a_memorix() -> None:
        from src.A_memorix.host_service import a_memorix_host_service
        from src.common.service_registry import service_registry

        service_registry.register("a_memorix_host_service", a_memorix_host_service)
        a_memorix_host_service.register_config_reload_callback()
        await a_memorix_host_service.start()

    @staticmethod
    @startup_item(
        name="emoji_manager",
        phase=StartupPhase.SUBSYSTEMS,
        order=3,
        critical=False,
        depends_on=["llm_service_port"],
        dependency_kind={"llm_service_port": DependencyKind.WEAK},
    )
    async def _load_emoji() -> None:
        from src.emoji_system.emoji_manager import emoji_manager

        await asyncio.to_thread(emoji_manager.load_emojis_from_db)

    @staticmethod
    @startup_item(
        name="model_config_port_inject",
        phase=StartupPhase.SUBSYSTEMS,
        order=4,
        critical=False,
    )
    async def _inject_model_config_port() -> None:
        system = _require_main_system()
        from src.llm_models import model_client
        from src.llm_models import utils_model
        from src.services import service_task_resolver

        utils_model.set_model_config_port(system._model_config_port)
        model_client.base_client.set_model_config_port(system._model_config_port)
        model_client.set_model_config_port(system._model_config_port)
        service_task_resolver.set_model_config_port(system._model_config_port)

    @staticmethod
    @startup_item(
        name="model_declaration_validator",
        phase=StartupPhase.SUBSYSTEMS,
        order=6,
        critical=True,
        depends_on=["model_config_port_inject", "model_config_port"],
        dependency_kind={
            "model_config_port_inject": DependencyKind.STRONG,
            "model_config_port": DependencyKind.STRONG,
        },
    )
    async def _validate_model_declarations() -> None:
        """启动需求校验（P1-7）：critical 声明不可满足 → 拒绝启动。

        对标 Linux device probe：声明错误 fast-fail，不假装驱动了设备。
        """
        system = _require_main_system()
        port = system._model_config_port
        if port is None:
            raise RuntimeError("ModelConfigPort 未注入，无法执行模型声明校验")
        from src.core.adapters.model_config_port import ConfigManagerModelConfigPort as _Port
        from src.llm_models.declaration_validator import STATUS_FAST_FAIL, DeclarationValidator
        from src.llm_models.model_registry import ModelRegistry

        registry = ModelRegistry()
        model_config = port.get_model_config()
        entries = [_Port._to_entry(m) for m in model_config.models]
        registry.build_index(list(model_config.api_providers), entries)
        report = DeclarationValidator().validate_all_declarations(registry)
        if report.status == STATUS_FAST_FAIL:
            raise RuntimeError(
                f"模型需求校验失败（critical 声明不可满足，拒绝启动）: "
                f"{report.fast_fail_components}"
            )
        if report.degraded_components:
            logger.warning(f"模型需求校验：非 critical 声明降级: {report.degraded_components}")

    @staticmethod
    @startup_item(
        name="message_port_v2",
        phase=StartupPhase.CORE_SERVICES,
        order=15,
        critical=True,
    )
    async def _inject_message_port_v2() -> None:
        from src.core.message_port_registry import set_message_port_v2
        from src.services.send_service import SendServiceMessagePortV2

        set_message_port_v2(SendServiceMessagePortV2())

    @staticmethod
    @startup_item(
        name="watchdog",
        phase=StartupPhase.CORE_SERVICES,
        order=16,
        critical=True,
        depends_on=["app_config_port", "agent_registry", "chat_manager_adapter", "replyer_port"],
        dependency_kind={
            "app_config_port": DependencyKind.STRONG,
            "agent_registry": DependencyKind.STRONG,
            "chat_manager_adapter": DependencyKind.STRONG,
            "replyer_port": DependencyKind.STRONG,
        },
    )
    async def _init_watchdog_and_service_manager() -> None:
        """ZG-3: ServiceManagerPort 注册 + 看门狗启动（CORE_SERVICES 相位）。

        ZG-10 遗留 1：从 _init_components post-startup 段移入启动编排——
        SUBSYSTEMS 相位组件（V2 Runner 注册看门狗等）早于 watchdog 注册，
        每次启动刷「WatchdogPort 未注册」降级日志；提前注册后 SUBSYSTEMS 可见。

        ServiceManagerAdapter 仅构造 + 注册 Port（adopt_from_startup 需
        StartupResult，留在 run() 之后执行）；V1 Runner 批量注册依赖
        plugin_runtime 已启动（SUBSYSTEMS 相位），留在 _init_components。
        看门狗 touch 循环（长驻 task）在 init_fn 内创建后返回，不阻塞启动完成。
        """
        system = _require_main_system()

        # ZG-1: 服务管理器接管运行时组件（构造 + Port 注册；adopt 延后）
        from src.core.adapters.service_manager_adapter import ServiceManagerAdapter
        from src.core.service_manager.lifecycle import ComponentActions
        from src.core.service_manager_port_registry import set_service_manager_port

        # 构建核心组件健康探针（依赖 chat_manager_adapter/agent_registry/replyer_port
        # 已由 depends_on 保证先于本项执行）
        probe_functions: dict = {}
        if system._chat_manager_adapter is not None:
            probe_functions["chat_manager_adapter"] = system._chat_manager_adapter.health_probe
        if system._agent_registry is not None:
            probe_functions["agent_registry"] = system._agent_registry.health_probe
        if system._replyer_adapter is not None:
            probe_functions["replyer_port"] = system._replyer_adapter.health_probe

        # ZG-6 衔接 5：系统关闭谓词注入（恢复引擎关闭中不自动拉起组件）
        def _system_shutting_down() -> bool:
            try:
                from src.core.system_state_port_registry import get_system_lifecycle_adapter

                adapter = get_system_lifecycle_adapter()
                return bool(adapter and adapter.is_shutting_down())
            except Exception as exc:
                from src.core.error_escalation.types import ErrorLevel
                from src.core.error_escalation_port_registry import get_error_escalation_port
                port = get_error_escalation_port()
                if port is not None:
                    port.report(ErrorLevel.WARNING, "判断系统是否关闭失败", exception=exc)
                return False

        system._service_manager = ServiceManagerAdapter(
            probe_functions=probe_functions,
            lifecycle_state_getter=_system_shutting_down,
            # ZG-15: plugin_runtime_v2 组件 stop 内嵌排空——
            # HostEndpoint.stop 发 ShutdownRequest → Runner 端 mark_going +
            # wait_drained + on_unload（引用计数驱动，非固定 sleep）
            component_actions={
                "plugin_runtime_v2": ComponentActions(
                    stop_fn=system._stop_plugin_runtime_v2,
                    start_fn=system._start_plugin_runtime_v2_stub,
                ),
            },
        )
        set_service_manager_port(system._service_manager)

        # ZG-3: 启动看门狗（WatchdogAdapter.start 要求 ServiceManagerPort 已注册）
        from src.core.adapters.watchdog_adapter import WatchdogAdapter
        from src.core.app_config_port_registry import get_app_config_port
        from src.core.watchdog_port_registry import set_watchdog_port

        watchdog_config = get_app_config_port().get_watchdog_config()
        system._watchdog = WatchdogAdapter(config=watchdog_config)
        set_watchdog_port(system._watchdog)
        await system._watchdog.start(asyncio.get_running_loop())

        # 看门狗 touch 循环（长驻 task——init_fn 内创建后返回，不阻塞启动完成）
        async def _watchdog_touch_loop() -> None:
            while True:
                system._watchdog.touch()
                await asyncio.sleep(watchdog_config.touch_interval_s)

        system._watchdog_touch_task = asyncio.create_task(
            _watchdog_touch_loop(), name="watchdog-touch"
        )

    # ── ZH1-1a 记忆索引层接线 ─────────────────────────────────

    @staticmethod
    @startup_item(
        name="mid_term_persistence",
        phase=StartupPhase.CORE_SERVICES,
        order=17,
        critical=False,
    )
    async def _init_mid_term_persistence() -> None:
        """ZH1-1a：初始化摘要持久化服务 + 自动建表。"""
        from src.maisaka.memory.mid_term_persistence import init_mid_term_persistence

        init_mid_term_persistence()

    @staticmethod
    @startup_item(
        name="mid_term_summary_queue",
        phase=StartupPhase.CORE_SERVICES,
        order=18,
        critical=False,
        depends_on=["mid_term_persistence"],
        dependency_kind={"mid_term_persistence": DependencyKind.STRONG},
    )
    async def _init_mid_term_summary_queue() -> None:
        """ZH1-1a：初始化异步摘要队列 + 消费者 task。"""
        from src.maisaka.memory.mid_term_summary_queue import init_mid_term_summary_queue

        init_mid_term_summary_queue(maxsize=1000)

    @staticmethod
    @startup_item(
        name="ipc_bridge_port",
        phase=StartupPhase.SUBSYSTEMS,
        order=1,
        critical=False,

    )
    async def _inject_ipc_bridge_port() -> None:
        # SUBSYSTEMS 波次依赖保证 plugin_runtime 先于本组件执行，但保留懒加载
        # 单例兜底：PRM 未启动时 is_running=False，EventBus 桥接跳过（CX 审核 P2-6）。
        from src.core.adapters.ipc_bridge_port import IpcBridgePortAdapter
        from src.core.ipc_bridge_port_registry import set_ipc_bridge_port
        from src.plugin_runtime.integration import get_plugin_runtime_manager

        prm = get_plugin_runtime_manager()
        set_ipc_bridge_port(IpcBridgePortAdapter(prm))

    @staticmethod
    @startup_item(
        name="forward_fetch_port",
        phase=StartupPhase.SUBSYSTEMS,
        order=2,
        critical=False,

    )
    async def _init_forward_fetch_port() -> None:
        from src.core.adapters.forward_fetch_adapter import ForwardFetchAdapter
        from src.core.forward_fetch_port_registry import set_forward_fetch_port

        set_forward_fetch_port(ForwardFetchAdapter())

    # ── 阶段 4 闭包 ───────────────────────────────────────────

    @staticmethod
    @startup_item(
        name="session_lifecycle",
        phase=StartupPhase.SESSION_RESTORE,
        order=0,
        critical=True,
        depends_on=["chat_manager_adapter"],
        dependency_kind={"chat_manager_adapter": DependencyKind.STRONG},
    )
    async def _restore_sessions() -> None:
        from src.core.session_port_registry import get_session_lifecycle_port

        lifecycle_port = get_session_lifecycle_port()
        await lifecycle_port.initialize()
        asyncio.create_task(lifecycle_port.regularly_save_sessions())

    @staticmethod
    @startup_item(
        name="memory_automation",
        phase=StartupPhase.SESSION_RESTORE,
        order=1,
        critical=False,
        depends_on=["a_memorix"],
        dependency_kind={"a_memorix": DependencyKind.WEAK},
    )
    async def _start_memory_automation() -> None:
        from src.services.memory_flow_service import memory_automation_service

        await memory_automation_service.start()

    # ── 阶段 5 闭包 ───────────────────────────────────────────

    @staticmethod
    @startup_item(
        name="message_handlers",
        phase=StartupPhase.READY,
        order=0,
        critical=True,
        depends_on=["message_ingestion_port"],
        dependency_kind={"message_ingestion_port": DependencyKind.STRONG},
    )
    async def _register_handlers() -> None:
        _require_main_system()._register_message_handlers()

    @staticmethod
    @startup_item(
        name="on_start_event",
        phase=StartupPhase.READY,
        order=1,
        critical=True,
    )
    async def _emit_on_start() -> None:
        from src.core.event_bus import event_bus
        from src.core.types import EventType

        await event_bus.emit(event_type=EventType.ON_START)

    @staticmethod
    @startup_item(
        name="webui_server",
        phase=StartupPhase.READY,
        order=2,
        critical=False,
        depends_on=["config_manager"],
        dependency_kind={"config_manager": DependencyKind.WEAK},
    )
    async def _start_webui() -> None:
        system = _require_main_system()
        system._start_webui_server()
        # V2 插件 scope 注入：webui 启动后执行（原在 SUBSYSTEMS 的 v2 启动路径，
        # 那时 webui 未启动注入不生效——时序修复）
        await system._inject_scope_services_to_webui()

    @staticmethod
    @startup_item(
        name="scheduled_tasks",
        phase=StartupPhase.READY,
        order=3,
        critical=False,
    )
    async def _add_scheduled_tasks() -> None:
        from src.chat.utils.statistic import OnlineTimeRecordTask, StatisticOutputTask

        await async_task_manager.add_task(OnlineTimeRecordTask())
        await async_task_manager.add_task(StatisticOutputTask())

    @staticmethod
    @startup_item(
        name="interaction_scheduler",
        phase=StartupPhase.READY,
        order=4,
        critical=False,
        depends_on=["a_memorix", "message_handlers"],
        dependency_kind={
            "a_memorix": DependencyKind.WEAK,
            "message_handlers": DependencyKind.STRONG,
        },
    )
    async def _start_interaction_scheduler() -> None:
        system = _require_main_system()
        try:
            from src.maisaka.agent_interaction.bootstrap import build_interaction_scheduler
            from src.maisaka.agent_interaction.relationship_manager import AgentRelationshipManager
            from src.core.adapters import get_memory_service_port

            scheduler = build_interaction_scheduler(get_memory_service_port())
            if scheduler is not None:
                relationship_mgr = AgentRelationshipManager()
                await relationship_mgr.initialize_from_config()
                await scheduler.start()
                system._interaction_scheduler = scheduler
                logger.info(t("startup.agent_interaction_started"))
        except Exception as e:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, "启动交互调度器失败", exception=e)
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


async def main(debug_startup: bool = False, skip_startup_items: set[str] | None = None) -> None:
    """主函数

    Args:
        debug_startup: --debug-startup 启动项逐项观测
        skip_startup_items: --skip-startup-item 跳过的启动项集合
    """
    set_main_loop(asyncio.get_running_loop())
    from src.config.config import initialize_config
    initialize_config()
    system = MainSystem(
        debug_startup=debug_startup,
        skip_startup_items=skip_startup_items,
    )
    try:
        await system.initialize()

        # ZG16-5: 初始化 Tier 1 运行时审计记录器（app_config_port 已就绪，事件循环已运行）
        from src.core.app_config_port_registry import get_app_config_port
        from src.plugin_runtime_v2.scope.scope_audit import init_scope_audit_recorder

        _app_port = get_app_config_port()
        init_scope_audit_recorder(
            log_path=_app_port.get_audit_log_path(),
            max_size_mb=_app_port.get_audit_log_max_size_mb(),
            backup_count=_app_port.get_audit_log_backup_count(),
            sensitive_param_names=_app_port.get_sensitive_param_names(),
        )

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
            except NotImplementedError as exc:
                # P0-4: 信号处理器注册失败出声（ZG-31）——仅主线程可用，保留适配器兜底 handler
                logger.debug("add_signal_handler 失败（非主线程？），保留兜底 handler: %s", exc)

        await system.schedule_tasks()
    finally:
        if system._watchdog_touch_task is not None:
            system._watchdog_touch_task.cancel()
            try:
                await system._watchdog_touch_task
            except asyncio.CancelledError:
                # P0-4: 正常取消静默（防刷屏，对标 kernel/signal.c TASK_KILLABLE）
                pass
            except Exception as exc:
                # P0-4: 关闭路径非预期异常出声（ZG-31）
                logger.warning("watchdog_touch_task 关闭异常: %s", exc, exc_info=True)
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

        from src.services.memory_flow_service import memory_automation_service

        emoji_manager.shutdown()
        await memory_automation_service.shutdown()
        if service_registry.has("a_memorix_host_service"):
            await service_registry.get("a_memorix_host_service").stop()
        if system._v2_host_endpoint is not None:
            await system._v2_host_endpoint.stop()
        # ZG-32: v1 plugin runtime disabled, skip shutdown
        logger.info("v1 plugin runtime disabled, skip shutdown")
        # await get_plugin_runtime_manager().bridge_event("on_stop")
        # await get_plugin_runtime_manager().stop()
        # ZG-21: 停止 SoftirqBatcher drainer（无悬挂 Task，积压不再处理）
        from src.core.event_bus_port_registry import get_event_bus_port
        from src.core.event_bus import event_bus as _core_event_bus

        _autonomy_bus = get_event_bus_port()
        if _autonomy_bus is not None and hasattr(_autonomy_bus, "stop"):
            await _autonomy_bus.stop()
        await _core_event_bus.stop()
        await async_task_manager.stop_and_wait_all_tasks()
        from src.config.config import config_manager as _cm
        await _cm.stop_file_watcher()

        # ZG16-5: 关闭 Tier 1 审计记录器（flush 队列 + 关闭日志文件）
        from src.plugin_runtime_v2.scope.scope_audit import close_scope_audit_recorder

        await close_scope_audit_recorder()

        # ZH1-1a: 关闭摘要队列 + 持久化服务
        from src.maisaka.memory.mid_term_summary_queue import close_mid_term_summary_queue
        from src.maisaka.memory.mid_term_persistence import close_mid_term_persistence

        await close_mid_term_summary_queue()
        await close_mid_term_persistence()

        set_main_loop(None)


if __name__ == "__main__":
    import argparse as _argparse

    _parser = _argparse.ArgumentParser(description="MaiBot")
    _parser.add_argument(
        "--debug-startup", action="store_true",
        help="启动项逐项观测（对标 initcall_debug）",
    )
    _parser.add_argument(
        "--skip-startup-item", type=str, default="",
        help="逗号分隔的跳过启动项名称（对标 initcall_blacklist）",
    )
    _parser.add_argument(
        "--check-model-config", action="store_true",
        help="仅校验模型配置（注册表 + @model_requirement 声明）后退出，不启动系统",
    )
    _args = _parser.parse_args()
    if _args.check_model_config:
        sys.exit(run_model_config_check())
    _skip = {n.strip() for n in _args.skip_startup_item.split(",") if n.strip()}
    asyncio.run(main(debug_startup=_args.debug_startup, skip_startup_items=_skip))
