"""gRPC Host 服务实现 — Connect 双向流 + RegisterComponents 一元 RPC。

实现 service PluginHost：握手校验、组件注册、消息循环、注册超时。
"""


import asyncio
import importlib.metadata
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, AsyncIterator

import grpc

from src.common.logger import get_logger
from src.plugin_runtime_v2.host.connection import (
    ConnectionState,
    HostEndpointConfig,
    RunnerConnection,
)
from src.plugin_runtime_v2.host.heartbeat import HeartbeatManager
from src.plugin_runtime_v2.host.registry import RunnerRegistry
from src.plugin_runtime_v2.proto import common_pb2, plugin_host_pb2
from src.plugin_runtime_v2.proto.plugin_host_pb2_grpc import PluginHostServicer
from src.plugin_runtime_v2.scope.validate_manifest_scopes import Tier1Detector


if TYPE_CHECKING:
    from src.common.data_models.message_component_data_model import MessageSequence
    from src.plugin_runtime_v2.mcp.host_bridge import MCPHostBridge

logger = get_logger("plugin_runtime_v2.host.servicer")

# ── 版本校验 ──
_MIN_SDK_VERSION = "4.0.0"
_MAX_SDK_VERSION = "5.0.0"


def _parse_version_tuple(version: str) -> tuple[int, ...]:
    """将语义化版本字符串转为可比较的整数元组。"""
    try:
        return tuple(int(p) for p in version.split("."))
    except (ValueError, TypeError):
        return ()


def _check_sdk_version(sdk_version: str) -> bool:
    """校验 sdk_version 是否在 [min, max) 范围内。"""
    v = _parse_version_tuple(sdk_version)
    lo = _parse_version_tuple(_MIN_SDK_VERSION)
    hi = _parse_version_tuple(_MAX_SDK_VERSION)
    if not v:
        return False
    return lo <= v < hi


# ── ZG16-5: 加载时 scopes 缺失告警 ──


@dataclass(frozen=True)
class LoadAlert:
    """加载告警事件。"""

    plugin_id: str
    alert_level: str  # "warning" | "error"
    is_tier1: bool
    timestamp: float
    missing_scopes: list[str] = field(default_factory=list)


def check_scopes_completeness(
    plugin_id: str,
    manifest: dict,
    is_v2: bool,
    plugin_code_path: str | None = None,
) -> LoadAlert | None:
    """检测插件 scopes 声明完整性。返回 LoadAlert 或 None（无告警）。

    纯逻辑函数，无副作用（不修改 manifest/不阻断加载，design 2.6.3）。
    """
    # v1 插件不触发（spec 5.4.1 规则 6）
    if not is_v2:
        return None

    # 提取 scopes
    scopes = manifest.get("scopes", [])
    if not isinstance(scopes, list):
        logger.warning("插件 %s scopes 字段格式错误，跳过检测", plugin_id)
        return None

    # scopes 缺失或空 → warning（spec 5.4.1 规则 1）
    if not scopes:
        return LoadAlert(
            plugin_id=plugin_id,
            alert_level="warning",
            is_tier1=False,
            timestamp=time.time(),
        )

    # Tier 1 静态检测
    if plugin_code_path is not None:
        try:
            detected = Tier1Detector.detect(plugin_code_path)
        except Exception:
            # 检测失败 → 降级为仅 scopes 字段检测（spec 5.4.3 场景 3）
            logger.warning("插件 %s Tier 1 检测失败，降级为仅 scopes 字段检测", plugin_id, exc_info=True)
            return None
    else:
        detected = []

    # 比对缺失
    missing_tier1 = [s for s in detected if s not in scopes]
    if missing_tier1:
        return LoadAlert(
            plugin_id=plugin_id,
            alert_level="error",
            missing_scopes=missing_tier1,
            is_tier1=True,
            timestamp=time.time(),
        )

    return None


def _emit_load_alert(alert: LoadAlert) -> None:
    """发送加载告警：logger.warning/error + error_escalation_port 上报。

    best-effort：失败不阻断加载（spec 5.4.1 规则 7）。
    """
    try:
        if alert.alert_level == "warning":
            msg = f"插件 {alert.plugin_id} 缺失 scopes 声明"
            logger.warning(msg)
        else:
            msg = f"插件 {alert.plugin_id} 缺失 Tier 1 scope: {alert.missing_scopes}"
            logger.error(msg)

        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port

        port = get_error_escalation_port()
        if port is not None:
            level = ErrorLevel.WARN if alert.alert_level == "warning" else ErrorLevel.ERROR
            port.report(level, msg, component_id=alert.plugin_id)
    except Exception:
        # best-effort：告警失败不阻断加载（spec 5.4.1 规则 7）
        logger.warning("加载告警发送失败，跳过", exc_info=True)


