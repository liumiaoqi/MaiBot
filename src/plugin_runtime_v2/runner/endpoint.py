"""gRPC Runner 端点 — 连接 Host 并暴露 InvokeTool 服务。

组合 gRPC 客户端（连 Host 的 Connect 双向流）和服务端（暴露 InvokeTool）。
"""

from __future__ import annotations

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

    def __init__(self, config: RunnerEndpointConfig) -> None:
        self._config = config
        self._channel: grpc.aio.Channel | None = None
        self._server: grpc.aio.Server | None = None
        self._state: ConnectionState = ConnectionState.DISCONNECTED
        self._reconnect = ReconnectPolicy(
            max_retries=config.reconnect_max_retries,
            initial_delay_s=config.reconnect_initial_delay_s,
            max_delay_s=config.reconnect_max_delay_s,
        )
        self._servicer = _PluginRunnerServicer()
        self._shutting_down: bool = False
        self._stream_call: grpc.aio.StreamStreamCall | None = None
        self._recv_task: asyncio.Task | None = None

    # ── 公共 API ────────────────────────────────────────────────

    async def start(self) -> None:
        """启动 Runner：连接 Host、握手、注册、进入接收循环。

        失败时自动重连（指数退避），握手被拒绝则停止。
        """
        self._shutting_down = False


        while True:
            self._transition(ConnectionState.CONNECTING)
            try:
                await self._connect_and_handshake()
                # 连接+握手+注册成功，进入 READY
                self._reconnect.reset()
                return
            except _HandshakeRejected as exc:
                logger.error("Runner %s 握手被拒绝: %s，停止重连", self._config.runner_id, exc)
                self._transition(ConnectionState.DISCONNECTED)
                return
            except Exception as exc:
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
        """停止 Runner：关闭双向流、停服务端、关通道。"""
        self._shutting_down = True
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
            logger.warning("Runner %s 接收循环异常: %s", self._config.runner_id, exc)
        finally:
            self._stream_call = None
            if not self._shutting_down:
                self._transition(ConnectionState.DISCONNECTED)

    async def _handle_shutdown(self, drain_timeout_ms: int) -> None:
        """优雅关停：停止接受新调用，等待排空，关闭流。"""
        self._shutting_down = True
        self._transition(ConnectionState.CLOSING)

        if drain_timeout_ms > 0:
            try:
                await asyncio.sleep(drain_timeout_ms / 1000.0)
            except asyncio.CancelledError:
                pass

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


class _HandshakeRejected(Exception):
    """握手被拒绝（业务拒绝，不重连）。"""
