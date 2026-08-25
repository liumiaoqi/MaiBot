"""gRPC Host 端点 — gRPC 服务端生命周期管理。

管理 Runner 连接：启动 gRPC 服务器、优雅关停、状态查询。
"""


import asyncio

import grpc
from grpc_reflection.v1alpha import reflection

from src.common.logger import get_logger
from src.plugin_runtime_v2.host.connection import (
    HostEndpointConfig,
    RunnerConnectionSnapshot,
)
from src.plugin_runtime_v2.host.heartbeat import HeartbeatManager
from src.plugin_runtime_v2.host.registry import RunnerRegistry
from src.plugin_runtime_v2.host.servicer import _PluginHostServicer
from src.plugin_runtime_v2.proto.plugin_host_pb2_grpc import (
    add_PluginHostServicer_to_server,
)

logger = get_logger("plugin_runtime_v2.host.endpoint")

# ── gRPC 服务端 keepalive 配置（design.md 2.3.2.4） ──
_GRPC_SERVER_OPTIONS = [
    ("grpc.keepalive_time_ms", 30000),
    ("grpc.keepalive_timeout_ms", 10000),
    ("grpc.keepalive_permit_without_calls", 1),
    ("grpc.http2.max_pings_without_data", 0),
    ("grpc.http2.min_time_between_pings_ms", 10000),
    ("grpc.http2.min_ping_interval_without_data_ms", 5000),
]

_SERVICE_NAME = "maibot.plugin.v2.PluginHost"


