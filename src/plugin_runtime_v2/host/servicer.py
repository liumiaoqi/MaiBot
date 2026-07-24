"""gRPC Host 服务实现 — Connect 双向流 + RegisterComponents 一元 RPC。

实现 service PluginHost：握手校验、组件注册、消息循环、注册超时。
"""

from __future__ import annotations

import asyncio
import importlib.metadata
import time
from typing import AsyncIterator

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


class _PluginHostServicer(PluginHostServicer):
    """PluginHost gRPC 服务实现。

    处理 Runner 的连接握手、组件注册和消息循环。
    """

    def __init__(
        self,
        registry: RunnerRegistry,
        heartbeat_mgr: HeartbeatManager,
        config: HostEndpointConfig,
    ) -> None:
        self._registry = registry
        self._heartbeat_mgr = heartbeat_mgr
        self._config = config

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
                request_iterator.__anext__(), timeout=10.0,
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
        self._registry.register(conn)

        logger.info("Runner %s 握手成功，sdk=%s", runner_id, hello.sdk_version)
        try:
            host_ver = importlib.metadata.version("maibot")
        except importlib.metadata.PackageNotFoundError:
            host_ver = "unknown"
        yield common_pb2.HostMessage(
            hello_response=common_pb2.HelloResponse(
                accepted=True,
                host_version=host_ver,
            )
        )

        # ── 注册等待阶段 ──
        conn.transition(ConnectionState.REGISTERING)
        outbox: asyncio.Queue[common_pb2.HostMessage] = asyncio.Queue(maxsize=64)
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
            """心跳连续超时回调：关闭双向流。"""
            logger.warning("Runner %s 心跳超时，关闭双向流", rid)
            await context.abort(grpc.StatusCode.UNAVAILABLE, "heartbeat timeout")

        self._heartbeat_mgr.start(runner_id, _send_heartbeat, _on_heartbeat_timeout)

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
                        await outbox.put(
                            common_pb2.HostMessage(
                                event_ack=common_pb2.EventAck(received=True),
                            )
                        )
                    elif payload_kind == "heartbeat":
                        self._heartbeat_mgr.record_response(runner_id)
                        conn.record_heartbeat()
            except Exception:
                logger.debug("Runner %s 接收循环退出", runner_id, exc_info=True)
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
                pass

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
        """校验 HelloPayload，返回 (accepted, reason)。"""
        if not hello.runner_id:
            return False, "MISSING_REQUIRED_FIELD: runner_id"
        if not hello.sdk_version:
            return False, "MISSING_REQUIRED_FIELD: sdk_version"
        if not hello.session_token:
            return False, "MISSING_REQUIRED_FIELD: session_token"
        if not hello.scopes:
            return False, "MISSING_REQUIRED_FIELD: scopes"
        if self._registry.has(hello.runner_id):
            return False, "RUNNER_ALREADY_CONNECTED"
        if not _check_sdk_version(hello.sdk_version):
            return False, "SDK_VERSION_MISMATCH"
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

    def _cleanup_connection(self, runner_id: str) -> None:
        """清理 Runner 连接资源。"""
        self._heartbeat_mgr.stop(runner_id)
        self._registry.unregister(runner_id)
        logger.info("Runner %s 连接已清理", runner_id)
