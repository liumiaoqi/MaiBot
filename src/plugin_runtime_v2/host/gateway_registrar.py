"""V2 网关注册协调器 — 网关就绪 → 驱动注册 → 路由绑定。

协调 GatewayRegistry（声明查询）、V2GatewaySupervisor（gRPC 调用）、
Platform IO Manager（驱动注册 + 路由绑定）、ScopeStore（scope gating）。
"""


import contextlib
from typing import Any

from src.common.logger import get_logger
from src.platform_io import DriverKind, RouteBinding, RouteKey, get_platform_io_manager
from src.platform_io.drivers.plugin_driver import PluginPlatformDriver
from src.plugin_runtime_v2.host.gateway_registry import GatewayRegistry
from src.plugin_runtime_v2.host.gateway_supervisor import V2GatewaySupervisor

logger = get_logger("plugin_runtime_v2.host.gateway_registrar")


class V2GatewayRegistrar:
    """网关就绪 → 先注销旧 → scope gating → 注册新驱动 → 绑定路由。

    由 servicer._recv_loop 在收到 gateway_ready payload 时触发。
    """

    def __init__(
        self,
        gateway_registry: GatewayRegistry,
        scope_store=None,
        startup_summary=None,
    ) -> None:
        self._gateway_registry = gateway_registry
        self._scope_store = scope_store
        self._startup_summary = startup_summary
        # 记录已注册的网关驱动：plugin_id → {gateway_name → V2GatewaySupervisor}
        self._registered: dict[str, dict[str, V2GatewaySupervisor]] = {}

    @staticmethod
    def _build_driver_id(plugin_id: str, gateway_name: str) -> str:
        """派生全局唯一的驱动 ID。"""
        return f"plugin.{plugin_id}.gateway.{gateway_name}"

    async def on_gateway_ready(
        self,
        plugin_id: str,
        gateway_name: str,
        platform: str,
        runner_listen_address: str,
        account_id: str | None = None,
        scope: str | None = None,
    ) -> None:
        """网关就绪 → 先注销旧 → scope gating → 注册新驱动 → 绑定路由。

        Args:
            plugin_id: 插件 ID。
            gateway_name: 网关名称（与 @MessageGateway(name=...) 一致）。
            platform: 平台标识（如 "qq"）。
            runner_listen_address: Runner 的 gRPC 监听地址（用于 V2GatewaySupervisor）。
            account_id: 可选账号 ID。
            scope: 可选路由作用域。
        """
        # ① 从 GatewayRegistry 查询声明
        decl = self._gateway_registry.get_declaration(plugin_id, gateway_name)
        if decl is None:
            logger.warning(
                "网关就绪但声明不存在: plugin=%s gateway=%s",
                plugin_id, gateway_name,
            )
            self._report_summary(plugin_id, gateway_name, "failed", "声明不存在")
            return

        # ② 先注销旧驱动和旧路由绑定（幂等）
        await self._unregister_gateway(plugin_id, gateway_name)

        # ③ scope gating
        effective_supports_send = decl.supports_send
        if decl.supports_send:
            if not self._has_send_scope(plugin_id, platform):
                effective_supports_send = False
                logger.warning(
                    "网关 %s scope 未授予 message:send:*，仅 receive 生效: plugin=%s",
                    gateway_name, plugin_id,
                )
                self._report_summary(
                    plugin_id, gateway_name, "scope_denied",
                    f"message:send:{platform} 未授予",
                )

        # ④ 创建 V2GatewaySupervisor
        tool_name = decl.metadata.get("tool_name", "napcat.send_text")
        supervisor = V2GatewaySupervisor(
            plugin_id=plugin_id,
            runner_listen_address=runner_listen_address,
            tool_name=tool_name,
        )

        # ⑤ 构造 PluginPlatformDriver
        driver_id = self._build_driver_id(plugin_id, gateway_name)
        driver = PluginPlatformDriver(
            driver_id=driver_id,
            platform=platform,
            supervisor=supervisor,
            component_name=gateway_name,
            supports_send=effective_supports_send,
            account_id=account_id,
            scope=scope,
            plugin_id=plugin_id,
            metadata={
                "protocol": decl.protocol,
                "route_type": decl.route_type,
                **decl.metadata,
            },
        )

        # ⑥ 注册到 Platform IO Manager
        platform_io_manager = get_platform_io_manager()
        try:
            if platform_io_manager.is_started:
                await platform_io_manager.add_driver(driver)
            else:
                platform_io_manager.register_driver(driver)
        except Exception as exc:
            logger.warning(
                "网关驱动注册失败: plugin=%s gateway=%s error=%s",
                plugin_id, gateway_name, exc,
            )
            self._report_error_escalation("网关驱动注册失败", exc)
            # 清理半注册状态
            with contextlib.suppress(Exception):
                if platform_io_manager.is_started:
                    await platform_io_manager.remove_driver(driver_id)
                else:
                    platform_io_manager.unregister_driver(driver_id)
            self._report_summary(plugin_id, gateway_name, "failed", str(exc))
            return

        # ⑦ 绑定路由
        route_key = RouteKey(platform=platform, account_id=account_id, scope=scope)
        binding = RouteBinding(
            route_key=route_key,
            driver_id=driver_id,
            driver_kind=DriverKind.PLUGIN,
            metadata={
                "plugin_id": plugin_id,
                "gateway_name": gateway_name,
                "protocol": decl.protocol,
                "route_type": decl.route_type,
                **decl.metadata,
            },
        )
        if effective_supports_send:
            platform_io_manager.bind_send_route(binding)
        if decl.supports_receive:
            platform_io_manager.bind_receive_route(binding)

        # ⑧ 记录已注册状态
        self._registered.setdefault(plugin_id, {})[gateway_name] = supervisor

        logger.info(
            "网关驱动已注册: plugin=%s gateway=%s platform=%s driver_id=%s "
            "send=%s receive=%s",
            plugin_id, gateway_name, platform, driver_id,
            effective_supports_send, decl.supports_receive,
        )
        self._report_summary(
            plugin_id, gateway_name, "registered",
            f"send={effective_supports_send} receive={decl.supports_receive}",
        )

    async def on_gateway_not_ready(
        self,
        plugin_id: str,
        gateway_name: str,
    ) -> None:
        """网关未就绪 → 注销驱动和路由绑定（幂等）。"""
        await self._unregister_gateway(plugin_id, gateway_name)
        logger.info("网关已注销: plugin=%s gateway=%s", plugin_id, gateway_name)

    async def on_runner_disconnected(self, plugin_id: str) -> None:
        """Runner 断开 → 注销该插件的所有网关驱动。"""
        gateways = self._registered.pop(plugin_id, {})
        for gateway_name in list(gateways.keys()):
            await self._unregister_gateway(plugin_id, gateway_name)
        if gateways:
            logger.info(
                "Runner 断开，已注销 %d 个网关驱动: plugin=%s",
                len(gateways), plugin_id,
            )

    # ── 内部方法 ────────────────────────────────────────────────

    async def _unregister_gateway(self, plugin_id: str, gateway_name: str) -> None:
        """注销单个网关驱动（幂等，不存在时不报错）。"""
        driver_id = self._build_driver_id(plugin_id, gateway_name)
        platform_io_manager = get_platform_io_manager()

        # 移除路由绑定
        platform_io_manager.send_route_table.remove_bindings_by_driver(driver_id)
        platform_io_manager.receive_route_table.remove_bindings_by_driver(driver_id)

        # 注销驱动
        with contextlib.suppress(Exception):
            if platform_io_manager.is_started:
                await platform_io_manager.remove_driver(driver_id)
            else:
                platform_io_manager.unregister_driver(driver_id)

        # 关闭 supervisor 的 gRPC 通道
        supervisors = self._registered.get(plugin_id, {})
        supervisor = supervisors.pop(gateway_name, None)
        if supervisor is not None:
            with contextlib.suppress(Exception):
                await supervisor.close()

    def _has_send_scope(self, plugin_id: str, platform: str) -> bool:
        """检查插件是否被授予 message:send:* scope。"""
        if self._scope_store is None:
            return True  # 无 scope_store 时放行
        granted = self._scope_store.get_granted_scopes(plugin_id)
        # 检查 message:send:<platform> 或 message:send:*
        return any(
            s == f"message:send:{platform}" or s == "message:send:*"
            for s in granted
        )

    def _report_summary(
        self,
        plugin_id: str,
        gateway_name: str,
        status: str,
        detail: str = "",
    ) -> None:
        """向启动摘要报告网关注册状态。"""
        if self._startup_summary is None:
            return
        try:
            self._startup_summary.report_gateway_status(
                plugin_id=plugin_id,
                gateway_name=gateway_name,
                status=status,
                detail=detail,
            )
        except Exception:
            pass  # best-effort

    def _report_error_escalation(self, message: str, exc: Exception) -> None:
        """双通道异常上报：logger + error_escalation port。"""
        try:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port

            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, message, exception=exc)
        except Exception:
            pass