class HostEndpoint:
    """gRPC Host 服务端 — 管理 Runner 连接生命周期。"""

    def __init__(self, config: HostEndpointConfig | None = None, host_bridge=None,
                 token_service=None, scope_store=None, rate_limiter=None,
                 storage_service=None, gateway_registry=None, gateway_registrar=None,
                 enable_v2_message_gateway: bool = True) -> None:
        self._cfg = config or HostEndpointConfig()
        self._server: grpc.aio.Server | None = None
        self._registry = RunnerRegistry()
        self._heartbeat_mgr = HeartbeatManager(
            interval_s=self._cfg.heartbeat_interval_s,
            timeout_s=self._cfg.heartbeat_timeout_s,
            max_misses=self._cfg.max_heartbeat_misses,
        )
        self._servicer = _PluginHostServicer(
            registry=self._registry,
            heartbeat_mgr=self._heartbeat_mgr,
            config=self._cfg,
            host_bridge=host_bridge,
            token_service=token_service,
            scope_store=scope_store,
            rate_limiter=rate_limiter,
            storage_service=storage_service,
            gateway_registry=gateway_registry,
            gateway_registrar=gateway_registrar,
            enable_v2_message_gateway=enable_v2_message_gateway,
        )
        self._token_service = token_service
        self._scope_store = scope_store
        self._storage_service = storage_service
        self._cleanup_task: asyncio.Task | None = None
        self._actual_listen_address: str = ""
        # ZG16-3：激活编排器（供 stop 逆序卸载用，bootstrap 注入）
        self._activation_coordinator = None
        # ZG16-6a：PluginConfig servicer（bootstrap 注入）
        self._plugin_config_servicer = None

    async def start(self) -> None:
        """启动 gRPC 服务器，开始监听 Runner 连接。

        Raises:
            OSError: 端口被占用。
        """
        self._server = grpc.aio.server(options=_GRPC_SERVER_OPTIONS)
        add_PluginHostServicer_to_server(self._servicer, self._server)

        # 服务描述（供反射服务使用）
        service_names = (_SERVICE_NAME, reflection.SERVICE_NAME)
        reflection.enable_server_reflection(service_names, self._server)

        listen_port = self._server.add_insecure_port(self._cfg.listen_address)
        await self._server.start()
        self._actual_listen_address = f"{self._cfg.listen_address.split(':')[0]}:{listen_port}"

        if self._token_service is not None:
            self._cleanup_task = asyncio.create_task(
                self._cleanup_loop(), name="token-cleanup",
            )

        logger.info(
            "HostEndpoint 已启动，监听 %s，server_id=%s",
            self._actual_listen_address, self._cfg.server_id,
        )

    async def stop(self) -> None:
        """优雅关停：按依赖图逆序卸载，联动 refcount drain。"""
        if self._server is None:
            return

        drain_ms = self._cfg.default_drain_timeout_ms
        runners = list(self._registry.get_all().keys())
        if runners:
            if self._activation_coordinator is not None:
                # ZG16-3：按依赖图逆序卸载（依赖方先于被依赖方）
                unload_order = self._activation_coordinator.plan_unload(set(runners))
                for runner_id in unload_order:
                    logger.info(
                        "向 Runner %s 发送 ShutdownRequest（逆序卸载），drain=%dms",
                        runner_id, drain_ms,
                    )
                    self._heartbeat_mgr.stop(runner_id)
                    self._servicer.request_shutdown(
                        runner_id, reason="host_shutdown", drain_ms=drain_ms,
                    )
                    self._activation_coordinator.on_plugin_unloaded(runner_id)
            else:
                # 无 coordinator fallback 原顺序（向后兼容）
                for runner_id in runners:
                    logger.info(
                        "向 Runner %s 发送 ShutdownRequest，drain=%dms",
                        runner_id, drain_ms,
                    )
                    self._heartbeat_mgr.stop(runner_id)
                    self._servicer.request_shutdown(
                        runner_id, reason="host_shutdown", drain_ms=drain_ms,
                    )

            # 等待排空
            if drain_ms > 0:
                await asyncio.sleep(drain_ms / 1000.0)

        # 停止心跳 + 清理注册表
        self._heartbeat_mgr.stop_all()
        for runner_id in list(self._registry.get_all().keys()):
            self._registry.unregister(runner_id)

        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            self._cleanup_task = None

        # 停止 gRPC 服务器
        await self._server.stop(grace=5)
        self._server = None
        self._actual_listen_address = ""

        # 停止 Runner 子进程
        supervisor = getattr(self, "_supervisor", None)
        if supervisor is not None:
            await supervisor.stop()

        logger.info("HostEndpoint 已停止")

    async def _cleanup_loop(self) -> None:
        """定期清理过期 token 的后台任务。"""
        try:
            while True:
                await asyncio.sleep(60)
                if self._token_service is not None:
                    self._token_service.cleanup_expired()
        except asyncio.CancelledError:
            # P0-4: 正常取消静默（防刷屏，对标 kernel/signal.c TASK_KILLABLE）
            pass
        except Exception as exc:
            # P0-2: 后台循环异常出声（ZG-31）
            # 对标 Linux kernel/panic.c:77-92 OOPS + dsh defensive-patterns: Contain callback exceptions in the dispatcher
            logger.exception("token cleanup loop failed: %s", exc, exc_info=True)
            # P1: 补 port.report 双通道上报（A23a P1-4）
            try:
                from src.core.error_escalation.types import ErrorLevel
                from src.core.error_escalation_port_registry import get_error_escalation_port
                _port = get_error_escalation_port()
                if _port is not None:
                    _port.report(ErrorLevel.ERROR, "token cleanup loop failed", exception=exc)
            except Exception:
                pass

    def get_status(self) -> dict[str, RunnerConnectionSnapshot]:
        """返回所有 Runner 连接状态快照，供 WebUI 调试页使用。"""
        return self._registry.get_all_snapshots()

    @property
    def listen_address(self) -> str:
        """实际监听地址（启动后可用）。"""
        return self._actual_listen_address

    @property
    def scope_store(self):
        return self._scope_store

    @property
    def token_service(self):
        return self._token_service

    def set_supervisor(self, supervisor) -> None:
        """正式注入 RunnerSupervisor。"""
        # ZG-15：双向注入——supervisor 需要 servicer（发 ShutdownRequest 排空）
        supervisor.set_servicer(self._servicer)
        self._supervisor = supervisor
        if self._servicer is not None:
            self._servicer._supervisor = supervisor

    def set_activation_coordinator(self, coordinator) -> None:
        """注入 ActivationCoordinator（ZG16-3，供 stop 逆序卸载用）。"""
        self._activation_coordinator = coordinator

    def set_plugin_config_servicer(self, config_manager, scope_validator) -> None:
        """ZG16-6a: 注入 PluginConfigServicer 并注册到已运行的 gRPC server。

        在 HostEndpoint.start() 之后调用——bootstrap 先启动 endpoint 再初始化
        PluginConfigManager，此处补注册 config 服务到运行中的 server。
        """
        from src.plugin_runtime_v2.host.servicer import PluginConfigServicer
        from src.plugin_runtime_v2.proto.plugin_config_pb2_grpc import (
            add_PluginConfigServiceServicer_to_server,
        )

        self._plugin_config_servicer = PluginConfigServicer(
            config_manager=config_manager,
            scope_validator=scope_validator,
        )
        if self._server is not None:
            add_PluginConfigServiceServicer_to_server(
                self._plugin_config_servicer, self._server,
            )
            logger.info("PluginConfigServicer 已注册到 Host gRPC server")

    def get_supervisor(self):
        """返回 RunnerSupervisor（未设置时 None）。"""
        return getattr(self, "_supervisor", None)

    async def reload_runners(self, drain_ms: int = 0) -> dict:
        """热重载所有 Runner。"""
        supervisor = getattr(self, "_supervisor", None)
        if supervisor is not None:
            return await supervisor.reload_all(drain_ms)
        return {}
