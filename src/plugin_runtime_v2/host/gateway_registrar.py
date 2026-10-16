"""V2 网关注册协调器 — 网关就绪 → 驱动注册 → 路由绑定。

协调 GatewayRegistry（声明查询）、V2GatewaySupervisor（gRPC 调用）、
Platform IO Manager（驱动注册 + 路由绑定）、ScopeStore（scope gating）。
"""


import contextlib
from typing import NamedTuple

from src.common.logger import get_logger
from src.platform_io import DriverKind, RouteBinding, RouteKey, get_platform_io_manager
from src.platform_io.drivers.plugin_driver import PluginPlatformDriver
from src.plugin_runtime_v2.host.gateway_registry import GatewayRegistry
from src.plugin_runtime_v2.host.gateway_supervisor import V2GatewaySupervisor

logger = get_logger("plugin_runtime_v2.host.gateway_registrar")

_SEND_SCOPE_PREFIX = "message:send:"
"""发送 scope 的前缀——``message:send:`` 之后跟的是**消息类型**。

权威定义见 `src/plugin_runtime_v2/scope/vocabulary.py:26-30`（text/image/emoji/forward/hybrid）；
SDK 侧同口径：`sdk/context.py:26-30`、发送侧 `host/servicer.py:709-715`。
⚠️ 词汇表里**没有** ``message:send:<平台名>`` 这一类——平台（``qq`` 等）只出现在
``RouteKey.platform`` 与 ``GatewayReadyPayload.platform``，是**路由**用的，不是权限粒度。
"""


class _SendScopeDecision(NamedTuple):
    """发送资格判定结果 —— **具名**：放行与拒绝都要说清依据。

    为什么不是裸 `bool`（P3"消灭静默"）：一个 `False` 在调用点分不出
    "插件没被授权" 与 "根本没法判定授权（scope_store 缺失）"——前者是正常的权限结果，
    后者是**运行时的接线缺失**，两者该在日志/启动摘要里长得不一样。
    """

    allowed: bool
    reason: str