class _PluginHostServicer(PluginHostServicer):
    """PluginHost gRPC 服务实现。

    处理 Runner 的连接握手、组件注册和消息循环。
    """

    def __init__(
        self,
        registry: RunnerRegistry,
        heartbeat_mgr: HeartbeatManager,
        config: HostEndpointConfig,
        host_bridge: MCPHostBridge | None = None,
        token_service = None,
        scope_store = None,
        rate_limiter = None,
        storage_service = None,
    ) -> None:
        self._registry = registry
        self._heartbeat_mgr = heartbeat_mgr
        self._config = config
        self._host_bridge = host_bridge
        self._token_service = token_service
        self._scope_store = scope_store
        self._rate_limiter = rate_limiter
        self._storage = storage_service
        self._pending_plugin_id: str = ""
        self._outboxes: dict[str, asyncio.Queue[common_pb2.HostMessage | None]] = {}

    # ── Connect 双向流 ──────────────────────────────────────────

    async def Connect(
        self,
        request_iterator: AsyncIterator[common_pb2.RunnerMessage],
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator[common_pb2.HostMessage]:
        """处理 Connect 双向流：握手 → 消息循环。"""
        # ── 握手阶段 ──
        try:
            first_msg: common_pb2.RunnerMessage = await asyncio.wait_for(
                anext(request_iterator), timeout=10.0,
            )
        except asyncio.TimeoutError:
            logger.info("Connect 双向流首条消息超时，关闭连接")
            yield common_pb2.HostMessage(
                hello_response=common_pb2.HelloResponse(
                    accepted=False, reason="FIRST_MESSAGE_TIMEOUT",
                )
            )
            return
        except StopAsyncIteration:
            return

        hello = first_msg.hello
        if first_msg.WhichOneof("payload") != "hello":
            logger.info("Connect 首条消息非 HelloPayload，关闭连接")
            yield common_pb2.HostMessage(
                hello_response=common_pb2.HelloResponse(
                    accepted=False, reason="FIRST_MESSAGE_MUST_BE_HELLO",
                )
            )
            return

        accept, reason = self._validate_hello(hello)
        if not accept:
            logger.info("Runner %s 握手被拒: %s", hello.runner_id or "(无ID)", reason)
            yield common_pb2.HostMessage(
                hello_response=common_pb2.HelloResponse(
                    accepted=False, reason=reason,
                )
            )
            return

        runner_id = hello.runner_id
        conn = RunnerConnection(
            runner_id=runner_id,
            state=ConnectionState.HANDSHAKING,
            sdk_version=hello.sdk_version,
            session_token=hello.session_token,
            scopes=list(hello.scopes),
        )
        conn._peer = context.peer() or ""
        conn.runner_listen_address = hello.runner_listen_address or ""
        self._registry.register(conn)

        logger.info("Runner %s 握手成功，sdk=%s", runner_id, hello.sdk_version)

        # 计算 granted/rejected scopes
        rejected_scopes: list[str] = []
        scope_key = self._pending_plugin_id or runner_id
        if self._scope_store is not None:
            self._scope_store.approve_all_pending(scope_key, list(hello.scopes))
            approved = self._scope_store.get_granted_scopes(scope_key)
            requested = set(hello.scopes)
            granted = requested & approved
            rejected_scopes = list(requested - approved)
            conn.scopes = list(granted)
            if rejected_scopes:
                logger.warning(
                    "Runner %s 部分 scope 被拒绝: %s", runner_id, rejected_scopes,
                )

        # ── ZG16-5: 加载时 scopes 缺失告警（握手处理中，不阻断加载） ──
        # 注意：plugin_code_path=None → Tier 1 静态检测不运行（握手时插件代码路径不可得）
        # 仅检测 scopes 字段缺失/空（warning 级），Tier 1 error 告警需在插件目录可得处补跑
        try:
            _manifest_for_check = {"scopes": list(hello.scopes)}
            _plugin_id_for_check = self._pending_plugin_id or runner_id
            _alert = check_scopes_completeness(
                plugin_id=_plugin_id_for_check,
                manifest=_manifest_for_check,
                is_v2=True,
                plugin_code_path=None,
            )
            if _alert is not None:
                _emit_load_alert(_alert)
        except Exception:
            # 告警 best-effort：失败不阻断加载（spec 5.4.1 规则 7）
            logger.warning("scopes 缺失告警失败，跳过", exc_info=True)

        try:
            host_ver = importlib.metadata.version("maibot")
        except importlib.metadata.PackageNotFoundError:
            host_ver = "unknown"
        yield common_pb2.HostMessage(
            hello_response=common_pb2.HelloResponse(
                accepted=True,
                host_version=host_ver,
                rejected_scopes=rejected_scopes,
            )
        )

        # ── 注册等待阶段 ──
        conn.transition(ConnectionState.REGISTERING)
        outbox: asyncio.Queue[common_pb2.HostMessage | None] = asyncio.Queue(maxsize=64)
        self._outboxes[runner_id] = outbox
        register_deadline = time.time() + self._config.register_timeout_s

        async def _send_heartbeat() -> None:
            """构造心跳请求并放入发送队列。"""
            hb = common_pb2.HostMessage(
                heartbeat=common_pb2.HeartbeatRequest(
                    timestamp_ms=int(time.time() * 1000),
                )
            )
            try:
                outbox.put_nowait(hb)
            except asyncio.QueueFull:
                logger.warning("Runner %s 发送队列已满，跳过心跳", runner_id)

        async def _on_heartbeat_timeout(rid: str) -> None:
            """心跳连续超时回调：通知 Supervisor + 关闭双向流。"""
            logger.warning("Runner %s 心跳超时，关闭双向流", rid)
            supervisor = getattr(self, "_supervisor", None)
            if supervisor is not None:
                asyncio.create_task(
                    supervisor._on_heartbeat_timeout(rid),
                    name=f"supervisor-hb-timeout-{rid}",
                )
            await context.abort(grpc.StatusCode.UNAVAILABLE, "heartbeat timeout")

        self._heartbeat_mgr.start(runner_id, _send_heartbeat, _on_heartbeat_timeout)

        # ZG-3: V2 Runner 注册到看门狗桥接（经注册点，不导入具体类；
        # 看门狗未注册/异常时降级跳过，不阻断 Runner 连接）
        try:
            from src.core.watchdog_port_registry import get_watchdog_port

            watchdog = get_watchdog_port()
            supervisor = getattr(self, "_supervisor", None)
            if supervisor is not None:
                watchdog.register_v2_supervisor(
                    runner_id, supervisor, self._heartbeat_mgr, "plugin_runtime_v2",
                )
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, 'V2 Runner 注册到看门狗桥接失败，已降级跳过', exception=exc)
            logger.warning(
                "V2 Runner 注册到看门狗桥接失败，已降级跳过（runner_id=%s）",
                runner_id,
                exc_info=True,
            )

        # ── 消息循环 ──
        async def _recv_loop() -> None:
            """接收 RunnerMessage 的后台任务。"""
            try:
                async for msg in request_iterator:
                    payload_kind = msg.WhichOneof("payload")
                    if payload_kind == "event":
                        event = msg.event
                        logger.debug(
                            "Runner %s 推送 Event: %s", runner_id, event.event_name,
                        )
                        if self._host_bridge is not None:
                            asyncio.create_task(
                                self._host_bridge.on_event_received(
                                    event.event_name, event.payload, runner_id,
                                ),
                                name=f"event-dispatch-{runner_id}",
                            )
                        await outbox.put(
                            common_pb2.HostMessage(
                                event_ack=common_pb2.EventAck(received=True),
                            )
                        )
                    elif payload_kind == "heartbeat":
                        self._heartbeat_mgr.record_response(runner_id)
                        conn.record_heartbeat()
            except Exception as exc:
                from src.core.error_escalation.types import ErrorLevel
                from src.core.error_escalation_port_registry import get_error_escalation_port
                port = get_error_escalation_port()
                if port is not None:
                    port.report(ErrorLevel.WARNING, 'Runner 接收循环退出', exception=exc)
                logger.warning("Runner %s 接收循环退出", runner_id, exc_info=True)
            finally:
                await outbox.put(None)  # 发送终止信号

        async def _send_loop() -> None:
            """发送 HostMessage 的后台任务。"""
            try:
                while True:
                    msg = await outbox.get()
                    if msg is None:
                        return
                    yield msg
            except GeneratorExit:
                # P0-4: 生成器关闭静默（对标 CancelledError，正常关闭路径）
                pass
            except Exception as exc:
                # P0-2: 发送循环异常出声（ZG-31）
                # 对标 Linux kernel/panic.c:77-92 OOPS + dsh defensive-patterns: Contain callback exceptions in the dispatcher
                logger.exception("send loop failed (runner_id=%s): %s", runner_id, exc, exc_info=True)

        recv_task = asyncio.create_task(_recv_loop(), name=f"recv-{runner_id}")

        try:
            async for out_msg in _send_loop():
                # 注册超时检查
                if conn.state == ConnectionState.REGISTERING:
                    if time.time() > register_deadline:
                        logger.warning("Runner %s 注册超时（%ds），关闭连接",
                                       runner_id, self._config.register_timeout_s)
                        conn.transition(ConnectionState.CLOSING)
                        yield common_pb2.HostMessage(
                            shutdown=common_pb2.ShutdownRequest(
                                reason="REGISTER_TIMEOUT",
                                drain_timeout_ms=0,
                            )
                        )
                        return
                yield out_msg
        finally:
            await recv_task
            self._cleanup_connection(runner_id)

    def _validate_hello(self, hello: common_pb2.HelloPayload) -> tuple[bool, str]:
        """校验 HelloPayload，返回 (accepted, reason)。

        Token 验证成功时将 plugin_id 存入 self._pending_plugin_id 供 Connect 使用。
        """
        if not hello.runner_id:
            return False, "MISSING_REQUIRED_FIELD: runner_id"
        if not hello.sdk_version:
            return False, "MISSING_REQUIRED_FIELD: sdk_version"
        if not hello.session_token and self._token_service is not None:
            return False, "MISSING_REQUIRED_FIELD: session_token"
        if self._registry.has(hello.runner_id):
            return False, "RUNNER_ALREADY_CONNECTED"
        if not _check_sdk_version(hello.sdk_version):
            return False, "SDK_VERSION_MISMATCH"
        self._pending_plugin_id = ""
        if self._token_service is not None and hello.session_token:
            valid, plugin_id = self._token_service.validate_session(hello.session_token)
            if not valid:
                return False, "TOKEN_INVALID"
            self._pending_plugin_id = plugin_id
        return True, ""

    # ── RegisterComponents 一元 RPC ─────────────────────────────

    async def RegisterComponents(
        self,
        request: plugin_host_pb2.RegisterComponentsRequest,
        context: grpc.aio.ServicerContext,
    ) -> plugin_host_pb2.RegisterComponentsResponse:
        """处理组件注册请求。"""
        runner_id = self._resolve_runner_id(context)
        if not runner_id:
            return plugin_host_pb2.RegisterComponentsResponse(
                accepted=False, reasons=["RUNNER_NOT_FOUND"],
            )

        conn = self._registry.get(runner_id)
        if conn is None:
            return plugin_host_pb2.RegisterComponentsResponse(
                accepted=False, reasons=["RUNNER_NOT_FOUND"],
            )

        if conn.state != ConnectionState.REGISTERING:
            return plugin_host_pb2.RegisterComponentsResponse(
                accepted=False,
                reasons=[f"INVALID_STATE: expected REGISTERING, got {conn.state.value}"],
            )

        if not request.plugin_id:
            return plugin_host_pb2.RegisterComponentsResponse(
                accepted=False, reasons=["MISSING_PLUGIN_ID"],
            )

        if self._rate_limiter is not None and not self._rate_limiter.check(request.plugin_id):
            return plugin_host_pb2.RegisterComponentsResponse(
                accepted=False, reasons=["RATE_LIMIT_EXCEEDED"],
            )

        # 校验组件 name 唯一性
        tool_names = [t.name for t in request.tools]
        event_names = [e.name for e in request.events]
        seen_tools: set[str] = set()
        seen_events: set[str] = set()
        for name in tool_names:
            if name in seen_tools:
                return plugin_host_pb2.RegisterComponentsResponse(
                    accepted=False, reasons=[f"DUPLICATE_TOOL_NAME: {name}"],
                )
            seen_tools.add(name)
        for name in event_names:
            if name in seen_events:
                return plugin_host_pb2.RegisterComponentsResponse(
                    accepted=False, reasons=[f"DUPLICATE_EVENT_NAME: {name}"],
                )
            seen_events.add(name)

        # 存储组件声明
        conn.tools = list(request.tools)
        conn.events = list(request.events)
        conn.plugin_id = request.plugin_id
        conn.plugin_version = request.plugin_version
        conn.connected_at = time.time()
        conn.transition(ConnectionState.READY)

        logger.info(
            "Runner %s 组件注册成功: plugin=%s, tools=%d, events=%d",
            runner_id, request.plugin_id, len(request.tools), len(request.events),
        )

        if self._host_bridge is not None:
            self._host_bridge.on_runner_registered(
                runner_id=conn.runner_id,
                plugin_id=conn.plugin_id,
                tools=conn.tools,
                events=conn.events,
                runner_listen_address=conn.runner_listen_address,
            )

        return plugin_host_pb2.RegisterComponentsResponse(accepted=True)

    def _resolve_runner_id(self, context: grpc.aio.ServicerContext) -> str:
        """从 gRPC 上下文解析 runner_id。

        RegisterComponents 是一元 RPC，无法直接通过双向流关联 runner_id。
        通过 peer 地址在注册表中查找匹配的 Runner。
        """
        peer = context.peer() or ""
        for runner_id, conn in self._registry.get_all().items():
            if getattr(conn, "_peer", "") == peer:
                return runner_id
        return ""

    # ── 资源清理 ────────────────────────────────────────────────

    def request_shutdown(self, runner_id: str, reason: str = "host_shutdown", drain_ms: int = 5000) -> None:
        """向指定 Runner 发送 ShutdownRequest。

        注入到 Runner 的 outbox 中，由 send_loop 异步发送。
        """
        outbox = self._outboxes.get(runner_id)
        if outbox is None:
            return
        try:
            outbox.put_nowait(
                common_pb2.HostMessage(
                    shutdown=common_pb2.ShutdownRequest(
                        reason=reason,
                        drain_timeout_ms=drain_ms,
                    )
                )
            )
        except asyncio.QueueFull:
            logger.warning("Runner %s outbox 已满，ShutdownRequest 未发送", runner_id)

    def _cleanup_connection(self, runner_id: str) -> None:
        """清理 Runner 连接资源。"""
        self._heartbeat_mgr.stop(runner_id)

        # ZG-3: V2 Runner 从看门狗桥接注销（stop 已清理心跳监听器，
        # unregister_runner 摘除监听器为静默忽略；看门狗未注册时降级跳过）
        try:
            from src.core.watchdog_port_registry import get_watchdog_port

            watchdog = get_watchdog_port()
            watchdog.unregister_runner(runner_id)
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, 'V2 Runner 从看门狗桥接注销失败，已降级跳过', exception=exc)
            logger.warning(
                "V2 Runner 从看门狗桥接注销失败，已降级跳过（runner_id=%s）",
                runner_id,
                exc_info=True,
            )

        # ZG-15 修复：先读 plugin_id 再 unregister——原顺序在 unregister 后
        # get 恒返回 None，on_runner_disconnected 恒收空 id，MCPToolProvider
        # 永不注销（每次断连泄漏一个 provider + channel）
        conn = self._registry.get(runner_id)
        plugin_id = conn.plugin_id if conn else ""
        self._registry.unregister(runner_id)
        self._outboxes.pop(runner_id, None)
        if self._host_bridge is not None:
            asyncio.create_task(
                self._host_bridge.on_runner_disconnected(runner_id, plugin_id),
                name=f"bridge-disconnect-{runner_id}",
            )
        logger.info("Runner %s 连接已清理", runner_id)

    # ── Phoenix-6: SDK RPC 辅助方法 ──────────────────────────────

    def _resolve_plugin_id(self, context: grpc.aio.ServicerContext) -> str | None:
        """从 metadata 的 session_token 中解析 plugin_id。

        使用 validate_session（可重复），避免一次性 token 问题。
        """
        md = dict(context.invocation_metadata())
        token = md.get("session_token", "")
        if self._token_service is not None and token:
            valid, plugin_id = self._token_service.validate_session(token)
            if valid:
                return plugin_id
        return None

    def _check_plugin_scope(self, plugin_id: str, scope: str) -> bool:
        """检查插件是否拥有指定 scope。"""
        if self._scope_store is None:
            return False
        return scope in self._scope_store.get_granted_scopes(plugin_id)

    # ── Phoenix-6: SDK RPC 实现 ──────────────────────────────────

    async def SendMessage(self, request, context: grpc.aio.ServicerContext):
        """发送消息 RPC。过滤 plugin_id → scope 校验 → 转发到 MessagePortV2。"""
        import base64

        from src.common.data_models.message_component_data_model import MessageSequence
        from src.core.message_port_registry import get_message_port_v2
        from src.plugin_runtime_v2.proto import plugin_host_pb2

        plugin_id = self._resolve_plugin_id(context)
        if plugin_id is None:
            return plugin_host_pb2.SendMessageResponse(success=False, error="AUTH_FAILED")

        scope_map = {
            "TEXT": "message:send:text",
            "IMAGE": "message:send:image",
            "EMOJI": "message:send:emoji",
            "FORWARD": "message:send:forward",
            "HYBRID": "message:send:hybrid",
        }
        scope = scope_map.get(request.message_type, "")
        if scope and not self._check_plugin_scope(plugin_id, scope):
            return plugin_host_pb2.SendMessageResponse(success=False, error="SCOPE_DENIED")

        # 组装 MessageSequence
        msg_seq = MessageSequence([])
        match request.message_type:
            case "TEXT":
                msg_seq.text(request.text_content)
            case "IMAGE":
                img_data = base64.b64decode(request.image_base64) if request.image_base64 else b""
                msg_seq.image(img_data)
            case "EMOJI":
                emoji_data = base64.b64decode(request.emoji_base64) if request.emoji_base64 else b""
                msg_seq.emoji(emoji_data)
            case "FORWARD":
                from src.common.data_models.message_component_data_model import ReplyComponent
                msg_seq.components.append(ReplyComponent(target_message_id=request.forward_message_id))
            case "HYBRID":
                import json as _json
                try:
                    payload = _json.loads(request.hybrid_payload)
                except _json.JSONDecodeError:
                    return plugin_host_pb2.SendMessageResponse(success=False, error="INVALID_HYBRID_PAYLOAD")
                msg_seq = self._build_hybrid_message(payload)

        if not msg_seq.components:
            return plugin_host_pb2.SendMessageResponse(success=False, error="EMPTY_MESSAGE")

        # 调用 MessagePortV2
        try:
            port = get_message_port_v2()
            result = await port.send_message(
                session_id=request.session_id,
                message=msg_seq,
                source=f"plugin:{plugin_id}",
            )
            if result.success:
                return plugin_host_pb2.SendMessageResponse(
                    success=True, message_id=result.message_id,
                )
            return plugin_host_pb2.SendMessageResponse(success=False, error=result.error or "SEND_FAILED")
        except Exception as e:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.ERROR, 'SendMessage RPC 转发失败', exception=e)
            logger.error("SendMessage RPC 转发失败: %s", e, exc_info=True)
            return plugin_host_pb2.SendMessageResponse(success=False, error="INTERNAL_ERROR")

    async def StorageGet(self, request, context: grpc.aio.ServicerContext):
        """键值读取 RPC。"""
        import json

        from src.plugin_runtime_v2.proto import plugin_host_pb2

        plugin_id = self._resolve_plugin_id(context)
        if plugin_id is None:
            return plugin_host_pb2.StorageGetResponse(found=False, error="AUTH_FAILED")
        if not self._check_plugin_scope(plugin_id, "database:read:self"):
            return plugin_host_pb2.StorageGetResponse(found=False, error="SCOPE_DENIED")
        if self._storage is None:
            return plugin_host_pb2.StorageGetResponse(found=False, error="STORAGE_NOT_AVAILABLE")

        default = None
        if request.default_value:
            try:
                default = json.loads(request.default_value)
            except json.JSONDecodeError:
                default = request.default_value
        value = self._storage.get(plugin_id, request.key, default)
        if value is None and default is None:
            return plugin_host_pb2.StorageGetResponse(found=False)
        return plugin_host_pb2.StorageGetResponse(
            found=True, value=json.dumps(value, ensure_ascii=False),
        )

    async def StorageSet(self, request, context: grpc.aio.ServicerContext):
        """键值写入 RPC。"""
        import json

        from src.plugin_runtime_v2.proto import plugin_host_pb2

        plugin_id = self._resolve_plugin_id(context)
        if plugin_id is None:
            return plugin_host_pb2.StorageSetResponse(success=False, error="AUTH_FAILED")
        if not self._check_plugin_scope(plugin_id, "database:write:self"):
            return plugin_host_pb2.StorageSetResponse(success=False, error="SCOPE_DENIED")
        if self._storage is None:
            return plugin_host_pb2.StorageSetResponse(success=False, error="STORAGE_NOT_AVAILABLE")

        try:
            value = json.loads(request.value)
        except json.JSONDecodeError:
            value = request.value
        self._storage.set(plugin_id, request.key, value)
        return plugin_host_pb2.StorageSetResponse(success=True)

    async def StorageDelete(self, request, context: grpc.aio.ServicerContext):
        """键值删除 RPC。"""
        from src.plugin_runtime_v2.proto import plugin_host_pb2

        plugin_id = self._resolve_plugin_id(context)
        if plugin_id is None:
            return plugin_host_pb2.StorageDeleteResponse(deleted=False, error="AUTH_FAILED")
        if not self._check_plugin_scope(plugin_id, "database:write:self"):
            return plugin_host_pb2.StorageDeleteResponse(deleted=False, error="SCOPE_DENIED")
        if self._storage is None:
            return plugin_host_pb2.StorageDeleteResponse(deleted=False, error="STORAGE_NOT_AVAILABLE")

        deleted = self._storage.delete(plugin_id, request.key)
        return plugin_host_pb2.StorageDeleteResponse(deleted=deleted)

    async def GetSessionInfo(self, request, context: grpc.aio.ServicerContext):
        """查询会话信息 RPC。"""
        from src.plugin_runtime_v2.proto import plugin_host_pb2

        plugin_id = self._resolve_plugin_id(context)
        if plugin_id is None:
            return plugin_host_pb2.GetSessionInfoResponse(found=False, error="AUTH_FAILED")
        if not self._check_plugin_scope(plugin_id, "session:read:detail"):
            return plugin_host_pb2.GetSessionInfoResponse(found=False, error="SCOPE_DENIED")

        from src.core.session_port_registry import get_session_info
        info = get_session_info(request.session_id)
        if info is None:
            return plugin_host_pb2.GetSessionInfoResponse(found=False, error="SESSION_NOT_FOUND")

        return plugin_host_pb2.GetSessionInfoResponse(
            found=True,
            session_id=info.session_id,
            session_name=info.session_name,
            platform=info.platform,
            is_group_session=info.is_group_session,
            primary_agent_id=info.primary_agent_id,
        )

    @staticmethod
    def _build_hybrid_message(payload: list) -> "MessageSequence":
        """从 JSON payload 构建 MessageSequence。

        payload 格式：[{"type": "text", "data": {"text": "..."}}]
        """
        import base64

        from src.common.data_models.message_component_data_model import (
            MessageSequence,
        )

        seq = MessageSequence([])
        for item in payload:
            comp_type = item.get("type", "")
            data = item.get("data", {})
            if comp_type == "text":
                seq.text(data.get("text", ""))
            elif comp_type == "image":
                img_b64 = data.get("base64", "")
                img_data = base64.b64decode(img_b64) if img_b64 else b""
                seq.image(img_data)
        return seq


# ZG16-6a: Host 侧 PluginConfigService 实现
class PluginConfigServicer:
    """Host 侧 PluginConfigService 实现。

    config:write scope 校验（填补既有 config:write:self / plugin:write:config 消费点）。
    """

    def __init__(self, config_manager, scope_validator) -> None:
        self._config_manager = config_manager
        self._scope_validator = scope_validator

    async def UpdatePluginConfig(
        self,
        request,
        context,
    ):
        """Host 侧推送配置到 Runner。"""
        from src.plugin_runtime_v2.proto import plugin_config_pb2

        # scope 校验（spec 4.3.1）——填补既有 config:write scope 消费点
        if not self._scope_validator.validate("config:write:self", context):
            return plugin_config_pb2.UpdatePluginConfigResponse(
                success=False, error="未授权 config:write:self scope"
            )
        # 推送配置到 Runner（通过 gRPC stub）
        try:
            await self._config_manager.handle_file_change(
                request.plugin_id, request.source
            )
            return plugin_config_pb2.UpdatePluginConfigResponse(
                success=True, new_revision=self._config_manager._revision_store.get(request.plugin_id)
            )
        except Exception as e:
            return plugin_config_pb2.UpdatePluginConfigResponse(success=False, error=str(e))
