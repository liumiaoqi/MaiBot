from typing import TYPE_CHECKING, Any

from rich.traceback import install

import asyncio
import time

from src.common.i18n import t
from src.common.logger import get_logger
from src.common.runtime_loop import set_main_loop
from src.config.config import config_manager, global_config
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


async def _wait_for_plugin_runners_spawned(
    plugin_runtime_manager: Any,
    plugin_runtime_task: asyncio.Task[None],
    timeout: float = 1.0,
) -> None:
    """让插件 Runner 子进程先拉起，以便和后续重初始化并行。"""

    deadline = asyncio.get_running_loop().time() + timeout
    while not plugin_runtime_task.done():
        supervisors = list(getattr(plugin_runtime_manager, "supervisors", []))
        if supervisors and all(getattr(supervisor, "_runner_process", None) is not None for supervisor in supervisors):
            return
        if asyncio.get_running_loop().time() >= deadline:
            return
        await asyncio.sleep(0.02)


class MainSystem:
    def __init__(self) -> None:
        # 使用消息API替代直接的FastAPI实例
        self.app: MessageServer | None = None
        self.server: Server | None = None
        self.webui_server: ThreadedWebUIServer | None = None  # 独立线程中的 WebUI 服务器
        self._message_handlers_registered = False
        self._interaction_scheduler: Any | None = None

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

        self.app.register_message_handler(chat_bot.message_process)
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
            from src.services.tool_record_cleanup_service import run_startup_tool_record_vacuum_if_needed

            await asyncio.to_thread(run_startup_tool_record_vacuum_if_needed)
            await self._init_components()
        except Exception:
            if self.webui_server:
                await self.webui_server.shutdown()
            raise

        logger.info(t("startup.initialization_completed_banner", nickname=global_config.bot.nickname))

    async def _init_components(self) -> None:
        """初始化其他组件"""
        init_start_time = time.time()

        await config_manager.start_file_watcher()

        # ── 构造子模块 → 构造适配器 → 注册 Protocol 端口 ─────────────────
        # 必须在 A_memorix 启动之前，因为 A_memorix 注入时从注册点获取
        from src.chat.message_receive.session_store import SessionStore
        from src.chat.message_receive.message_registry import MessageRegistry
        from src.chat.message_receive.session_name_cache import SessionNameCache
        from src.chat.message_receive.session_resolver import SessionResolver
        from src.chat.message_receive.binding_restorer import BindingRestorer
        from src.chat.message_receive.session_lifecycle import SessionLifecycle
        from src.core.adapters.chat_manager_adapter import ChatManagerAdapter
        from src.core.adapters.routing_adapter import ChatManagerRoutingAdapter
        from src.core.session_port_registry import (
            register_session_info_port,
            register_session_lifecycle_port,
            register_session_query_port,
            register_message_registry_port,
        )
        from src.maisaka.agent.router import AgentRouter
        from src.maisaka.agent.registry import AgentConfigRegistry

        # 构造子模块（SessionStore ↔ MessageRegistry 循环依赖需处理后注入）
        session_store = SessionStore()
        message_registry = MessageRegistry(session_store)
        session_store.set_message_registry(message_registry)
        name_cache = SessionNameCache(session_store)
        resolver = SessionResolver(session_store)
        agent_router = AgentRouter(AgentConfigRegistry())
        binding_restorer = BindingRestorer(agent_router)
        session_lifecycle = SessionLifecycle(session_store, message_registry, agent_router)

        # 构造适配器（构造注入子模块）
        routing_adapter = ChatManagerRoutingAdapter(agent_router)
        _adapter = ChatManagerAdapter(
            routing_service=routing_adapter,
            session_store=session_store,
            message_registry=message_registry,
            name_cache=name_cache,
            resolver=resolver,
            binding_restorer=binding_restorer,
            session_lifecycle=session_lifecycle,
        )

        # 注册 4 个 Protocol 端口
        register_session_info_port(_adapter)
        register_session_lifecycle_port(_adapter)
        register_session_query_port(_adapter)
        register_message_registry_port(_adapter)

        # ── 注册 ReplyerServicePort + ImageDescriptionPort ─────────────────
        from src.chat.replyer.replyer_manager import replyer_manager
        from src.chat.image_system.image_manager import image_manager
        from src.core.adapters.replyer_service_adapter import ReplyerServiceAdapter
        from src.core.adapters.image_description_adapter import ImageDescriptionAdapter
        from src.core.replyer_port_registry import register_replyer_service_port
        from src.core.image_port_registry import register_image_description_port

        register_replyer_service_port(ReplyerServiceAdapter(replyer_manager))
        register_image_description_port(ImageDescriptionAdapter(image_manager))

        # 注册 ChatRuntimeRegistry + ChatRuntimeFactory
        # — 打破 heartflow_manager ↔ maisaka 物理循环依赖
        from src.core.adapters.runtime_registry import HeartflowRuntimeRegistry
        from src.core.runtime_port_registry import (
            register_chat_runtime_factory,
            register_chat_runtime_registry,
        )
        from src.maisaka.runtime import MaisakaRuntimeFactory

        register_chat_runtime_registry(HeartflowRuntimeRegistry())
        register_chat_runtime_factory(MaisakaRuntimeFactory())

        # 插件 Runner 启动最重，尽早发起以便和后续初始化并行。
        from src.plugin_runtime.integration import get_plugin_runtime_manager

        plugin_runtime_manager = get_plugin_runtime_manager()
        plugin_runtime_task = asyncio.create_task(plugin_runtime_manager.start(), name="plugin_runtime_start")
        await _wait_for_plugin_runners_spawned(plugin_runtime_manager, plugin_runtime_task)

        from src.A_memorix.host_service import a_memorix_host_service
        from src.common.service_registry import service_registry

        service_registry.register("a_memorix_host_service", a_memorix_host_service)
        a_memorix_host_service.register_config_reload_callback()

        # 创建 ModelConfigPort 适配器并提前注入 — 必须在 a_memorix start 之前，
        # 否则 EmbeddingAPIAdapter 初始化时 model_config_port 为 None
        from src.core.adapters.model_config_port import ConfigManagerModelConfigPort
        from src.maisaka.agent.registry import AgentConfigRegistry

        _agent_registry = AgentConfigRegistry.get_instance()
        _agent_registry.load()

        _model_config_port = ConfigManagerModelConfigPort(
            config_manager=config_manager,
            agent_config_resolver=lambda aid: _agent_registry.get_agent(aid) if _agent_registry.has_agent(aid) else None,
        )
        a_memorix_host_service.set_model_config_port(_model_config_port)

        a_memorix_task = asyncio.create_task(a_memorix_host_service.start(), name="a_memorix_start")

        await asyncio.sleep(0)
        prompt_manager.load_prompts()

        from src.emoji_system.emoji_manager import emoji_manager

        emoji_load_task = asyncio.create_task(asyncio.to_thread(emoji_manager.load_emojis_from_db), name="emoji_load_from_db")

        # 启动API服务器
        # start_api_server()
        # logger.info("API服务器启动成功")

        try:
            await asyncio.gather(plugin_runtime_task, a_memorix_task)
            await emoji_load_task
        except Exception:
            for task in (plugin_runtime_task, a_memorix_task, emoji_load_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(
                plugin_runtime_task,
                a_memorix_task,
                emoji_load_task,
                return_exceptions=True,
            )
            raise

        # 初始化表情管理器
        logger.info(t("startup.emoji_manager_initialized"))

        # 初始化聊天管理器（通过 SessionLifecyclePort，核心层不直接导入 chat_manager）
        from src.core.session_port_registry import get_session_lifecycle_port
        from src.services.memory_flow_service import memory_automation_service

        lifecycle_port = get_session_lifecycle_port()
        await lifecycle_port.initialize()
        asyncio.create_task(lifecycle_port.regularly_save_sessions())


        logger.info(t("startup.chat_manager_initialized"))
        await memory_automation_service.start()

        # 注入 ModelConfigPort 到其余消费者模块（a_memorix 已在上方提前注入）
        from src.llm_models import model_client
        from src.llm_models import utils_model
        from src.services import service_task_resolver

        utils_model.set_model_config_port(_model_config_port)
        model_client.base_client.set_model_config_port(_model_config_port)
        model_client.set_model_config_port(_model_config_port)
        service_task_resolver.set_model_config_port(_model_config_port)
        logger.info("ModelConfigPort 适配器已创建并注入到 4 个消费者模块")

        # await asyncio.sleep(0.5) #防止logger输出飞了

        # 触发 ON_START 事件，事件总线会统一桥接到 IPC 插件运行时。
        from src.core.event_bus import event_bus
        from src.core.types import EventType

        await event_bus.emit(event_type=EventType.ON_START)
        # logger.info("已触发 ON_START 事件")

        self._start_webui_server()

        from src.chat.utils.statistic import OnlineTimeRecordTask, StatisticOutputTask

        # 添加在线时间统计任务
        await async_task_manager.add_task(OnlineTimeRecordTask())

        # 添加统计信息输出任务
        await async_task_manager.add_task(StatisticOutputTask())

        # 添加遥测心跳与统计上传任务
        from src.common.remote import TelemetryHeartBeatTask, TelemetryStatsUploadTask

        await async_task_manager.add_task(TelemetryHeartBeatTask())
        await async_task_manager.add_task(TelemetryStatsUploadTask())

        # 启动智能体交互调度器
        try:
            from src.maisaka.agent_interaction.bootstrap import build_interaction_scheduler
            from src.maisaka.agent_interaction.relationship_manager import AgentRelationshipManager
            from src.core.adapters import get_memory_service_port

            scheduler = build_interaction_scheduler(get_memory_service_port())
            if scheduler is not None:
                # 初始化关系数据
                relationship_mgr = AgentRelationshipManager()
                await relationship_mgr.initialize_from_config()
                # 启动定时调度
                await scheduler.start()
                self._interaction_scheduler = scheduler
                logger.info(t("startup.agent_interaction_started"))
        except Exception as e:
            logger.warning(t("startup.agent_interaction_failed", error=e))

        try:
            init_time = int(1000 * (time.time() - init_start_time))
            logger.info(t("startup.initialization_completed_cycles", init_time=init_time))
        except Exception as e:
            logger.error(t("startup.brain_external_world_failed", error=e))
            raise

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

            self._register_message_handlers()
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
    system = MainSystem()
    try:
        await system.initialize()
        await system.schedule_tasks()
    finally:
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
        await get_plugin_runtime_manager().bridge_event("on_stop")
        await get_plugin_runtime_manager().stop()
        await async_task_manager.stop_and_wait_all_tasks()
        await config_manager.stop_file_watcher()
        set_main_loop(None)


if __name__ == "__main__":
    asyncio.run(main())