#: `gateway metadata['tool_name']` 缺失时的**具名回落**值（P1②）。
#: ⚠️ 它**不是**正常态：命中即打 warning（"插件未声明 tool_name"）。
#: 保留它是为了**旧插件（不声明 metadata）仍能工作** —— 但要让"你在靠回落跑"在日志里看得见。
_FALLBACK_TOOL_NAME = "napcat.send_text"


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
            self._report_summary(plugin_id, gateway_name, "failed", "声明不存在", platform=platform)
            return

        # ② 先注销旧驱动和旧路由绑定（幂等）
        await self._unregister_gateway(plugin_id, gateway_name)

        # ③ scope gating
        effective_supports_send = decl.supports_send
        if decl.supports_send:
            scope_decision = self._decide_send_scope(plugin_id)
            if not scope_decision.allowed:
                effective_supports_send = False
                logger.warning(
                    "网关 %s 未获得发送资格，仅 receive 生效: plugin=%s 依据=%s",
                    gateway_name, plugin_id, scope_decision.reason,
                )
                self._report_summary(
                    plugin_id, gateway_name, "scope_denied",
                    scope_decision.reason,
                    platform=platform,
                )

        # ④ 创建 V2GatewaySupervisor
        # P1②：tool_name 来自**插件声明的 metadata**（此前 proto 无 metadata 字段 ⇒ 主机只能硬编码）。
        # ⚠️ 硬编码**不删**：declared 缺失时回落到它，但**必须具名**（不许静默）。
        declared_tool_name = str((decl.metadata or {}).get("tool_name", "")).strip()
        if declared_tool_name:
            tool_name = declared_tool_name
        else:
            tool_name = _FALLBACK_TOOL_NAME
            logger.warning(
                "插件未声明 metadata['tool_name']，回落到 %s（gateway=%s, plugin=%s）"
                "—— 这是回退路径，不是正常态；请让插件在 @MessageGateway 里声明",
                tool_name,
                gateway_name,
                plugin_id,
            )
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
            self._report_summary(plugin_id, gateway_name, "failed", str(exc), platform=platform)
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
            platform=platform,
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

    def _decide_send_scope(self, plugin_id: str) -> "_SendScopeDecision":
        """插件是否被授予**发送资格**：``message:send:*`` 或任一 ``message:send:<消息类型>``。

        ⚠️ **2026-10-16 修**：原实现按 ``message:send:{platform}`` 取（platform 来自网关声明，
        如 ``qq``）⇒ 去找一个**词汇表里不存在的** scope，与真机上已授予的 ``message:send:text``
        **永远匹配不上** ⇒ 网关被判成"只能收不能发"（麦麦"能听不能说"）。
        易错点在这里：本函数同时拿得到 ``platform`` 与 ``scope``（后者是**路由**作用域），
        而 ``GatewayReadyPayload`` 的 proto 注释把 ``message:send:qq`` 当例子写着
        （``proto/common.proto:99``）——照着它写就会把"平台"当成权限粒度。

        ⚠️ **2026-10-16 P3 修：``scope_store`` 缺失改为 fail-closed + 具名**。原实现在这里
        ``return True``（注释写着"无 scope_store 时放行"）——那是 **fail-open**：授权服务没接上时
        **所有**插件都自动拿到发送资格，安全面**静默降级**，日志里还看不出来。
        按裁定（**authority 面一律 fail-closed + 具名**：降级可以，静默不行）：
        缺失 ⇒ **拒绝**，并把"无法判定授权"作为**具名 reason** 交给调用方写日志与启动摘要。

        **粒度分工（本函数的语义，别改）**：

        - **这里只判"有没有发送资格"**：网关注册时只知道平台，不知道将来要发哪种消息，
          所以"有任意一种 `message:send:<类型>` 授权"即算有资格。只授了 ``message:send:image``
          的插件也该能注册——否则它的图片永远发不出去（同一个 bug 换张脸）。
        - **具体消息类型**的授权在**发送那一刻**按类型复核：``host/servicer.py:709-718`` 把
          TEXT/IMAGE/… 映射成 ``message:send:<type>``，未授予即返回 ``SCOPE_DENIED``。
          ⇒ 只授 ``forward`` 的插件**能注册**，但**发 text 会被拒**——拒绝发生在发送侧。
        - 声明（``decl.supports_send``）**不能替代授权**：它是"这个网关会不会发"，
          不是"允许不允许发"。⇒ 本判据只做减法、不做加法。

        Returns:
            ``_SendScopeDecision``：``allowed`` 为是否放行，``reason`` 为**具名依据**
            （放行时为空串；拒绝时必非空，调用方据此写日志与摘要）。
        """
        if self._scope_store is None:
            return _SendScopeDecision(
                allowed=False,
                reason="scope_store 缺失 ⇒ 无法判定授权（authority 面 fail-closed，拒绝发送资格）",
            )
        granted = self._scope_store.get_granted_scopes(plugin_id)
        # 前缀判据一并覆盖 `message:send:*`（通配也以该前缀开头）；
        # 词汇表外的写法（如 `message:send:qq`）若真被授予，也算有资格——**宁可放行到发送侧
        # 由类型复核兜住**，也不在这里把已授权的插件误判成"不能说"。
        if any(scope.startswith(_SEND_SCOPE_PREFIX) for scope in granted):
            return _SendScopeDecision(allowed=True, reason="")
        return _SendScopeDecision(
            allowed=False,
            reason="未授予任何 message:send:*（发送资格）",
        )

    def _report_summary(
        self,
        plugin_id: str,
        gateway_name: str,
        status: str,
        detail: str = "",
        *,
        platform: str = "",
    ) -> None:
        """向启动摘要报告网关注册状态。

        ⚠️ ``platform`` **必须传**（2026-10-16 修）：摘要适配器的形参默认是 ``""``，渲染时把
        空值显示成 ``?``（``gateway_startup_summary.py:39/54``）⇒ 不传就会出现 ``platform=?``
        这种"看不出是没解析还是没传"的现场（真机启动摘要里就是这么显示的，还被误读成
        "平台没解析 ⇒ 检查找的是 message:send:?"）。
        """
        if self._startup_summary is None:
            return
        try:
            self._startup_summary.report_gateway_status(
                plugin_id=plugin_id,
                gateway_name=gateway_name,
                status=status,
                detail=detail,
                platform=platform,
            )
        except Exception as exc:  # noqa: BLE001 — 摘要上报是 best-effort，但**不许静默**
            # 原实现是 `except Exception: pass`（AGENTS §十三：拿未来换现在——排障能力被透支）。
            # 保留"不因上报失败而中断注册"的意图，但要让它在日志里看得见。
            logger.warning(
                "网关注册状态上报失败（不影响注册结果）: plugin=%s gateway=%s status=%s: %s",
                plugin_id, gateway_name, status, exc,
                exc_info=True,
            )

    def _report_error_escalation(self, message: str, exc: Exception) -> None:
        """双通道异常上报：logger + error_escalation port（上报失败只出声，不抛出）。"""
        try:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port

            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, message, exception=exc)
        except Exception as report_exc:  # noqa: BLE001 — 同 `_report_summary`：不静默
            logger.warning(
                "错误上报通道不可用（不影响主流程）: %s: %s", message, report_exc, exc_info=True
            )