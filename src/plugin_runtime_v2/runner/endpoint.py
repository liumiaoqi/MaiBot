"""gRPC Runner 端点 — 连接 Host 并暴露 InvokeTool 服务。

组合 gRPC 客户端（连 Host 的 Connect 双向流）和服务端（暴露 InvokeTool）。
"""


import asyncio
import json
from typing import Any

import grpc

from src.common.logger import get_logger
from src.plugin_runtime_v2.host.connection import ConnectionState
from src.plugin_runtime_v2.proto import common_pb2, plugin_host_pb2
from src.plugin_runtime_v2.proto.plugin_host_pb2_grpc import PluginHostStub
from src.plugin_runtime_v2.proto.plugin_runner_pb2_grpc import (
    add_PluginRunnerServicer_to_server,
)
from src.plugin_runtime_v2.runner.reconnect import ReconnectPolicy, RunnerEndpointConfig
from src.plugin_runtime_v2.runner.servicer import _PluginRunnerServicer
from src.plugin_runtime_v2.runner.tool_router import ToolRouter
from src.plugin_runtime_v2.lifecycle.refcount import PluginRefcount

logger = get_logger("plugin_runtime_v2.runner.endpoint")

# ── gRPC 通道 keepalive 配置（design.md 2.3.2.4） ──
_GRPC_CHANNEL_OPTIONS = [
    ("grpc.keepalive_time_ms", 30000),
    ("grpc.keepalive_timeout_ms", 10000),
    ("grpc.keepalive_permit_without_calls", 1),
    ("grpc.http2.max_pings_without_data", 0),
]

# ── gRPC 服务端 keepalive 配置 ──
_GRPC_SERVER_OPTIONS = [
    ("grpc.keepalive_time_ms", 30000),
    ("grpc.keepalive_timeout_ms", 10000),
    ("grpc.keepalive_permit_without_calls", 1),
    ("grpc.http2.max_pings_without_data", 0),
    ("grpc.http2.min_time_between_pings_ms", 10000),
    ("grpc.http2.min_ping_interval_without_data_ms", 5000),
]


class RunnerEndpoint:
    """gRPC Runner 端点 — 连接 Host 并管理双向流。"""

    def __init__(self, config: RunnerEndpointConfig, plugin_loader=None) -> None:
        self._config = config
        self._channel: grpc.aio.Channel | None = None
        self._server: grpc.aio.Server | None = None
        self._state: ConnectionState = ConnectionState.DISCONNECTED
        self._reconnect = ReconnectPolicy(
            max_retries=config.reconnect_max_retries,
            initial_delay_s=config.reconnect_initial_delay_s,
            max_delay_s=config.reconnect_max_delay_s,
        )
        self._tool_router = ToolRouter()
        self._servicer = _PluginRunnerServicer(tool_router=self._tool_router)
        self._shutting_down: bool = False
        self._stream_call: grpc.aio.StreamStreamCall | None = None
        self._recv_task: asyncio.Task | None = None
        self._plugin_loader = plugin_loader
        self._plugin_instance = None
        self._granted_scopes: set[str] = set()
        # ZG-15：插件活体引用（加载成功后创建，注入 servicer/loader）
        self._refcount: PluginRefcount | None = None
        self._unloader = None

    # ── 公共 API ────────────────────────────────────────────────

    def is_going(self) -> bool:
        """插件是否处于 GOING/UNFORMED 状态（ZG-15：ctx.register_task 拒新检查）。

        CX 审查 P1：UNFORMED（已卸载）同样拒新——卸载后 register_task 不放行。
        """
        if self._refcount is None:
            return False
        return self._refcount.state.value in ("going", "unformed")

    async def start(self) -> None:
        """启动 Runner：连接 Host、握手、注册、进入接收循环。

        失败时自动重连（指数退避），握手被拒绝则停止。
        """
        self._shutting_down = False

        # 加载插件（仅首次，重连时复用）
        if self._plugin_loader is not None and not self._plugin_loader.is_loaded:
            tools, events, homecard_registry, plugin_instance = await self._plugin_loader.load()
            if plugin_instance is not None:
                self._config.tools = tools
                self._config.events = events
                self._plugin_instance = plugin_instance
                # ZG-15：创建活体引用并注入 servicer（拒新 + GetInflightCount）
                self._refcount = PluginRefcount(self._config.plugin_id)
                self._servicer.set_refcount(self._refcount)
                # 注入 PluginContext
                from src.plugin_runtime_v2.sdk.context import PluginContext
                ctx = PluginContext(
                    plugin_id=self._config.plugin_id,
                    granted_scopes=set(self._config.scopes),
                    runner_endpoint=self,
                    homecard_registry=homecard_registry,
                )
                self._plugin_instance.ctx = ctx
                # ZG-15：卸载编排器（三条卸载路径统一走 PluginUnloader）
                from src.plugin_runtime_v2.lifecycle.unloader import PluginUnloader
                self._unloader = PluginUnloader(
                    refcount=self._refcount,
                    loader=self._plugin_loader,
                    ctx=ctx,
                )
                for tool_entry in tools:
                    self._tool_router.register(
                        tool_name=tool_entry["name"],
                        plugin=self._plugin_instance,
                        handler=tool_entry["handler"],
                        refcount=self._refcount,
                    )
                # 调用 on_load
                try:
                    await self._plugin_instance.on_load()
                except Exception as exc:
                    from src.core.error_escalation.types import ErrorLevel
                    from src.core.error_escalation_port_registry import get_error_escalation_port
                    port = get_error_escalation_port()
                    if port is not None:
                        port.report(ErrorLevel.ERROR, "插件 on_load 失败", exception=exc)
                    logger.error("插件 on_load 失败: %s", exc)

        while True:
            if self._shutting_down:
                return
            self._transition(ConnectionState.CONNECTING)
            try:
                await self._connect_and_handshake()
                # 连接+握手+注册成功，进入 READY
                self._reconnect.reset()
                # 阻塞等待接收循环结束（连接断开），然后重连
                recv_task = self._recv_task
                if recv_task is not None:
                    try:
                        await recv_task
                    except asyncio.CancelledError:
                        return
                continue
            except _HandshakeRejected as exc:
                logger.error("Runner %s 握手被拒绝: %s，停止重连", self._config.runner_id, exc)
                self._transition(ConnectionState.DISCONNECTED)
                return
            except Exception as exc:
                from src.core.error_escalation.types import ErrorLevel
                from src.core.error_escalation_port_registry import get_error_escalation_port
                port = get_error_escalation_port()
                if port is not None:
                    port.report(ErrorLevel.WARNING, "Runner 连接失败", exception=exc)
                logger.warning(
                    "Runner %s 连接失败: %s", self._config.runner_id, exc
                )
                self._transition(ConnectionState.DISCONNECTED)
                delay = self._reconnect.next_delay()
                if delay is None:
                    logger.error(
                        "Runner %s 重连耗尽（%d次），进入终态",
                        self._config.runner_id, self._config.reconnect_max_retries,
                    )
                    return
                logger.warning(
                    "Runner %s %.1fs 后重连（第 %d 次）",
                    self._config.runner_id, delay, self._reconnect._attempt,
                )
                await asyncio.sleep(delay)

    async def stop(self) -> None:
        """停止 Runner：卸载插件（若未卸载）→ 关闭双向流、停服务端、关通道。"""
        self._shutting_down = True
        self._servicer._shutting_down = True
        # ZG-15：SIGTERM 路径统一走 PluginUnloader（若 ShutdownRequest 路径已卸载则跳过）
        if (self._unloader is not None and self._refcount is not None
                and self._refcount.state.value != "unformed"):
            await self._unloader.unload_plugin()
            self._plugin_instance = None
        if self._recv_task is not None:
            self._recv_task.cancel()
            self._recv_task = None
        if self._stream_call is not None:
            self._stream_call.cancel()
            self._stream_call = None
        if self._server is not None:
            await self._server.stop(grace=5)
            self._server = None
        if self._channel is not None:
            await self._channel.close()
            self._channel = None
        self._transition(ConnectionState.DISCONNECTED)

    async def emit_event(self, event_name: str, payload: dict[str, Any]) -> None:
        """推送 Event 到 Host。"""
        if self._state != ConnectionState.READY:
            raise ConnectionError("Runner not in READY state")
        if self._stream_call is None:
            raise ConnectionError("Stream not available")
        msg = common_pb2.RunnerMessage(
            event=common_pb2.EventPayload(
                event_name=event_name,
                payload=json.dumps(payload, ensure_ascii=False),
            )
        )
        try:
            await self._stream_call.write(msg)
        except grpc.aio.AioRpcError:
            logger.warning("Runner %s emit_event 写入失败: %s",
                           self._config.runner_id, event_name)

    @property
    def state(self) -> ConnectionState:
        return self._state

    @property
    def is_ready(self) -> bool:
        return self._state == ConnectionState.READY

    # ── 内部：连接 + 握手 + 注册流程 ─────────────────────────────

    async def _connect_and_handshake(self) -> None:
        """完整连接流程：通道 → 服务端 → Connect → 握手 → 注册 → 接收循环。"""
        # 1. 创建 gRPC 通道
        self._channel = grpc.aio.insecure_channel(
            self._config.host_address,
            options=_GRPC_CHANNEL_OPTIONS,
        )

        # 2. 启动 PluginRunner gRPC 服务端（随机端口）
        self._server = grpc.aio.server(options=_GRPC_SERVER_OPTIONS)
        add_PluginRunnerServicer_to_server(self._servicer, self._server)
        listen_port = self._server.add_insecure_port("127.0.0.1:0")
        await self._server.start()
        runner_listen_address = f"127.0.0.1:{listen_port}"

        # 3. Connect 双向流（使用 read/write API，不与 iterator API 混用）
        stub = PluginHostStub(self._channel)

        self._transition(ConnectionState.HANDSHAKING)
        call: grpc.aio.StreamStreamCall = stub.Connect()
        self._stream_call = call

        # 4. 发送 HelloPayload
        await call.write(
            common_pb2.RunnerMessage(
                hello=common_pb2.HelloPayload(
                    runner_id=self._config.runner_id,
                    sdk_version=self._config.sdk_version,
                    session_token=self._config.session_token,
                    scopes=self._config.scopes,
                    runner_listen_address=runner_listen_address,
                )
            )
        )

        # 5. 等待 HelloResponse
        try:
            first_response: common_pb2.HostMessage = await asyncio.wait_for(
                call.read(), timeout=10.0,
            )
        except asyncio.TimeoutError:
            raise _HandshakeRejected("HelloResponse 超时") from None

        if first_response.WhichOneof("payload") != "hello_response":
            raise _HandshakeRejected("首条 HostMessage 非 HelloResponse") from None

        hr = first_response.hello_response
        if not hr.accepted:
            raise _HandshakeRejected(hr.reason or "unknown")

        # 处理 rejected_scopes：更新 _granted_scopes
        if hr.rejected_scopes:
            rejected = set(hr.rejected_scopes)
            self._granted_scopes = set(self._config.scopes) - rejected
            logger.warning(
                "Runner %s 部分 scope 被拒绝: %s, granted=%s",
                self._config.runner_id, hr.rejected_scopes, self._granted_scopes,
            )
            if self._plugin_instance is not None:
                self._plugin_instance.ctx.update_granted_scopes(self._granted_scopes)
        else:
            self._granted_scopes = set(self._config.scopes)

        logger.info("Runner %s 握手成功，host=%s", self._config.runner_id, hr.host_version)

        # 5. RegisterComponents
        self._transition(ConnectionState.REGISTERING)
        reg_resp = await stub.RegisterComponents(
            plugin_host_pb2.RegisterComponentsRequest(
                plugin_id=self._config.plugin_id,
                plugin_version=self._config.plugin_version,
                tools=[
                    plugin_host_pb2.ToolDeclaration(
                        name=t.get("name", ""),
                        description=t.get("description", ""),
                        parameters_schema=json.dumps(t.get("parameters_schema") or {}),
                        output_schema=json.dumps(t.get("output_schema") or {}),
                    )
                    for t in self._config.tools
                ],
                events=[
                    plugin_host_pb2.EventDeclaration(
                        name=e.get("name", ""),
                        description=e.get("description", ""),
                        event_schema=json.dumps(e.get("event_schema") or {}),
                    )
                    for e in self._config.events
                ],
            )
        )
        if not reg_resp.accepted:
            raise _HandshakeRejected(
                f"组件注册失败: {', '.join(reg_resp.reasons)}"
            )

        self._transition(ConnectionState.READY)
        logger.info("Runner %s 注册成功，进入 READY", self._config.runner_id)

        # 6. 接收循环作为后台任务，start() 立即返回
        self._recv_task = asyncio.create_task(
            self._recv_loop(call), name=f"recv-{self._config.runner_id}",
        )

    async def _recv_loop(self, call: grpc.aio.StreamStreamCall) -> None:
        """HostMessage 接收循环。"""
        try:
            while True:
                msg = await call.read()
                if msg is grpc.aio.EOF:
                    break
                payload_kind = msg.WhichOneof("payload")
                if payload_kind == "heartbeat":
                    hb = msg.heartbeat
                    await call.write(
                        common_pb2.RunnerMessage(
                            heartbeat=common_pb2.HeartbeatResponse(
                                timestamp_ms=hb.timestamp_ms,
                            )
                        )
                    )
                elif payload_kind == "shutdown":
                    sd = msg.shutdown
                    logger.info(
                        "Runner %s 收到 ShutdownRequest: reason=%s drain=%dms",
                        self._config.runner_id, sd.reason, sd.drain_timeout_ms,
                    )
                    await self._handle_shutdown(sd.drain_timeout_ms)
                    return
                elif payload_kind == "hello_response":
                    pass  # 已在握手阶段处理
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, "Runner 接收循环异常", exception=exc)
            logger.warning("Runner %s 接收循环异常: %s", self._config.runner_id, exc)
        finally:
            self._stream_call = None
            if not self._shutting_down:
                self._transition(ConnectionState.DISCONNECTED)

    async def _handle_shutdown(self, drain_timeout_ms: int) -> None:
        """优雅关停：置 GOING 拒新 → 等待在途排空 → 卸载插件 → 关闭流。

        ZG-15：固定 sleep 替换为 wait_drained（引用计数驱动排空）。
        """
        self._shutting_down = True
        self._servicer._shutting_down = True
        self._transition(ConnectionState.CLOSING)

        if self._refcount is not None:
            # 置 GOING（对标 try_stop_module），新 acquire 立即失败
            self._refcount.mark_going()
            if drain_timeout_ms > 0:
                drained = await self._refcount.wait_drained(
                    timeout_s=drain_timeout_ms / 1000.0)
                if not drained:
                    logger.warning(
                        "Runner %s 排空超时（%dms），强制关停",
                        self._config.runner_id, drain_timeout_ms,
                    )

        # 卸载插件（on_unload + 自启任务取消，对标 mod->exit()）
        if self._plugin_instance is not None and self._unloader is not None:
            await self._unloader.unload_plugin()
            self._plugin_instance = None

        if self._stream_call is not None:
            self._stream_call.cancel()
            self._stream_call = None

    # ── 内部工具 ────────────────────────────────────────────────

    def _transition(self, new_state: ConnectionState) -> None:
        """状态转换，含日志。"""
        old_state = self._state
        self._state = new_state
        logger.info(
            "Runner %s 状态变更: %s → %s",
            self._config.runner_id, old_state.value, new_state.value,
        )


    # ── Phoenix-6: SDK RPC 客户端方法 ────────────────────────────

    async def send_message(
        self, message_type: str, session_id: str, **kwargs,
    ) -> dict[str, Any]:
        """发送消息 RPC 客户端。"""
        if self._channel is None:
            return {"success": False, "error": "CHANNEL_NOT_READY"}
        from src.plugin_runtime_v2.proto.plugin_host_pb2_grpc import PluginHostStub
        from src.plugin_runtime_v2.proto import plugin_host_pb2

        stub = PluginHostStub(self._channel)
        metadata = [("session_token", self._config.session_token)]
        req = plugin_host_pb2.SendMessageRequest(
            session_id=session_id,
            message_type=message_type,
            text_content=kwargs.get("text", ""),
            image_base64=kwargs.get("image_base64", ""),
            emoji_base64=kwargs.get("emoji_base64", ""),
            forward_message_id=kwargs.get("message_id", ""),
            hybrid_payload=kwargs.get("hybrid_payload", ""),
        )
        resp = await stub.SendMessage(req, metadata=metadata)
        return {"success": resp.success, "error": resp.error, "message_id": resp.message_id}

    async def storage_get(self, key: str, default: Any = None) -> Any:
        """键值读取 RPC 客户端。"""
        if self._channel is None:
            return default
        from src.plugin_runtime_v2.proto.plugin_host_pb2_grpc import PluginHostStub
        from src.plugin_runtime_v2.proto import plugin_host_pb2

        stub = PluginHostStub(self._channel)
        metadata = [("session_token", self._config.session_token)]
        req = plugin_host_pb2.StorageGetRequest(
            key=key, default_value=json.dumps(default),
        )
        resp = await stub.StorageGet(req, metadata=metadata)
        if resp.found:
            return json.loads(resp.value)
        return default

    async def storage_set(self, key: str, value: Any) -> bool:
        """键值写入 RPC 客户端。"""
        if self._channel is None:
            return False
        from src.plugin_runtime_v2.proto.plugin_host_pb2_grpc import PluginHostStub
        from src.plugin_runtime_v2.proto import plugin_host_pb2

        stub = PluginHostStub(self._channel)
        metadata = [("session_token", self._config.session_token)]
        resp = await stub.StorageSet(
            plugin_host_pb2.StorageSetRequest(key=key, value=json.dumps(value)),
            metadata=metadata,
        )
        return resp.success

    async def storage_delete(self, key: str) -> bool:
        """键值删除 RPC 客户端。"""
        if self._channel is None:
            return False
        from src.plugin_runtime_v2.proto.plugin_host_pb2_grpc import PluginHostStub
        from src.plugin_runtime_v2.proto import plugin_host_pb2

        stub = PluginHostStub(self._channel)
        metadata = [("session_token", self._config.session_token)]
        resp = await stub.StorageDelete(
            plugin_host_pb2.StorageDeleteRequest(key=key),
            metadata=metadata,
        )
        return resp.deleted

    async def get_session_info(self, session_id: str) -> dict[str, Any]:
        """查询会话信息 RPC 客户端。"""
        if self._channel is None:
            return {"found": False}
        from src.plugin_runtime_v2.proto.plugin_host_pb2_grpc import PluginHostStub
        from src.plugin_runtime_v2.proto import plugin_host_pb2

        stub = PluginHostStub(self._channel)
        metadata = [("session_token", self._config.session_token)]
        resp = await stub.GetSessionInfo(
            plugin_host_pb2.GetSessionInfoRequest(session_id=session_id),
            metadata=metadata,
        )
        return {
            "found": resp.found,
            "session_id": resp.session_id,
            "session_name": resp.session_name,
            "platform": resp.platform,
            "is_group_session": resp.is_group_session,
            "primary_agent_id": resp.primary_agent_id,
        }


class _HandshakeRejected(Exception):
    """握手被拒绝（业务拒绝，不重连）。"""
